"""Bounded, deterministic skill for proposing two-round evidence comparisons.

The skill deliberately returns a candidate rather than a teaching-effect verdict.  The
backend still enforces evidence, ownership and teacher-review gates.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

SKILL_NAME = "evidence-comparison"
PROMPT_VERSION = "comparison-v1"


@dataclass(frozen=True, slots=True)
class ComparisonCandidate:
    key: str
    content: str
    created_at: datetime


def _terms(text: str) -> Counter[str]:
    lowered = text.lower()
    latin = re.findall(r"[a-z0-9]{2,}", lowered)
    han = re.findall(r"[\u4e00-\u9fff]", lowered)
    return Counter(latin + ["".join(han[index : index + 2]) for index in range(len(han) - 1)])


def select_related_candidate(
    action_text: str,
    success_criterion: str,
    candidates: Sequence[ComparisonCandidate],
) -> str | None:
    """Return the best overlapping candidate key, or None when evidence is insufficient."""

    target = _terms(f"{action_text}{success_criterion}")
    if not target:
        return None
    scored = [
        (sum((target & _terms(item.content)).values()), item.created_at, item.key)
        for item in candidates
    ]
    best = max(scored, default=None, key=lambda row: (row[0], row[1]))
    return best[2] if best is not None and best[0] > 0 else None


def propose_outcome(content: str) -> Literal["improved", "unchanged", "regressed"]:
    """Propose a conservative lexical outcome label; never claim causality."""

    if any(term in content for term in ("下降", "减少", "退步", "恶化", "不足")):
        return "regressed"
    if any(term in content for term in ("提升", "增加", "改善", "更充分", "更清晰", "延长")):
        return "improved"
    return "unchanged"
