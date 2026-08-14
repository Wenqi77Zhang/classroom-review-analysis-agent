"""领取一个 analyze 任务，运行受约束 Agent，并回写待复核结论。"""

from __future__ import annotations

import argparse
import asyncio
import os
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Self

from agent.contracts import AgentErrorCode, AnalysisInput, EvidenceItem
from agent.job_store import AgentJobStore, AgentJobStoreError, HttpAgentJobStore
from agent.observability.tracing import JsonlTraceSink
from agent.orchestrator import AgentOrchestrator, AgentRunError
from agent.providers import ProviderRouter
from agent.providers.cloud import CloudModelProvider
from agent.providers.local import LocalModelProvider
from agent.skills import load_domain_skills
from agent.validators import load_conclusion_validator
from backend.app.schemas.agent_runtime import (
    InternalAgentClaimRequest,
    InternalAgentHeartbeat,
    InternalAgentTaskClaim,
)
from backend.app.schemas.common import ErrorCode
from backend.app.schemas.task import InternalTaskStateUpdate, TaskStage, TaskStatus


@dataclass(slots=True)
class _HeartbeatMonitor:
    store: AgentJobStore
    claim: InternalAgentTaskClaim
    agent_id: str
    lease_seconds: int
    interval_seconds: float
    _stop: threading.Event = field(init=False, default_factory=threading.Event)
    _failure: AgentJobStoreError | None = field(init=False, default=None)
    _thread: threading.Thread = field(init=False)

    def __post_init__(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name=f"agent-heartbeat-{self.claim.task_id}",
            daemon=True,
        )

    def __enter__(self) -> Self:
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join(timeout=max(1.0, self.interval_seconds + 1.0))

    def ensure_lease(self) -> None:
        if self._failure is not None:
            raise self._failure

    def _run(self) -> None:
        heartbeat = InternalAgentHeartbeat(
            agent_id=self.agent_id,
            lease_seconds=self.lease_seconds,
        )
        while not self._stop.wait(self.interval_seconds):
            try:
                self.store.heartbeat(self.claim.task_id, heartbeat)
            except AgentJobStoreError as exc:
                self._failure = exc
                self._stop.set()
                return


def _analysis_input(claim: InternalAgentTaskClaim) -> AnalysisInput:
    return AnalysisInput(
        task_id=claim.task_id,
        owner_id=claim.owner_id,
        contract=claim.analysis_contract,
        evidence=[
            EvidenceItem.model_validate(item.model_dump(mode="python"))
            for item in claim.evidence
        ],
        trace_id=claim.trace_id,
    )


def _public_failure(error: BaseException) -> tuple[ErrorCode, str]:
    if isinstance(error, AgentRunError):
        if error.code is AgentErrorCode.BILINGUAL_EVIDENCE_INCOMPLETE:
            return (
                ErrorCode.SCHEMA_INVALID,
                "分析契约要求中英双语，但当前逐字稿没有完整译文。请补充译文，或确认本节为纯中文后关闭双语并重新处理。",
            )
        if error.code in {
            AgentErrorCode.PROVIDER_NOT_CONFIGURED,
            AgentErrorCode.MODEL_PROVIDER_ERROR,
        }:
            return ErrorCode.UPSTREAM_UNAVAILABLE, "分析模型暂时不可用，请稍后重试。"
        if error.code is AgentErrorCode.AGENT_INTERNAL_ERROR:
            return ErrorCode.INTERNAL_ERROR, "教学分析运行失败，请联系管理员并提供 Trace ID。"
        return ErrorCode.SCHEMA_INVALID, "分析输入或模型输出未通过证据与结构校验。"
    if isinstance(error, AgentJobStoreError):
        return ErrorCode.UPSTREAM_UNAVAILABLE, "分析服务暂时无法连接任务后端。"
    return ErrorCode.INTERNAL_ERROR, "教学分析运行失败，请联系管理员并提供 Trace ID。"


async def run_claimed_once(
    store: AgentJobStore,
    orchestrator: AgentOrchestrator,
    request: InternalAgentClaimRequest,
    *,
    heartbeat_interval_seconds: float | None = None,
) -> InternalAgentTaskClaim | None:
    claim = store.claim(request)
    if claim is None:
        return None
    interval = heartbeat_interval_seconds or max(10.0, request.lease_seconds / 3)
    monitor = _HeartbeatMonitor(
        store=store,
        claim=claim,
        agent_id=request.agent_id,
        lease_seconds=request.lease_seconds,
        interval_seconds=interval,
    )
    try:
        with monitor:
            store.update_state(
                claim.task_id,
                InternalTaskStateUpdate(
                    stage=TaskStage.ANALYZE,
                    status=TaskStatus.RUNNING,
                    progress=0.2,
                    message="Agent 已开始基于证据生成教学分析。",
                    trace_id=claim.trace_id,
                ),
            )
            result = await orchestrator.analyze(_analysis_input(claim))
            monitor.ensure_lease()
            store.save_conclusions(claim.task_id, result.conclusions)
            monitor.ensure_lease()
            store.update_state(
                claim.task_id,
                InternalTaskStateUpdate(
                    stage=TaskStage.ANALYZE,
                    status=TaskStatus.SUCCEEDED,
                    progress=1.0,
                    message="教学分析已生成，等待教师逐条复核。",
                    trace_id=result.trace_id,
                ),
            )
        return claim
    except Exception as exc:
        error_code, message = _public_failure(exc)
        try:
            store.update_state(
                claim.task_id,
                InternalTaskStateUpdate(
                    stage=TaskStage.ANALYZE,
                    status=TaskStatus.FAILED,
                    progress=0.0,
                    message=message,
                    error_code=error_code,
                    trace_id=claim.trace_id,
                ),
            )
        except AgentJobStoreError:
            pass
        raise


def build_provider_router_from_env() -> ProviderRouter:
    local_endpoint = os.getenv("LOCAL_MODEL_CHAT_COMPLETIONS_URL", "").strip()
    local_model = os.getenv("LOCAL_MODEL_NAME", "").strip()
    # 本地结构化分析默认关闭隐藏推理；否则小显存设备可能在生成最终 JSON 前
    # 已耗尽上下文。需要推理模式的其他本地模型仍可通过环境变量显式覆盖。
    local_reasoning_effort = (
        os.getenv("LOCAL_MODEL_REASONING_EFFORT", "none").strip() or "none"
    )
    cloud_endpoint = os.getenv("CLOUD_MODEL_CHAT_COMPLETIONS_URL", "").strip()
    cloud_model = os.getenv("CLOUD_MODEL_NAME", "").strip()
    cloud_key = os.getenv("CLOUD_MODEL_API_KEY", "").strip()
    local = (
        LocalModelProvider(
            endpoint=local_endpoint,
            model=local_model,
            reasoning_effort=local_reasoning_effort,
        )
        if local_endpoint and local_model
        else None
    )
    cloud = (
        CloudModelProvider(
            endpoint=cloud_endpoint,
            model=cloud_model,
            api_key=cloud_key,
        )
        if cloud_endpoint and cloud_model and cloud_key
        else None
    )
    return ProviderRouter(local=local, cloud=cloud)


def build_trace_sink_from_env() -> JsonlTraceSink:
    path = os.getenv("AGENT_TRACE_PATH", "logs/agent-traces.jsonl").strip()
    if not path:
        raise ValueError("AGENT_TRACE_PATH 不能为空。")
    return JsonlTraceSink(Path(path))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行一次课堂复盘 Agent 任务。")
    parser.add_argument(
        "--backend-url",
        default=os.getenv("BACKEND_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--agent-id",
        default=os.getenv("AGENT_RUNNER_ID", "agent-local-1"),
    )
    parser.add_argument(
        "--lease-seconds",
        type=int,
        default=int(os.getenv("AGENT_LEASE_SECONDS", "300")),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    token = os.getenv("AGENT_SERVICE_TOKEN", "").strip()
    store = HttpAgentJobStore(args.backend_url, token)
    try:
        claim = asyncio.run(
            run_claimed_once(
                store,
                AgentOrchestrator(
                    providers=build_provider_router_from_env(),
                    skill_registry=load_domain_skills(),
                    conclusion_validator=load_conclusion_validator(),
                    trace_sink=build_trace_sink_from_env(),
                ),
                InternalAgentClaimRequest(
                    agent_id=args.agent_id,
                    lease_seconds=args.lease_seconds,
                ),
            )
        )
    finally:
        store.close()
    if claim is None:
        print("当前没有等待分析的任务。")
    else:
        print(f"Agent 已完成任务 {claim.task_id}，结论等待教师复核。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
