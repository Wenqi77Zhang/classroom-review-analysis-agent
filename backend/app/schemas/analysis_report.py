"""分析、证据、复核与报告 Schema。

负责人：成员 3；协作：成员 1（报告页面）、成员 5（Agent 结构化输出与报告组合）。

`docs/interface-contracts.md` 把 `AnalysisConclusion` 的强制字段写死为
id / type / content / evidence_refs / review_status / created_at / trace_id，
成员 2 的 `contracts.ts` 与成员 5 的 `agent/contracts.py` 都以此对齐。

两条硬约束在本文件用校验器落实，不靠"大家记得检查"：

1. 每条结论至少一条证据引用（需求基线第 7 条、发布门禁"结论没有证据"）。
2. 视频/原文证据必须有时间范围，课件证据必须有页码或画面引用
   （`docs/interface-contracts.md`）。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from backend.app.schemas.common import ApiModel, OrmModel, ResourceId, UserRef

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
ReportTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]


class ConclusionType(StrEnum):
    """事实 / 判断 / 建议三层。前端按此分组，报告按此分节。"""

    FACT = "fact"
    JUDGMENT = "judgment"
    SUGGESTION = "suggestion"


class ReviewStatus(StrEnum):
    PENDING = "pending"  # 待教师复核
    ACCEPTED = "accepted"  # 原样接受
    MODIFIED = "modified"  # 教师改写后确认
    REJECTED = "rejected"  # 驳回


# 只有这两种状态允许进入报告。成员 5 在 Agent 侧做报告过滤，后端在数据层再拦一道：
# "未复核或已驳回结论进入报告"是发布门禁的阻断项，值得双重保险。
REPORTABLE_REVIEW_STATUSES: frozenset[ReviewStatus] = frozenset(
    {ReviewStatus.ACCEPTED, ReviewStatus.MODIFIED}
)


class EvidenceSourceType(StrEnum):
    VIDEO = "video"  # 视频片段
    TRANSCRIPT = "transcript"  # 逐字稿原文
    COURSEWARE = "courseware"  # 课件页
    FRAME = "frame"  # 视频画面


class EvidenceReference(OrmModel):
    """一条可定位的证据引用。

    定位信息按 `source_type` 分别必填；缺失即 422，Agent 无法用"我觉得"绕过门禁。
    """

    id: ResourceId | None = Field(default=None, description="Agent 写入时为空，落库后由后端补。")
    source_type: EvidenceSourceType
    asset_id: ResourceId | None = Field(default=None, description="证据所属文件。")
    segment_id: ResourceId | None = Field(default=None, description="逐字稿证据指向的句子。")
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, gt=0)
    page_no: int | None = Field(default=None, ge=1, description="课件页码，从 1 开始。")
    image_ref: str | None = Field(
        default=None, max_length=512, description="画面引用（对象 key）。"
    )
    quote: str | None = Field(default=None, max_length=2000, description="展示用摘录，可空。")

    @model_validator(mode="after")
    def _require_locator(self) -> EvidenceReference:
        if self.source_type in (EvidenceSourceType.VIDEO, EvidenceSourceType.TRANSCRIPT):
            if self.start_ms is None or self.end_ms is None:
                raise ValueError(
                    f"{self.source_type} 证据必须同时提供 start_ms 与 end_ms，"
                    "否则前端无法从结论跳回播放器片段。"
                )
            if self.end_ms <= self.start_ms:
                raise ValueError("end_ms 必须大于 start_ms。")
        elif self.source_type is EvidenceSourceType.FRAME:
            if self.start_ms is None and self.image_ref is None:
                raise ValueError("frame 证据必须提供 start_ms 或 image_ref 之一。")
        elif self.source_type is EvidenceSourceType.COURSEWARE:
            if self.page_no is None and self.image_ref is None:
                raise ValueError("课件证据必须提供 page_no 或 image_ref 之一。")
        return self


class AnalysisConclusion(OrmModel):
    """一条教学分析结论。字段集受 `docs/interface-contracts.md` 约束，不可随意增删。"""

    id: ResourceId
    classroom_id: ResourceId
    task_id: ResourceId
    type: ConclusionType
    content: str
    evidence_refs: list[EvidenceReference] = Field(min_length=1)
    review_status: ReviewStatus
    # 教师改写后的内容；review_status=modified 时报告用这一份，而不是 content。
    reviewed_content: str | None = None
    created_at: datetime
    trace_id: str

    # 证据账本：记录这条结论由哪个模型、哪个 Skill、哪版 Prompt 产生。
    # 由成员 5 在写入时提供，后端只持久化。
    model_name: str | None = Field(default=None, max_length=128)
    skill: str | None = Field(default=None, max_length=64)
    prompt_version: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _check_review_consistency(self) -> AnalysisConclusion:
        """`modified` 必须带非空的教师改写内容。

        否则会出现一种最坏的情况：状态显示"教师已修改确认"，报告里却是模型原文。
        这既是数据不一致，也直接违反"只组合已确认内容"（PR #6 审查意见 3）。
        """
        if (
            self.review_status is ReviewStatus.MODIFIED
            and not (self.reviewed_content or "").strip()
        ):
            raise ValueError(
                "review_status=modified 必须提供非空 reviewed_content；"
                "缺失时必须拒绝，不允许退回模型原文。"
            )
        return self

    def reportable_content(self) -> str:
        """报告应当采用的正文。

        对不可进入报告的状态直接抛错，而不是返回一段"看起来能用"的文本：
        静默回退正是"未复核或已驳回结论进入报告"这条阻断项的典型成因。
        """
        if self.review_status not in REPORTABLE_REVIEW_STATUSES:
            raise ValueError(
                f"review_status={self.review_status} 的结论不得进入报告，"
                f"仅允许 {sorted(s.value for s in REPORTABLE_REVIEW_STATUSES)}。"
            )
        if self.review_status is ReviewStatus.MODIFIED:
            # 校验器已保证非空；此处不做 `or self.content` 回退，避免将来
            # 有人绕过校验构造对象时悄悄拿到模型原文。
            if not (self.reviewed_content or "").strip():
                raise ValueError("modified 结论缺少教师改写内容，拒绝进入报告。")
            return self.reviewed_content  # type: ignore[return-value]
        return self.content


# --------------------------------------------------------------------------- #
# 复核
# --------------------------------------------------------------------------- #


class ReviewAction(StrEnum):
    ACCEPT = "accept"
    MODIFY = "modify"
    REJECT = "reject"


class ReviewRequest(ApiModel):
    action: ReviewAction
    edited_content: NonBlankText | None = Field(
        default=None, description="action=modify 时必填。"
    )
    note: str | None = Field(
        default=None,
        max_length=2000,
        description="教师备注写入复核历史；审计事件只记录动作和结果状态。",
    )

    @model_validator(mode="after")
    def _check_edited_content(self) -> ReviewRequest:
        if self.action is ReviewAction.MODIFY and not (self.edited_content or "").strip():
            raise ValueError("action=modify 必须提供非空 edited_content。")
        if self.action is not ReviewAction.MODIFY and self.edited_content is not None:
            raise ValueError("只有 action=modify 才能携带 edited_content。")
        return self


class ReviewDecision(OrmModel):
    """append-only 复核记录，构成"修改历史"。不覆盖，永不删除。"""

    id: ResourceId
    conclusion_id: ResourceId
    action: ReviewAction
    resulting_status: ReviewStatus
    previous_content: str | None = None
    edited_content: str | None = None
    note: str | None = None
    decided_by: UserRef
    created_at: datetime


# --------------------------------------------------------------------------- #
# 报告
# --------------------------------------------------------------------------- #


class ReportExportFormat(StrEnum):
    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"


class ReportRead(OrmModel):
    id: ResourceId
    classroom_id: ResourceId
    title: str
    content: str = Field(
        description="服务端从 accepted/modified 结论生成的 Markdown 正文。"
    )
    included_conclusion_ids: list[ResourceId] = Field(
        description="实际组合进报告的结论；后端保证其 review_status 都在 "
        "REPORTABLE_REVIEW_STATUSES 内。"
    )
    updated_at: datetime | None = None


class ReportUpdate(ApiModel):
    title: ReportTitle


class ReportExportRequest(ApiModel):
    format: ReportExportFormat = ReportExportFormat.MARKDOWN


class ReportExportResponse(OrmModel):
    format: ReportExportFormat
    download_url: str = Field(description="限时预签名地址；不得写入日志。")
    expires_at: datetime


# --------------------------------------------------------------------------- #
# 内部：Agent → 后端
# --------------------------------------------------------------------------- #


class InternalConclusionWrite(ApiModel):
    """Agent 写入一条结论。

    没有 `review_status` 字段：新结论一律 pending，Agent 不得直接改教师确认状态
    （`docs/project-plan-v5.md` §2.2："Agent 不得绕过证据门禁，也不得直接修改教师确认状态"）。
    """

    type: ConclusionType
    content: str = Field(min_length=1)
    evidence_refs: list[EvidenceReference] = Field(min_length=1)
    trace_id: str
    model_name: str | None = Field(default=None, max_length=128)
    skill: str | None = Field(default=None, max_length=64)
    prompt_version: str | None = Field(default=None, max_length=64)


class InternalConclusionBatchWrite(ApiModel):
    """整批替换该任务的结论。

    与逐字稿同理：换输入或重跑必须产生与新输入对应的新结论，追加语义会让旧结论
    残留（门禁："更换输入后仍出现固定结论"）。已复核的结论不会被覆盖，后端按
    conclusion 的 review_status 保留教师成果。
    """

    conclusions: list[InternalConclusionWrite] = Field(min_length=1)
