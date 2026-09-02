"""Fail closed before exposing the application through a public endpoint."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from scripts.runtime_preflight import main as runtime_preflight

PLACEHOLDER_MARKERS = ("replace-with", "change-me", "changeme", "example.edu")


def _require(name: str, *, minimum: int = 1) -> str:
    value = os.getenv(name, "").strip()
    if len(value) < minimum:
        raise ValueError(f"生产配置缺少或过短：{name}")
    if any(marker in value.lower() for marker in PLACEHOLDER_MARKERS):
        raise ValueError(f"生产配置仍为示例占位值：{name}")
    return value


def _optional(name: str, *, minimum: int) -> str | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    return _require(name, minimum=minimum)


def main() -> int:
    if os.getenv("APP_ENV", "").strip() != "production":
        raise ValueError("公网部署必须设置 APP_ENV=production。")
    origin = urlparse(_require("FRONTEND_ORIGIN"))
    if origin.scheme != "https" or not origin.netloc:
        raise ValueError("公网部署 FRONTEND_ORIGIN 必须是完整 HTTPS 地址。")
    _optional("TEAM_TUNNEL_ACCESS_CODE", minimum=16)
    _optional("DEMO_ACCOUNT_PASSWORD", minimum=16)
    _require("DATABASE_URL", minimum=16)
    _require("JWT_SECRET", minimum=32)
    _require("OBJECT_STORAGE_ENDPOINT", minimum=8)
    _require("OBJECT_STORAGE_BUCKET", minimum=3)
    _require("OBJECT_STORAGE_ACCESS_KEY_ID", minimum=6)
    _require("OBJECT_STORAGE_SECRET_ACCESS_KEY", minimum=12)
    if _require("WORKER_SERVICE_TOKEN", minimum=16) == _require(
        "AGENT_SERVICE_TOKEN", minimum=16
    ):
        raise ValueError("Worker 与 Agent 服务令牌必须不同。")
    tunnel_token = os.getenv("CLOUDFLARE_TUNNEL_TOKEN", "").strip()
    if tunnel_token:
        _require("CLOUDFLARE_TUNNEL_TOKEN", minimum=16)

    privacy_mode = os.getenv("MODEL_PRIVACY_MODE", "local").strip()
    if privacy_mode == "cloud":
        _require("CLOUD_MODEL_CHAT_COMPLETIONS_URL", minimum=8)
        _require("CLOUD_MODEL_NAME", minimum=2)
        _require("CLOUD_MODEL_API_KEY", minimum=8)
    elif privacy_mode == "local":
        _require("LOCAL_MODEL_CHAT_COMPLETIONS_URL", minimum=8)
        _require("LOCAL_MODEL_NAME", minimum=2)
    runtime_preflight()
    print("生产部署预检通过（敏感值未输出）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
