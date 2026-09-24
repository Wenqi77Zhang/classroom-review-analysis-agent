import sys

from scripts import configure_production_cors


def _values(*, use_path_style: str = "") -> dict[str, str]:
    return {
        "OBJECT_STORAGE_ENDPOINT": "http://minio:9000",
        "OBJECT_STORAGE_REGION": "us-east-1",
        "OBJECT_STORAGE_BUCKET": "classroom-review",
        "OBJECT_STORAGE_ACCESS_KEY_ID": "access-key",
        "OBJECT_STORAGE_SECRET_ACCESS_KEY": "secret-key",
        "OBJECT_STORAGE_USE_PATH_STYLE": use_path_style,
    }


def test_create_client_uses_path_style_for_private_minio(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_client(*args, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(configure_production_cors.boto3, "client", fake_client)

    configure_production_cors.create_client(_values(use_path_style="true"))

    assert captured["config"].s3["addressing_style"] == "path"


def test_create_client_keeps_virtual_style_by_default(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_client(*args, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(configure_production_cors.boto3, "client", fake_client)

    configure_production_cors.create_client(_values())

    assert captured["config"].s3["addressing_style"] == "virtual"


def test_verify_uses_preflight_without_reading_bucket_cors(monkeypatch) -> None:
    client = object()
    observed: dict[str, object] = {}
    monkeypatch.setattr(
        configure_production_cors,
        "load_values",
        lambda _path: _values(use_path_style="true"),
    )
    monkeypatch.setattr(configure_production_cors, "create_client", lambda _values: client)
    monkeypatch.setattr(
        configure_production_cors,
        "verify_preflight",
        lambda actual_client, bucket, origin: observed.update(
            client=actual_client,
            bucket=bucket,
            origin=origin,
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["configure_production_cors.py", "verify", "--origin", "https://example.com"],
    )

    configure_production_cors.main()

    assert observed == {
        "client": client,
        "bucket": "classroom-review",
        "origin": "https://example.com",
    }
