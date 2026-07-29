"""Local one-shot entry point for validating a real video."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from worker.adapters.asr import LocalWhisperAdapter
from worker.job_store import LocalJobStore
from worker.pipeline import run_pipeline
from worker.types import PipelineTask


def main() -> int:
    parser = argparse.ArgumentParser(description="从真实课堂视频生成带时间戳逐字稿")
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=os.getenv("WHISPER_MODEL", "tiny"))
    parser.add_argument("--language", default=None)
    args = parser.parse_args()

    store = LocalJobStore()
    task = PipelineTask(input_path=args.video)
    result = run_pipeline(
        task,
        LocalWhisperAdapter(args.model, language=args.language),
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
