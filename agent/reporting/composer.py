"""只组合 accepted/modified 结论并保留可定位来源。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.schemas.analysis_report import (
    REPORTABLE_REVIEW_STATUSES,
    AnalysisConclusion,
    ConclusionType,
)
from backend.app.schemas.common import ResourceId


class ComposedReport(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str
    included_conclusion_ids: list[ResourceId]


_SECTION_TITLES = {
    ConclusionType.FACT: "事实",
    ConclusionType.JUDGMENT: "判断",
    ConclusionType.SUGGESTION: "建议",
}


def _format_reference(conclusion: AnalysisConclusion) -> str:
    labels: list[str] = []
    for reference in conclusion.evidence_refs:
        if reference.start_ms is not None:
            end = reference.end_ms if reference.end_ms is not None else reference.start_ms
            labels.append(f"{reference.source_type.value} {reference.start_ms}–{end} ms")
        elif reference.page_no is not None:
            labels.append(f"{reference.source_type.value} 第 {reference.page_no} 页")
        elif reference.image_ref:
            labels.append(f"{reference.source_type.value} 画面证据")
    return "；".join(labels)


def compose_reviewed_report(
    *, title: str, conclusions: list[AnalysisConclusion]
) -> ComposedReport:
    """过滤未复核/已驳回项；modified 严格采用教师改写内容。"""

    normalized_title = title.strip()
    if not normalized_title:
        raise ValueError("报告标题不能为空。")
    reportable = [
        item for item in conclusions if item.review_status in REPORTABLE_REVIEW_STATUSES
    ]
    lines = [f"# {normalized_title}"]
    included: list[ResourceId] = []
    for conclusion_type in ConclusionType:
        items = [item for item in reportable if item.type is conclusion_type]
        if not items:
            continue
        lines.extend(["", f"## {_SECTION_TITLES[conclusion_type]}"])
        for item in items:
            included.append(item.id)
            lines.extend(
                [
                    "",
                    f"- {item.reportable_content().strip()}",
                    f"  - 证据：{_format_reference(item)}",
                    f"  - Trace：`{item.trace_id}`",
                ]
            )
    if not included:
        lines.extend(["", "当前没有经教师接受或修改确认的结论。"])
    return ComposedReport(
        title=normalized_title,
        content="\n".join(lines) + "\n",
        included_conclusion_ids=included,
    )
