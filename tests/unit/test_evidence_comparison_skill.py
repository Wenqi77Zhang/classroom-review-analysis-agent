from datetime import UTC, datetime, timedelta

from agent.skills.evidence_comparison import (
    ComparisonCandidate,
    propose_outcome,
    select_related_candidate,
)


def test_select_related_candidate_prefers_evidence_overlap() -> None:
    now = datetime.now(UTC)
    candidates = [
        ComparisonCandidate("unrelated", "课堂开始回顾上节内容", now),
        ComparisonCandidate(
            "matched", "关键提问后的等待时间延长，学生回应增加", now + timedelta(seconds=1)
        ),
    ]

    assert select_related_candidate("关键提问后等待", "出现学生回应", candidates) == "matched"


def test_select_related_candidate_refuses_unsupported_match() -> None:
    candidate = ComparisonCandidate("only", "完全无关的课堂导入", datetime.now(UTC))
    assert select_related_candidate("同伴互评", "学生解释理由", [candidate]) is None


def test_outcome_remains_a_bounded_candidate_label() -> None:
    assert propose_outcome("等待时间延长") == "improved"
    assert propose_outcome("学生回应减少") == "regressed"
    assert propose_outcome("课堂继续讨论") == "unchanged"
