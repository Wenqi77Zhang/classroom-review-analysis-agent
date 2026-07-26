"""时间戳、说话人、原文与译文 Schema。

负责人：成员 3；协作：成员 4（Worker 写入真实识别结果）。

需求基线第 5、6 条：逐字稿必须由视频实际生成并带时间点；英文或中英混合课堂要
同时保留英文原文和逐句中文译文，且教师可以修改文字、说话人和译文。

因此这里刻意做成"原文与译文同一条 segment 上的两个字段"，而不是两份独立列表：
逐句对齐是硬要求，两份列表会在教师插入/删除句子后错位。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from backend.app.schemas.common import ApiModel, OrmModel, ResourceId, UserRef


class TranscriptSegment(OrmModel):
    """一句逐字稿。

    时间用毫秒整数而不是浮点秒：前端点击结论要跳回播放器精确位置，浮点累加会漂移，
    整数毫秒也便于数据库排序与区间查询。
    """

    id: ResourceId
    task_id: ResourceId
    index: int = Field(ge=0, description="句序，从 0 开始；教师编辑不改变 index。")
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    speaker: str | None = Field(default=None, max_length=64, description='如"教师""学生 1"。')
    text: str = Field(description="识别出的原文，不做翻译。")
    source_language: str = Field(max_length=16, description='BCP-47，如 "en"、"zh"、"en-zh"。')
    translation: str | None = Field(default=None, description="逐句中文译文；中文课堂可为空。")
    translation_language: str | None = Field(default=None, max_length=16)
    is_edited: bool = Field(default=False, description="是否被教师改过，前端据此显示标记。")
    edited_at: datetime | None = None

    @model_validator(mode="after")
    def _check_range(self) -> TranscriptSegment:
        if self.end_ms <= self.start_ms:
            raise ValueError("end_ms 必须大于 start_ms，否则证据无法定位到有效区间。")
        return self


class TranscriptRead(OrmModel):
    task_id: ResourceId
    source_language: str
    has_translation: bool = Field(description="前端据此决定是否渲染双语列。")
    segment_count: int
    duration_ms: int = Field(ge=0)
    segments: list[TranscriptSegment]


class TranscriptSegmentUpdate(ApiModel):
    """教师修改一句。

    三个字段都是可选，但不能全空——全空的 PATCH 只会产生一条无意义的修改历史。
    """

    text: str | None = None
    speaker: str | None = Field(default=None, max_length=64)
    translation: str | None = None

    @model_validator(mode="after")
    def _require_any_field(self) -> TranscriptSegmentUpdate:
        if self.text is None and self.speaker is None and self.translation is None:
            raise ValueError("text、speaker、translation 至少要提供一个。")
        return self


class TranscriptSegmentRevision(OrmModel):
    """append-only 修改历史。

    不覆盖原值：门禁里"教师修改内容或状态没有持久保存"是阻断项，必须能拿出前后对比。
    """

    id: ResourceId
    segment_id: ResourceId
    previous_text: str | None = None
    previous_speaker: str | None = None
    previous_translation: str | None = None
    edited_by: UserRef
    created_at: datetime


# --------------------------------------------------------------------------- #
# 内部：Worker → 后端
# --------------------------------------------------------------------------- #


class InternalTranscriptSegmentWrite(ApiModel):
    index: int = Field(ge=0)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    speaker: str | None = Field(default=None, max_length=64)
    text: str
    translation: str | None = None


class InternalTranscriptWrite(ApiModel):
    """Worker 批量写入识别结果。

    整批替换而不是逐句追加：ASR 重跑（重试或换输入）必须产生与新输入对应的结果，
    追加语义会把两次运行的句子混在一起（门禁："更换输入后仍出现固定结论"）。
    """

    source_language: str = Field(max_length=16)
    translation_language: str | None = Field(default=None, max_length=16)
    duration_ms: int = Field(ge=0)
    segments: list[InternalTranscriptSegmentWrite] = Field(min_length=1)
    trace_id: str | None = None
