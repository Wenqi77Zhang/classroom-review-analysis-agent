"""成员 5：统一启动守护入口的安全命令构造。"""

from __future__ import annotations

import sys

import pytest

from scripts.run_service_loop import service_command


def test_worker_loop_reuses_existing_cli_without_service_token(monkeypatch) -> None:
    monkeypatch.setenv("BACKEND_URL", "http://127.0.0.1:8000/")
    monkeypatch.setenv("WORKER_SERVICE_TOKEN", "must-not-enter-argv")

    command = service_command("worker")

    assert command == [
        sys.executable,
        "-m",
        "worker.runner",
        "--api-base-url",
        "http://127.0.0.1:8000",
    ]
    assert "must-not-enter-argv" not in command


def test_agent_loop_reuses_existing_cli_without_service_token(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_SERVICE_TOKEN", "must-not-enter-argv")

    command = service_command("agent")

    assert command[:3] == [sys.executable, "-m", "agent.runner"]
    assert "must-not-enter-argv" not in command


def test_unknown_loop_service_is_rejected() -> None:
    with pytest.raises(ValueError, match="未知服务"):
        service_command("browser")
