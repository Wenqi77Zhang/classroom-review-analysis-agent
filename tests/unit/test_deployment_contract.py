from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_production_compose_exposes_only_frontend() -> None:
    payload = yaml.safe_load((ROOT / "deploy/compose.production.yml").read_text(encoding="utf-8"))
    services = payload["services"]
    assert "ports" in services["frontend"]
    for name in ("postgres", "backend", "worker", "agent"):
        assert "ports" not in services[name], f"{name} must remain private"
    assert payload["networks"]["private"]["internal"] is True


def test_production_services_have_health_or_supervision() -> None:
    payload = yaml.safe_load((ROOT / "deploy/compose.production.yml").read_text(encoding="utf-8"))
    services = payload["services"]
    for name in ("postgres", "backend", "frontend"):
        assert "healthcheck" in services[name]
    for name in ("backend", "worker", "agent", "frontend", "postgres", "cloudflared"):
        assert services[name]["restart"] == "unless-stopped"


def test_named_tunnel_keeps_token_out_of_process_arguments() -> None:
    payload = yaml.safe_load((ROOT / "deploy/compose.production.yml").read_text(encoding="utf-8"))
    frontend_port = payload["services"]["frontend"]["ports"][0]
    tunnel = payload["services"]["cloudflared"]
    assert frontend_port.startswith("127.0.0.1:")
    assert tunnel["profiles"] == ["tunnel"]
    assert "token" not in " ".join(tunnel["command"]).lower()
    assert "TUNNEL_TOKEN" in tunnel["environment"]


def test_worker_has_isolated_cpu_media_image() -> None:
    payload = yaml.safe_load((ROOT / "deploy/compose.production.yml").read_text(encoding="utf-8"))
    services = payload["services"]
    assert services["backend"]["build"]["target"] == "runtime"
    assert services["agent"]["build"]["target"] == "runtime"
    assert services["worker"]["build"]["target"] == "worker"
    dockerfile = (ROOT / "deploy/Dockerfile.python").read_text(encoding="utf-8")
    assert "download.pytorch.org/whl/cpu" in dockerfile


def test_committed_deployment_files_contain_no_secret_values() -> None:
    compose = (ROOT / "deploy/compose.production.yml").read_text(encoding="utf-8")
    example = (ROOT / "deploy/.env.production.example").read_text(encoding="utf-8")
    assert "env_file" in compose
    assert "replace-with" in example
    assert "gho_" not in compose + example
    assert "sk-" not in compose + example


def test_storage_readiness_sentinel_is_provisioned_before_serving() -> None:
    compose = (ROOT / "deploy/compose.production.yml").read_text(encoding="utf-8")
    start_windows = (ROOT / "start.ps1").read_text(encoding="utf-8")
    start_posix = (ROOT / "start.sh").read_text(encoding="utf-8")
    provisioner = (ROOT / "scripts/ensure_storage_readiness.py").read_text(encoding="utf-8")

    assert compose.index("scripts/ensure_storage_readiness.py") < compose.index("uvicorn")
    assert "scripts/ensure_storage_readiness.py" in start_windows
    assert "scripts/ensure_storage_readiness.py" in start_posix
    assert "READINESS_OBJECT_KEY" in provisioner
    assert 'b"ok"' in provisioner
    assert "OBJECT_STORAGE_SECRET_ACCESS_KEY" not in provisioner
