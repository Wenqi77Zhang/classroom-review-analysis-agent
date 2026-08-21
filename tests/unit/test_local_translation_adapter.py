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


def _single_model_response(translation: str) -> bytes:
    return json.dumps(
        {
            "model": "qwen3.5:4b",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"translation": translation},
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


def test_local_translation_recovers_omitted_rows_by_splitting_failed_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_sizes: list[int] = []

    def omit_large_batch(request: Request, *, timeout: float) -> _Response:
        assert timeout == 30
        payload = json.loads(request.data or b"{}")
        source_items = json.loads(payload["messages"][1]["content"])["items"]
        requested_sizes.append(len(source_items))
        response_items = [
            {"id": item["id"], "text": f"译文{item['id']}"}
            for item in source_items
        ]
        if len(source_items) == 6:
            response_items = response_items[:4]
        return _Response(_model_response(response_items))

    monkeypatch.setattr("worker.adapters.local_translation._open_local", omit_large_batch)
    adapter = LocalModelTranslationAdapter(
        endpoint="http://127.0.0.1:11434/v1/chat/completions",
        model="qwen3.5:4b",
        timeout_seconds=30,
        batch_size=8,
    )

    result = adapter.translate_batch(
        tuple(f"segment-{index}" for index in range(6)),
        source_language="en",
        target_language="zh",
    )

    assert result.translations == (
        "译文0",
        "译文1",
        "译文2",
        "译文0",
        "译文1",
        "译文2",
    )
    assert requested_sizes == [6, 3, 3]


def test_local_translation_does_not_retry_non_schema_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def unavailable(*_args: object, **_kwargs: object) -> None:
        nonlocal call_count
        call_count += 1
        raise URLError("local model offline")

    monkeypatch.setattr("worker.adapters.local_translation._open_local", unavailable)
    adapter = LocalModelTranslationAdapter(
        endpoint="http://127.0.0.1:11434/v1/chat/completions",
        model="qwen3.5:4b",
    )

    with pytest.raises(WorkerError) as raised:
        adapter.translate_batch(
            ("first", "second"),
            source_language="en",
            target_language="zh",
        )

    assert raised.value.code is WorkerErrorCode.TRANSLATION_UNAVAILABLE
    assert call_count == 1


def test_local_translation_retries_malformed_singleton_with_strict_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    def malformed_then_valid(*_args: object, **_kwargs: object) -> _Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _Response(_model_response([]))
        return _Response(_model_response([{"id": 0, "text": "有效译文"}]))

    monkeypatch.setattr(
        "worker.adapters.local_translation._open_local",
        malformed_then_valid,
    )
    adapter = LocalModelTranslationAdapter(
        endpoint="http://127.0.0.1:11434/v1/chat/completions",
        model="qwen3.5:4b",
    )

    result = adapter.translate_batch(
        ("one segment",),
        source_language="en",
        target_language="zh",
    )

    assert result.translations == ("有效译文",)
    assert call_count == 2


def test_local_translation_splits_long_singleton_after_bounded_schema_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_lengths: list[int] = []

    def reject_long_source(request: Request, **_kwargs: object) -> _Response:
        payload = json.loads(request.data or b"{}")
        user_data = json.loads(payload["messages"][1]["content"])
        if "items" in user_data:
            source = user_data["items"][0]["text"]
            requested_lengths.append(len(source))
            items = [] if len(source) > 300 else [{"id": 0, "text": "分段译文"}]
            return _Response(_model_response(items))
        source = user_data["data"]["text"]
        requested_lengths.append(len(source))
        translation = "" if len(source) > 300 else "分段译文"
        return _Response(_single_model_response(translation))

    monkeypatch.setattr(
        "worker.adapters.local_translation._open_local",
        reject_long_source,
    )
    adapter = LocalModelTranslationAdapter(
        endpoint="http://127.0.0.1:11434/v1/chat/completions",
        model="qwen3.5:4b",
    )

    result = adapter.translate_batch(
        (("classroom evidence " * 27).strip(),),
        source_language="en",
        target_language="zh",
    )

    assert result.translations == ("分段译文 分段译文",)
    assert requested_lengths[:4] == [512, 512, 512, 512]
    assert len(requested_lengths) == 6
    assert max(requested_lengths[4:]) <= 300


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
