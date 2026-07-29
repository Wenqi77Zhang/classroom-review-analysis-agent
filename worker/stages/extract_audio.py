"""Extract speech-ready WAV audio from a real video with FFmpeg."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from worker.errors import WorkerError, WorkerErrorCode


def extract_audio(
    input_path: Path,
    output_path: Path,
    *,
    timeout_seconds: int = 600,
    ffmpeg_binary: str = "ffmpeg",
) -> Path:
    if not input_path.is_file():
        raise WorkerError(WorkerErrorCode.INPUT_NOT_FOUND, "输入视频不存在。")
    if shutil.which(ffmpeg_binary) is None:
        raise WorkerError(
            WorkerErrorCode.FFMPEG_NOT_FOUND,
            "未找到 FFmpeg，请先安装并确保它在 PATH 中。",
            retryable=True,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg_binary,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output_path.unlink(missing_ok=True)
        raise WorkerError(
            WorkerErrorCode.AUDIO_EXTRACTION_TIMEOUT,
            f"FFmpeg 音频抽取超过 {timeout_seconds} 秒。",
            retryable=True,
        ) from exc

    if completed.returncode != 0:
        output_path.unlink(missing_ok=True)
        # FFmpeg stderr can include full local paths, object keys and tenant
        # identifiers. It must not enter an exception persisted as TaskEvent.
        raise WorkerError(
            WorkerErrorCode.AUDIO_EXTRACTION_FAILED,
            f"音频抽取失败（FFmpeg 退出码 {completed.returncode}）。",
        )
    if not output_path.is_file() or output_path.stat().st_size <= 44:
        output_path.unlink(missing_ok=True)
        raise WorkerError(
            WorkerErrorCode.AUDIO_EXTRACTION_FAILED,
            "视频没有产生有效音频。",
        )
    return output_path
