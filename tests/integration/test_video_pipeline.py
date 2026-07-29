"""Opt-in real-video validation; course videos and transcripts stay local."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.app.schemas.task import TaskStatus
from worker.adapters.asr import LocalWhisperAdapter
from worker.job_store import LocalJobStore
from worker.pipeline import run_pipeline
from worker.types import PipelineTask


@pytest.mark.skipif(
    not os.getenv("CLASSROOM_TEST_VIDEOS"),
    reason="set CLASSROOM_TEST_VIDEOS to two local MP4 paths separated by os.pathsep",
)
def test_two_real_videos_produce_distinct_timestamped_transcripts() -> None:
    paths = [Path(value) for value in os.environ["CLASSROOM_TEST_VIDEOS"].split(os.pathsep)]
    assert len(paths) == 2
    texts: list[str] = []
    for path in paths:
        store = LocalJobStore()
        task = PipelineTask(input_path=path)
        result = run_pipeline(task, LocalWhisperAdapter(os.getenv("WHISPER_MODEL", "tiny")), store)
        transcript = store.transcripts[task.task_id]
        assert result.transcript_segments > 0
        assert all(segment.end_ms > segment.start_ms for segment in transcript.segments)
        assert all(
            current.start_ms >= previous.end_ms
            for previous, current in zip(
                transcript.segments,
                transcript.segments[1:],
                strict=False,
            )
        )
        assert transcript.segments[-1].end_ms <= transcript.duration_ms
        assert store.events[task.task_id][-1].status is TaskStatus.RUNNING
        texts.append(" ".join(segment.text for segment in transcript.segments))
    assert texts[0] != texts[1]
