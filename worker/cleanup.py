"""Cleanup helpers for worker-owned temporary files."""

from __future__ import annotations

import shutil
from pathlib import Path


def cleanup_path(path: Path) -> None:
    """Remove a worker-owned file/directory; missing paths are already clean."""
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)
