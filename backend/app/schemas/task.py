"""文件、任务、进度、错误与重试 Schema。

负责人：成员 3；协作：成员 4（Worker 回写）、成员 5（Agent 回写）。

本文件同时定义两组契约，不要混用：

* 面向浏览器的对外 Schema（教师带 JWT 调用）。
* 以 ``Internal`` 前缀命名的内部 Schema（Worker / Agent 带 ``WORKER_SERVICE_TOKEN``
  调用），是成员 4 的 `worker/job_store.py` 与成员 5 的 Agent 唯一的落库入口。

上传链路刻意设计成"后端签名 → 浏览器直传对象存储 → 后端确认"三步：视频二进制
不经过 FastAPI，也不进数据库（Issue #3 独立验收第 1 条）。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from backend.app.schemas.common import (
    ApiModel,
    ErrorCode,
    OrmModel,
    ResourceId,
)


class AssetKind(StrEnum):
    """三类可上传输入。

    `TRANSCRIPT` 只是补充输入：需求基线明确"只上传现成逐字稿不能替代真实视频处理链路"，
    因此仅有 transcript 的课堂不允许创建 `transcribe` 阶段的任务。
    """

    VIDEO = "video"
    COURSEWARE = "courseware"
    TRANSCRIPT = "transcript"


class UploadStatus(StrEnum):
    PENDING = "pending"  # 已签名，浏览器尚未确认传完
    UPLOADED = "uploaded"  # 已确认，对象可被 Worker 读取
    FAILED = "failed"  # 浏览器上传失败或确认超时


class PrivacyMode(StrEnum):
    """隐私路由：公开课可用云模型，私有课堂默认本地处理。"""

    LOCAL = "local"
    CLOUD = "cloud"


class TaskStatus(StrEnum):
    PENDING = "pending"  # 已创建，未入队
    QUEUED = "queued"  # 等待 Worker 领取
    RUNNING = "running"  # 某个 stage 正在执行
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStage(StrEnum):
    """处理阶段，顺序即前端进度条的顺序。

    命名与成员 4 的 `worker/stages/` 文件一一对应，改名要两边同步。
    """

    UPLOADED = "uploaded"
    EXTRACT_AUDIO = "extract_audio"
    SEGMENT = "segment"
    TRANSCRIBE = "transcribe"
    TRANSLATE = "translate"
    PARSE_COURSEWARE = "parse_courseware"
    BUILD_EVIDENCE_INDEX = "build_evidence_index"
    ANALYZE = "analyze"


# 状态机允许的迁移。后端在 `services/` 层按此表校验，非法迁移返回
# ErrorCode.STATE_CONFLICT，而不是默默改库——否则"失败可重试"这条无法验证。
ALLOWED_STATUS_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.QUEUED, TaskStatus.CANCELLED}),
    TaskStatus.QUEUED: frozenset({TaskStatus.RUNNING, TaskStatus.CANCELLED}),
    TaskStatus.RUNNING: frozenset(
        {TaskStatus.RUNNING, TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    # 失败后可重试：回到 QUEUED 是唯一出口，重试次数由后端累加。
    TaskStatus.FAILED: frozenset({TaskStatus.QUEUED}),
    TaskStatus.SUCCEEDED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}

TERMINAL_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}
)


# --------------------------------------------------------------------------- #
# 文件（Asset）
# --------------------------------------------------------------------------- #


class PresignRequest(ApiModel):
    kind: AssetKind
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=127)
    size_bytes: int = Field(gt=0, description="真实字节数；上限由 config 按 kind 分别校验。")


class PresignResponse(OrmModel):
    """浏览器拿到后直接 PUT 到 `upload_url`，再调 `/assets/{id}/complete`。

    `upload_url` 是限时、限对象、限方法的预签名地址（`PRESIGN_EXPIRE_SECONDS`）。
    它属于敏感数据：不得写入日志、不得存进前端 localStorage、不得进仓库。
    """

    asset_id: ResourceId
    object_key: str
    upload_url: str
    method: str = Field(default="PUT")
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="浏览器必须原样带上的请求头，如 Content-Type；缺失会导致签名不匹配。",
    )
    expires_at: datetime


class AssetCompleteRequest(ApiModel):
    """浏览器直传成功后回调，后端据此把 upload_status 落成 uploaded。"""

    etag: str | None = Field(default=None, max_length=255)
    checksum: str | None = Field(default=None, max_length=128)


class AssetRead(OrmModel):
    id: ResourceId
    classroom_id: ResourceId
    kind: AssetKind
    filename: str
    content_type: str
    size_bytes: int
    upload_status: UploadStatus
    # 只存地址与归属，不存二进制。
    object_key: str
    created_at: datetime


class DownloadUrlResponse(OrmModel):
    url: str
    expires_at: datetime


# --------------------------------------------------------------------------- #
# 任务（对外）
# --------------------------------------------------------------------------- #


class TaskCreate(ApiModel):
    asset_ids: list[ResourceId] = Field(min_length=1)
    privacy_mode: PrivacyMode = PrivacyMode.LOCAL
    # 分析契约由成员 5 在 `agent/contracts.py` 冻结结构；后端只做透传与持久化，
    # 不解释其语义。TODO(成员 5)：结构冻结后在此收紧为具体 Schema。
    analysis_contract: dict[str, Any] = Field(default_factory=dict)


class TaskRead(OrmModel):
    id: ResourceId
    classroom_id: ResourceId
    status: TaskStatus
    stage: TaskStage
    progress: float = Field(ge=0.0, le=1.0, description="当前阶段进度，真实值，不是前端计时器。")
    privacy_mode: PrivacyMode
    retry_count: int = Field(ge=0)
    last_error_code: ErrorCode | None = None
    last_error_message: str | None = None
    trace_id: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    finished_at: datetime | None = None


class TaskEventRead(OrmModel):
    """append-only 事件流，前端进度条读它。

    每次 (stage, status) 变更追加一行；因为有真实事件流，页面就不需要模拟计时器
    （发布门禁里"页面进度为模拟计时器"是阻断项）。
    """

    id: ResourceId
    task_id: ResourceId
    stage: TaskStage
    status: TaskStatus
    progress: float = Field(ge=0.0, le=1.0)
    message: str | None = None
    error_code: ErrorCode | None = None
    trace_id: str | None = None
    created_at: datetime


# --------------------------------------------------------------------------- #
# 任务（内部：Worker / Agent → 后端）
# --------------------------------------------------------------------------- #


class InternalTaskClaimRequest(ApiModel):
    """Worker 领取任务。

    `lease_seconds` 到期后任务可被重新领取，这样 Worker 进程被杀也不会让任务
    永久卡在 running（对应 Issue #3 的"失败可重试"）。
    """

    worker_id: str = Field(min_length=1, max_length=128)
    stages: list[TaskStage] = Field(min_length=1, description="该 Worker 能处理的阶段。")
    lease_seconds: int = Field(default=300, ge=30, le=3600)


class InternalTaskClaim(OrmModel):
    """领取成功后返回的任务包，含 Worker 读对象所需的一切。"""

    task_id: ResourceId
    classroom_id: ResourceId
    owner_id: ResourceId
    stage: TaskStage
    privacy_mode: PrivacyMode
    assets: list[AssetRead]
    analysis_contract: dict[str, Any] = Field(default_factory=dict)
    lease_expires_at: datetime
    trace_id: str


class InternalTaskStateUpdate(ApiModel):
    """Worker / Agent 回写阶段与状态。

    `error_code` 与 `message` 只在 status=failed 时有意义；后端会同时追加一条
    TaskEvent，因此 Worker 不需要（也不允许）自己写事件表。
    """

    stage: TaskStage
    status: TaskStatus
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: str | None = Field(default=None, max_length=2000)
    error_code: ErrorCode | None = None
    trace_id: str | None = None

    @model_validator(mode="after")
    def _require_error_on_failure(self) -> InternalTaskStateUpdate:
        if self.status is TaskStatus.FAILED and self.error_code is None:
            raise ValueError("status=failed 必须带 error_code，否则前端无法给出可操作提示。")
        return self


class InternalTaskHeartbeat(ApiModel):
    """续租。长阶段（ASR、翻译）必须周期性调用，否则租约到期任务会被别人抢走。"""

    worker_id: str = Field(min_length=1, max_length=128)
    lease_seconds: int = Field(default=300, ge=30, le=3600)
