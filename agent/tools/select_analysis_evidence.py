"""Bounded lexical retrieval with adjacent transcript context, without model calls."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

from agent.contracts import AnalysisContract, EvidenceItem
from backend.app.schemas.analysis_report import EvidenceSourceType

MAX_ITEMS = 12
MAX_TEXT_CHARS = 6000
MAX_ITEM_CHARS = 800
_STOP_WORDS = frozenset({
    "the", "and", "for", "with", "this", "that", "from", "have", "what", "which",
    "课堂", "分析", "教师", "学生", "是否", "内容", "进行", "复盘", "证据",
})


def _terms(text: str) -> set[str]:
    words = set(re.findall(r"[a-z][a-z0-9_]{2,}", text.casefold()))
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        words.update(run[index:index + 2] for index in range(len(run) - 1))
    return words - _STOP_WORDS


def _excerpt(text: str, terms: set[str], limit: int) -> str:
    """Keep a contiguous original span; never rewrite or synthesize evidence."""
    if len(text) <= limit:
        return text
    lowered = text.casefold()
    positions = [lowered.find(term) for term in terms if term in lowered]
    center = min(positions, default=0)
    start = max(0, min(center - limit // 3, len(text) - limit))
    return text[start:start + limit]


def select_analysis_evidence(
    evidence: Sequence[EvidenceItem], contract: AnalysisContract,
) -> list[EvidenceItem]:
    """Caller must filter tenant and teacher scope before invoking this selector.

    Ranking is an aid to retrieval, not semantic support verification. A sampled
    view cannot justify claims that something never happened in the full lesson.
    """
    if not evidence:
        return []
    query = _terms(" ".join([contract.goal, *contract.focus_areas, *contract.judgment_criteria]))
    documents = [_terms(item.text + " " + (item.translation or "")) for item in evidence]
    frequency = Counter(term for terms in documents for term in terms)
    scores = [
        sum(math.log(1 + len(evidence) / (1 + frequency[term])) for term in terms & query)
        / math.sqrt(max(1, len(terms)))
        for terms in documents
    ]
    selected: set[int] = set()

    def add_window(index: int) -> None:
        if len(selected) >= MAX_ITEMS:
            return
        selected.add(index)
        item = evidence[index]
        if item.reference.source_type is not EvidenceSourceType.TRANSCRIPT:
            return
        # Select the immediate sentences as context, only in the same recording.
        for neighbor in (index - 1, index + 1):
            if not 0 <= neighbor < len(evidence) or len(selected) >= MAX_ITEMS:
                continue
            other = evidence[neighbor]
            if (other.reference.source_type is EvidenceSourceType.TRANSCRIPT
                    and other.reference.asset_id == item.reference.asset_id
                    and other.reference.start_ms is not None
                    and item.reference.start_ms is not None
                    and abs(other.reference.start_ms - item.reference.start_ms) <= 15000):
                selected.add(neighbor)

    # Reserve one useful window per source so long slide decks cannot displace speech.
    sources = list(dict.fromkeys(item.reference.source_type for item in evidence))
    for source in sources:
        indices = [i for i, item in enumerate(evidence) if item.reference.source_type is source]
        best = max(indices, key=lambda i: (scores[i], -i))
        if scores[best] > 0:
            add_window(best)
    for index in sorted(range(len(evidence)), key=lambda i: (-scores[i], i)):
        if scores[index] > 0:
            add_window(index)
    # No lexical match: retain distributed source coverage instead of claiming relevance.
    if not selected:
        per_source = max(1, MAX_ITEMS // len(sources))
        for source in sources:
            indices = [i for i, item in enumerate(evidence) if item.reference.source_type is source]
            count = min(per_source, len(indices))
            for offset in range(count):
                selected.add(indices[offset * (len(indices) - 1) // max(1, count - 1)])

    # Divide the total budget fairly; a long first page must not crowd out later speech.
    per_item = min(MAX_ITEM_CHARS, MAX_TEXT_CHARS // max(1, len(selected)))
    result: list[EvidenceItem] = []
    for index in sorted(selected):
        item = evidence[index]
        text_limit = per_item if not item.translation else per_item // 2
        result.append(item.model_copy(update={
            "text": _excerpt(item.text, query, text_limit),
            "translation": _excerpt(item.translation, query, per_item - text_limit)
            if item.translation else None,
        }))
    return result
