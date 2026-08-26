"""Provision and verify the non-sensitive object-storage readiness sentinel."""

from __future__ import annotations

import asyncio
import sys

from backend.app.config import get_settings
from backend.app.errors import AppError
from backend.app.services.storage import READINESS_OBJECT_KEY, S3ObjectStorage


async def main() -> None:
    storage = S3ObjectStorage(get_settings())
    # Overwriting this fixed two-byte, non-sensitive object is idempotent and
    # works with restricted keys that intentionally hide missing-object status.
    await storage.put(READINESS_OBJECT_KEY, b"ok", "text/plain")
    await storage.ready()
    print("OBJECT_STORAGE_READINESS_OK")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AppError:
        print("OBJECT_STORAGE_READINESS_UNAVAILABLE", file=sys.stderr)
        raise SystemExit(1) from None
