"""Cleanup helpers for worker-owned temporary files."""

from __future__ import annotations

import shutil
from pathlib import Path

from worker.errors import WorkerError, WorkerErrorCode


def cleanup_path(path: Path) -> None:
    """Remove a worker-owned file/directory; missing paths are already clean."""
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    except OSError as exc:
        raise WorkerError(
            WorkerErrorCode.CLEANUP_FAILED,
            f"临时媒体清理失败：{path.name}",
            retryable=True,
        ) from exc
