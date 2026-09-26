from __future__ import annotations

import tomllib
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


def test_production_preflight_runs_as_a_module() -> None:
    compose = (ROOT / "deploy/compose.production.yml").read_text(encoding="utf-8")

    assert "python -m scripts.production_preflight" in compose
    assert "python scripts/production_preflight.py" not in compose


def test_runtime_preflight_does_not_import_worker_runtime() -> None:
    source = (ROOT / "scripts" / "runtime_preflight.py").read_text(encoding="utf-8")

    assert "from worker.runner" not in source
    assert "from worker.adapters.translation_factory" in source


def test_runtime_http_client_is_a_core_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert any(dependency.startswith("httpx") for dependency in project["dependencies"])


def test_database_backup_and_restore_are_private_and_guarded() -> None:
    backup = (ROOT / "deploy/backup-database.sh").read_text(encoding="utf-8")
    restore = (ROOT / "deploy/restore-database.sh").read_text(encoding="utf-8")
    verify_restore = (ROOT / "deploy/verify-database-restore.sh").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "umask 077" in backup
    assert "pg_dump" in backup and "--format=custom" in backup
    assert "partial.$$" in backup and 'mv "$TEMP_TARGET" "$TARGET"' in backup
    assert "deploy/backups/" in gitignore
    assert "CONFIRM_DATABASE_RESTORE" in restore
    assert "--clean --if-exists" in restore and "--exit-on-error" in restore
    stop_index = restore.index("stop frontend backend worker agent")
    assert restore.index("pg_restore --list") < stop_index
    assert stop_index < restore.index("pg_restore --username", stop_index)
    assert "mktemp -d" in verify_restore
    assert "docker run -d --rm" in verify_restore
    assert "postgres:17-alpine" in verify_restore
    assert "diff -u" in verify_restore
    assert "trap cleanup" in verify_restore
    assert 'rm -rf "$WORK_DIR"' in verify_restore
    assert "stop frontend backend worker agent" not in verify_restore
    assert "--clean --if-exists" not in verify_restore
    assert "RESTORE_DRILL=PASS" in verify_restore


def test_object_storage_restore_drill_is_isolated_and_self_cleaning() -> None:
    verify_restore = (
        ROOT / "deploy/verify-object-storage-restore.sh"
    ).read_text(encoding="utf-8")

    assert "umask 077" in verify_restore
    assert "mktemp -d" in verify_restore
    assert "mc mirror" in verify_restore
    assert "tar -C" in verify_restore
    assert "docker network create" in verify_restore
    assert "docker run -d --rm" in verify_restore
    assert '--user "$(id -u):$(id -g)"' in verify_restore
    assert "diff -u" in verify_restore
    assert "trap cleanup" in verify_restore
    assert 'rm -rf "$WORK_DIR"' in verify_restore
    assert "mc rm" not in verify_restore
    assert "OBJECT_STORAGE_RESTORE_DRILL=PASS" in verify_restore


def test_offsite_backup_is_encrypted_atomic_and_self_cleaning() -> None:
    backup = (ROOT / "deploy/backup-offsite-s3.sh").read_text(encoding="utf-8")
    verify = (ROOT / "deploy/verify-offsite-s3-restore.sh").read_text(encoding="utf-8")

    assert "umask 077" in backup and "umask 077" in verify
    assert "mktemp -d" in backup and "mktemp -d" in verify
    assert "trap cleanup" in backup and "trap cleanup" in verify
    assert '--sse AES256' in backup
    assert backup.index('backup.sha256') < backup.index('REMOTE_PREFIX/COMPLETE')
    assert "mc mirror" in backup and "mc rm" not in backup
    assert "sha256sum -c backup.sha256" in verify
    assert "sha256sum -c \"$WORK_DIR/objects.sha256\"" in verify
    assert "docker run -d --rm" in verify
    assert "--no-owner --exit-on-error" in verify
    assert "OFFSITE_BACKUP=PASS" in backup
    assert "OFFSITE_RESTORE_DRILL=PASS" in verify
    assert "stop frontend backend worker agent" not in verify


def test_aws_stack_provisions_least_privilege_offsite_backup() -> None:
    template = (ROOT / "deploy/cloudformation.aws.yml").read_text(encoding="utf-8")
    timer = (ROOT / "deploy/install-offsite-backup-timer.sh").read_text(encoding="utf-8")

    assert "OffsiteBackupBucket:" in template
    assert "DeletionPolicy: Retain" in template
    assert "UpdateReplacePolicy: Retain" in template
    assert "SSEAlgorithm: AES256" in template
    assert "VersioningConfiguration:" in template and "Status: Enabled" in template
    for setting in ("BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls", "RestrictPublicBuckets"):
        assert f"{setting}: true" in template
    assert "s3:GetObject" in template and "s3:PutObject" in template
    assert "s3:DeleteObject" not in template
    assert "classroom-review-agent/*" in template
    assert "OnCalendar=*-*-* 03:20:00 UTC" in timer
    assert "OnCalendar=Sun *-*-* 04:20:00 UTC" in timer
    assert "Persistent=true" in timer
    assert "NoNewPrivileges=true" in timer


def test_production_example_defaults_to_formal_accounts() -> None:
    example = (ROOT / "deploy/.env.production.example").read_text(encoding="utf-8")
    assert "# DEMO_ACCOUNT_PASSWORD=" in example
    assert "# TEAM_TUNNEL_ACCESS_CODE=" in example
