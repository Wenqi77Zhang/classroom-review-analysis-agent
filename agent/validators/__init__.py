"""成员 4 证据校验器的 Agent 集成包；专业校验缺失时不伪造实现。"""

from __future__ import annotations

from collections.abc import Callable

from agent.validators import evidence_gate
from backend.app.schemas.analysis_report import InternalConclusionWrite

ConclusionValidator = Callable[[InternalConclusionWrite], None]


def load_conclusion_validator() -> ConclusionValidator | None:
    validator = getattr(evidence_gate, "validate_conclusion", None)
    if validator is None:
        return None
    if not isinstance(validator, Callable):
        raise TypeError("validate_conclusion 必须是可调用对象。")
    return validator


__all__ = ["load_conclusion_validator"]
