"""Fail-closed validation for the unified runtime without printing secret values."""

from __future__ import annotations

import os

from agent.runner import build_provider_router_from_env, build_trace_sink_from_env
from backend.app.config import Settings
from backend.app.schemas.task import PrivacyMode


def main() -> int:
    Settings()  # type: ignore[call-arg]
    privacy_mode = PrivacyMode(os.getenv("MODEL_PRIVACY_MODE", "local").strip())
    build_provider_router_from_env().select(privacy_mode)
    build_trace_sink_from_env()
    print("运行配置校验通过（敏感值未输出）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
