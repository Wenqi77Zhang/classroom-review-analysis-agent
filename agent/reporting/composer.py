"""只组合 accepted/modified 结论并保留可定位来源。"""

from __future__ import annotations

import re

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


def _plain_text(value: str) -> str:
    """Keep untrusted classroom text literal in Markdown and exported documents."""
    return re.sub(r"([\\`*_{}\[\]<>#+!|])", r"\\\1", " ".join(value.split()))


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


def compose_report_body(conclusions: list[AnalysisConclusion]) -> str:
    """One composition path for the API and Agent; no model-generated report facts."""
    lines: list[str] = []
    for conclusion_type in ConclusionType:
        items = [item for item in conclusions if item.type is conclusion_type
                 and item.review_status in REPORTABLE_REVIEW_STATUSES]
        if not items:
            continue
        lines.extend([f"## {_SECTION_TITLES[conclusion_type]}", ""])
        for item in items:
            review_label = "教师修改确认" if item.review_status == "modified" else "教师接受"
            lines.extend([
                f"- {_plain_text(item.reportable_content().strip())}",
                f"  - 人工复核：{review_label}；结论编号：{item.id}",
                f"  - 证据定位：{_format_reference(item)}",
            ])
            for index, ref in enumerate(item.evidence_refs, 1):
                identifiers = [f"证据 {index}"]
                if ref.id:
                    identifiers.append(f"编号 {ref.id}")
                if ref.asset_id:
                    identifiers.append(f"资料 {ref.asset_id}")
                if ref.segment_id:
                    identifiers.append(f"逐字稿句子 {ref.segment_id}")
                lines.append(f"  - {'；'.join(identifiers)}")
                lines.append(f"    - 原文摘录：{_plain_text(ref.quote) if ref.quote else '该证据未提供文字摘录，请在工作台核对原始画面。'}")
            provenance = [
                f"模型：{_plain_text(item.model_name or '未记录')}",
                f"分析方法：{_plain_text(item.skill or '未记录')}",
                f"提示词版本：{_plain_text(item.prompt_version or '未记录')}",
                f"Trace：{_plain_text(item.trace_id)}",
            ]
            lines.extend([f"  - {'；'.join(provenance)}", ""])
    return "\n".join(lines).rstrip()


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
    included = [item.id for kind in ConclusionType for item in reportable if item.type is kind]
    content = compose_report_body(reportable) or "当前没有经教师接受或修改确认的结论。"
    return ComposedReport(
        title=normalized_title,
        content=f"# {_plain_text(normalized_title)}\n\n{content}\n",
        included_conclusion_ids=included,
    )
