"""Local one-shot entry point for validating a real video."""

from __future__ import annotations

import argparse
import json
import os
import signal
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import FrameType
from typing import Self

from backend.app.schemas.agent_runtime import InternalAgentHandoff
from backend.app.schemas.task import (
    AssetKind,
    InternalAssetRead,
    InternalTaskClaim,
    InternalTaskClaimRequest,
    InternalTaskHeartbeat,
    InternalTaskStateUpdate,
    TaskStage,
    TaskStatus,
)
from worker.adapters.asr import AsrAdapter, LocalWhisperAdapter
from worker.adapters.translation import TranslationAdapter
from worker.cleanup import cleanup_path
from worker.errors import WorkerError, WorkerErrorCode, public_worker_error_message
from worker.job_store import ClaimingJobStore, HttpJobStore, LocalJobStore
from worker.pipeline import run_pipeline
from worker.runtime import PollPolicy, RuntimeCounters, run_forever
from worker.types import PipelineResult, PipelineTask

WORKER_CLAIM_STAGES = [
    TaskStage.UPLOADED,
    TaskStage.EXTRACT_AUDIO,
    TaskStage.TRANSCRIBE,
]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从真实课堂视频生成带时间戳逐字稿")
    parser.add_argument("video", type=Path, nargs="?")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", default=os.getenv("WHISPER_MODEL", "tiny"))
    parser.add_argument("--language", default=None)
    parser.add_argument("--api-base-url")
    parser.add_argument("--worker-id", default=os.getenv("WORKER_ID", "media-worker-local"))
    parser.add_argument("--lease-seconds", type=int, default=300)
    parser.add_argument("--object-root", type=Path)
    parser.add_argument("--once", action="store_true")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "5")),
    )
    parser.add_argument(
        "--max-backoff",
        type=float,
        default=float(os.getenv("WORKER_MAX_BACKOFF_SECONDS", "30")),
    )
    return parser


class HeartbeatLease:
    """Renew a claimed task until work completes or renewal fails."""

    def __init__(
        self,
        store: ClaimingJobStore,
        claim: InternalTaskClaim,
        *,
        worker_id: str,
        lease_seconds: int,
        interval_seconds: float | None = None,
    ) -> None:
        self.store = store
        self.claim = claim
        self.heartbeat = InternalTaskHeartbeat(
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )
        self.interval_seconds = interval_seconds or max(1.0, lease_seconds / 3)
        self.stop_event = threading.Event()
        self._finished = threading.Event()
        self._failure: WorkerError | None = None
        self._thread = threading.Thread(
            target=self._run,
            name=f"heartbeat-{claim.task_id}",
            daemon=True,
        )

    def _run(self) -> None:
        while not self._finished.is_set():
            try:
                self.store.heartbeat(self.claim.task_id, self.heartbeat)
            except WorkerError as exc:
                self._failure = exc
                self.stop_event.set()
                return
            self._finished.wait(self.interval_seconds)

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._finished.set()
        self._thread.join(timeout=max(1.0, self.interval_seconds * 2))
        if self._thread.is_alive():
            raise WorkerError(
                WorkerErrorCode.STOPPED,
                "heartbeat 线程未能按时停止。",
                retryable=True,
            )

    def raise_if_failed(self) -> None:
        if self._failure is not None:
            raise self._failure


def run_claimed_once[T](
    store: ClaimingJobStore,
    request: InternalTaskClaimRequest,
    process: Callable[[InternalTaskClaim, threading.Event], T],
    *,
    heartbeat_interval_seconds: float | None = None,
) -> T | None:
    claim = store.claim(request)
    if claim is None:
        return None
    with HeartbeatLease(
        store,
        claim,
        worker_id=request.worker_id,
        lease_seconds=request.lease_seconds,
        interval_seconds=heartbeat_interval_seconds,
    ) as lease:
        result = process(claim, lease.stop_event)
        lease.raise_if_failed()
        return result


def _claimed_video_asset(claim: InternalTaskClaim) -> InternalAssetRead:
    video_assets = [asset for asset in claim.assets if asset.kind is AssetKind.VIDEO]
    if not video_assets:
        raise WorkerError(
            WorkerErrorCode.INPUT_NOT_FOUND,
            "领取任务中没有视频资源。",
        )
    return video_assets[0]


@contextmanager
def _claimed_input_path(
    claim: InternalTaskClaim,
    store: HttpJobStore,
    object_root: Path | None,
) -> Iterator[Path]:
    asset = _claimed_video_asset(claim)
    if object_root is None:
        work_dir = Path(tempfile.mkdtemp(prefix=f"classroom-download-{claim.task_id}-"))
        candidate = work_dir / "source-media"
        primary_failure: BaseException | None = None
        try:
            store.download_asset(asset, candidate)
            yield candidate
        except BaseException as exc:
            primary_failure = exc
            raise
        finally:
            try:
                cleanup_path(work_dir)
            except WorkerError as cleanup_error:
                if primary_failure is not None:
                    primary_failure.add_note(f"{cleanup_error.code.value}: {cleanup_error}")
                else:
                    raise
        return

    root = object_root.resolve()
    candidate = (root / asset.object_key).resolve()
    if not candidate.is_relative_to(root):
        raise WorkerError(
            WorkerErrorCode.INPUT_NOT_FOUND,
            "视频对象地址越出允许的媒体目录。",
        )
    yield candidate


def _process_claimed_media(
    claim: InternalTaskClaim,
    stop: threading.Event,
    store: HttpJobStore,
    adapter: AsrAdapter,
    object_root: Path | None,
    worker_id: str,
    translation_adapter: TranslationAdapter | None = None,
) -> PipelineResult:
    pipeline_started = False
    pipeline_completed = False
    try:
        with _claimed_input_path(claim, store, object_root) as input_path:
            pipeline_started = True
            result = run_pipeline(
                PipelineTask(
                    task_id=claim.task_id,
                    trace_id=claim.trace_id,
                    input_path=input_path,
                ),
                adapter,
                store,
                stop_event=stop,
                translation_adapter=translation_adapter,
            )
            pipeline_completed = True
        store.handoff_agent(
            claim.task_id,
            InternalAgentHandoff(worker_id=worker_id),
        )
        return result
    except WorkerError as exc:
        if exc.code is WorkerErrorCode.STOPPED:
            raise
        # run_pipeline 自己记录其内部失败。下载尚未进入 pipeline，或 pipeline
        # 成功后外层下载目录清理失败时，必须由 runner 补写真实失败状态。
        if not pipeline_started or pipeline_completed:
            stage = TaskStage.EXTRACT_AUDIO if not pipeline_started else TaskStage.TRANSLATE
            store.update_state(
                claim.task_id,
                InternalTaskStateUpdate(
                    stage=stage,
                    status=TaskStatus.FAILED,
                    progress=0.0,
                    message=f"{exc.code.value}: {public_worker_error_message(exc.code)}",
                    error_code=exc.platform_code,
                    trace_id=claim.trace_id,
                ),
            )
        raise


def _install_signal_handlers(stop_event: threading.Event) -> None:
    """Request a graceful stop from the process main thread."""

    def request_stop(_signum: int, _frame: FrameType | None) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)


def _run_remote(
    args: argparse.Namespace,
    stop_event: threading.Event,
) -> RuntimeCounters | None:
    """Run one diagnostic claim or the resident single-Worker loop."""

    service_token = os.getenv("WORKER_SERVICE_TOKEN")
    if not service_token:
        raise WorkerError(
            WorkerErrorCode.JOB_STORE_AUTH_FAILED,
            "远程模式缺少 WORKER_SERVICE_TOKEN。",
            retryable=False,
        )

    adapter = LocalWhisperAdapter(args.model, language=args.language)
    store = HttpJobStore(args.api_base_url, service_token)
    request = InternalTaskClaimRequest(
        worker_id=args.worker_id,
        stages=WORKER_CLAIM_STAGES,
        lease_seconds=args.lease_seconds,
    )

    def run_once() -> PipelineResult | None:
        return run_claimed_once(
            store,
            request,
            lambda claim, stop: _process_claimed_media(
                claim,
                stop,
                store,
                adapter,
                args.object_root,
                args.worker_id,
            ),
        )

    try:
        if args.once:
            run_once()
            return None
        return run_forever(
            run_once,
            stop_event=stop_event,
            policy=PollPolicy(
                idle_seconds=args.poll_interval,
                max_backoff_seconds=args.max_backoff,
            ),
        )
    finally:
        store.close()


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.api_base_url:
        if not os.getenv("WORKER_SERVICE_TOKEN"):
            parser.error("远程模式必须配置 WORKER_SERVICE_TOKEN 环境变量")
        if args.poll_interval < 0:
            parser.error("--poll-interval 必须大于或等于 0")
        if args.max_backoff < 1:
            parser.error("--max-backoff 必须大于或等于 1")

        stop_event = threading.Event()
        _install_signal_handlers(stop_event)
        counters = _run_remote(args, stop_event)
        if counters is None:
            print("已完成一次诊断领取")
        else:
            print(
                "Worker 已停止："
                f"处理 {counters.claimed} 个任务，"
                f"空闲轮询 {counters.idle} 次，"
                f"可重试失败 {counters.retryable_failures} 次"
            )
        return 0

    if args.video is None or args.output is None:
        parser.error("本地模式必须提供 video 和 --output")
    adapter = LocalWhisperAdapter(args.model, language=args.language)
    store = LocalJobStore()
    task = PipelineTask(input_path=args.video)
    result = run_pipeline(
        task,
        adapter,
        store,
    )
    transcript = store.transcripts[task.task_id]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(transcript.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"完成：{result.transcript_segments} 段，"
        f"{result.duration_ms / 1000:.1f} 秒；输出 {args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
