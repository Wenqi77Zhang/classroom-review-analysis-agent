"""脱敏 Agent Trace；后续可由成员 3 的 audit 服务提供持久化 Sink。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

_SENSITIVE_PARTS = ("authorization", "cookie", "password", "secret", "token", "api_key")
_SENSITIVE_CONTENT_KEYS = {
    "content",
    "evidence_text",
    "prompt",
    "quote",
    "raw_input",
    "raw_response",
    "system_prompt",
    "transcript",
    "translation",
    "user_prompt",
}


def new_trace_id() -> str:
    return uuid4().hex


def _sanitize(value: Any, *, key: str = "") -> Any:
    normalized_key = key.casefold()
    if normalized_key in _SENSITIVE_CONTENT_KEYS or any(
        part in normalized_key for part in _SENSITIVE_PARTS
    ):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {
            str(item_key): _sanitize(item, key=str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, key=key) for item in value]
    if isinstance(value, str) and len(value) > 2000:
        return value[:2000] + "…[TRUNCATED]"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)[:2000]


@dataclass(frozen=True, slots=True)
class TraceEvent:
    trace_id: str
    name: str
    occurred_at: datetime
    attributes: dict[str, Any] = field(default_factory=dict)


class TraceSink(Protocol):
    def record(self, event: TraceEvent) -> None: ...


class InMemoryTraceSink:
    """进程内实现用于单元测试和本地运行；不能描述为持久化审计。"""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def record(self, event: TraceEvent) -> None:
        self.events.append(event)


class JsonlTraceSink:
    """Append-only persistent trace sink containing only sanitized structured fields."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def record(self, event: TraceEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "trace_id": event.trace_id,
            "name": event.name,
            "occurred_at": event.occurred_at.isoformat(),
            "attributes": _sanitize(event.attributes),
        }
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        descriptor = os.open(
            self.path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        try:
            os.write(descriptor, line.encode("utf-8"))
        finally:
            os.close(descriptor)


class Tracer:
    def __init__(self, sink: TraceSink, trace_id: str | None = None) -> None:
        self.trace_id = trace_id or new_trace_id()
        self._sink = sink

    def event(self, name: str, **attributes: Any) -> None:
        self._sink.record(
            TraceEvent(
                trace_id=self.trace_id,
                name=name,
                occurred_at=datetime.now(UTC),
                attributes=_sanitize(attributes),
            )
        )

    def error(self, error: BaseException, *, stage: str, error_code: str) -> None:
        """只记录稳定分类，不记录可能包含输入值的异常消息。"""

        self.event(
            "agent.error",
            stage=stage,
            error_type=type(error).__name__,
            error_code=error_code,
        )
