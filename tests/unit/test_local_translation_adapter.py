from __future__ import annotations

import json
from io import BytesIO
from typing import Self
from urllib.error import URLError
from urllib.request import Request

import pytest

from worker.adapters.local_translation import LocalModelTranslationAdapter
from worker.errors import WorkerError, WorkerErrorCode
from worker.runner import build_translation_adapter_from_env


class _Response(BytesIO):
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _model_response(items: list[dict[str, object]]) -> bytes:
    return json.dumps(
        {
            "model": "qwen3.5:4b",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"translations": items},
                            ensure_ascii=False,
                        )
                    }
                }
            ],
        },
        ensure_ascii=False,
    ).encode()


def test_local_translation_is_loopback_only() -> None:
    with pytest.raises(ValueError, match="loopback"):
        LocalModelTranslationAdapter(
            endpoint="https://models.example/v1/chat/completions",
            model="qwen",
        )


def test_local_translation_chunks_and_restores_id_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, object]] = []

    def fake_urlopen(request: Request, *, timeout: float) -> _Response:
        assert timeout == 30
        payload = json.loads(request.data or b"{}")
        requests.append(payload)
        source_items = json.loads(payload["messages"][1]["content"])["items"]
        response_items = [
            {"id": item["id"], "text": f"译文{item['id']}"}
            for item in reversed(source_items)
        ]
        return _Response(_model_response(response_items))

    monkeypatch.setattr("worker.adapters.local_translation._open_local", fake_urlopen)
    adapter = LocalModelTranslationAdapter(
        endpoint="http://127.0.0.1:11434/v1/chat/completions",
        model="qwen3.5:4b",
        timeout_seconds=30,
        batch_size=2,
    )

    result = adapter.translate_batch(
        ("first", "second", "third"),
        source_language="en",
        target_language="zh",
    )

    assert result.translations == ("译文0", "译文1", "译文0")
    assert len(requests) == 2
    assert all(request["temperature"] == 0 for request in requests)
    assert all(request["reasoning_effort"] == "none" for request in requests)
    assert "Authorization" not in str(requests)


@pytest.mark.parametrize(
    "items",
    [
        [{"id": 0, "text": "译文"}, {"id": 0, "text": "重复"}],
        [{"id": 1, "text": "缺少零号"}],
        [{"id": 0, "text": ""}],
    ],
)
def test_local_translation_rejects_misaligned_model_output(
    monkeypatch: pytest.MonkeyPatch,
    items: list[dict[str, object]],
) -> None:
    monkeypatch.setattr(
        "worker.adapters.local_translation._open_local",
        lambda *_args, **_kwargs: _Response(_model_response(items)),
    )
    adapter = LocalModelTranslationAdapter(
        endpoint="http://localhost:11434/v1/chat/completions",
        model="qwen",
    )

    with pytest.raises(WorkerError) as raised:
        adapter.translate_batch(("private lesson",), source_language="en", target_language="zh")

    assert raised.value.code is WorkerErrorCode.TRANSLATION_SCHEMA_INVALID
    assert "private lesson" not in str(raised.value)


def test_local_translation_hides_source_on_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise URLError("private upstream diagnostic")

    monkeypatch.setattr("worker.adapters.local_translation._open_local", fail)
    adapter = LocalModelTranslationAdapter(
        endpoint="http://127.0.0.1:11434/v1/chat/completions",
        model="qwen",
    )

    with pytest.raises(WorkerError) as raised:
        adapter.translate_batch(("secret lesson text",), source_language="en", target_language="zh")

    assert raised.value.code is WorkerErrorCode.TRANSLATION_UNAVAILABLE
    assert raised.value.retryable is True
    assert "secret lesson text" not in str(raised.value)
    assert "private upstream diagnostic" not in str(raised.value)


def test_translation_builder_inherits_local_agent_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRANSLATION_PROVIDER", "local_model")
    monkeypatch.setenv(
        "LOCAL_MODEL_CHAT_COMPLETIONS_URL",
        "http://127.0.0.1:11434/v1/chat/completions",
    )
    monkeypatch.setenv("LOCAL_MODEL_NAME", "qwen-test")
    monkeypatch.delenv("TRANSLATION_MODEL_CHAT_COMPLETIONS_URL", raising=False)
    monkeypatch.delenv("TRANSLATION_MODEL_NAME", raising=False)

    adapter = build_translation_adapter_from_env()

    assert adapter is not None
    assert adapter.model_name == "qwen-test"


def test_translation_builder_can_be_explicitly_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRANSLATION_PROVIDER", "disabled")

    assert build_translation_adapter_from_env() is None


def test_local_translation_rejects_oversized_source_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def should_not_open(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("worker.adapters.local_translation._open_local", should_not_open)
    adapter = LocalModelTranslationAdapter(
        endpoint="http://127.0.0.1:11434/v1/chat/completions",
        model="qwen",
    )

    with pytest.raises(WorkerError) as raised:
        adapter.translate_batch(("a" * 20_001,), source_language="en", target_language="zh")

    assert raised.value.code is WorkerErrorCode.TRANSLATION_SCHEMA_INVALID
    assert called is False
