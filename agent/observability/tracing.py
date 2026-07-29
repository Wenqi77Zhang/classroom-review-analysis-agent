"""脱敏 Agent Trace；后续可由成员 3 的 audit 服务提供持久化 Sink。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

_SENSITIVE_PARTS = ("authorization", "cookie", "password", "secret", "token", "api_key")


def new_trace_id() -> str:
    return uuid4().hex


def _sanitize(value: Any, *, key: str = "") -> Any:
    if any(part in key.casefold() for part in _SENSITIVE_PARTS):
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

    def error(self, error: BaseException, *, stage: str) -> None:
        self.event(
            "agent.error",
            stage=stage,
            error_type=type(error).__name__,
            error_message=str(error),
        )
