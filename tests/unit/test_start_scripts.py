"""成员 5：统一启动入口的静态安全与服务覆盖检查。"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_windows_start_entry_covers_all_services_without_cli_secrets() -> None:
    script = (ROOT / "start.ps1").read_text(encoding="utf-8")

    assert "TODO(成员 5)" not in script
    assert '"--factory", "backend.app.main:create_app"' in script
    assert '"frontend"' in script
    assert '"worker"' in script
    assert '"agent"' in script
    assert "--service-token" not in script
    assert "-WindowStyle Hidden" in script


def test_unix_start_entry_covers_all_services_and_cleans_up() -> None:
    script = (ROOT / "start.sh").read_text(encoding="utf-8")

    assert "TODO(成员 5)" not in script
    assert "backend.app.main:create_app" in script
    assert "npm run dev" in script
    assert "scripts/run_service_loop.py worker" in script
    assert "scripts/run_service_loop.py agent" in script
    assert "trap cleanup EXIT INT TERM" in script


def test_service_loop_reads_tokens_only_from_environment_and_forwards_stop() -> None:
    script = (ROOT / "scripts" / "run_service_loop.py").read_text(encoding="utf-8")

    assert "--service-token" not in script
    assert "worker.runner" in script
    assert "agent.runner" in script
    assert "signal.SIGTERM" in script
    assert "current.terminate()" in script
