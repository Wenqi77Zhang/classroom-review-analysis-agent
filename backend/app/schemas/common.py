"""ID、分页、统一错误与通用响应 Schema。

负责人：成员 3。本文件是跨模块契约的根：成员 2 的 `frontend/src/types/contracts.ts`、
成员 4 的 Worker 回写、成员 5 的 Agent 结构化输出都以此处的错误结构、分页结构和
枚举命名为准。修改前必须先更新 `../../../docs/product-and-technology-handbook.md`（`AGENTS.md` 第 7 条）。
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# 所有主键统一 UUID：任务、资源和结论的 ID 会出现在前端 URL 与对象存储 key 中，
# 自增整数会泄漏总量，也让跨账号猜 ID 变得容易。
ResourceId = UUID


class ApiModel(BaseModel):
    """请求体基类：拒绝未声明字段，避免前端拼错字段名却静默通过。"""

    model_config = ConfigDict(extra="forbid")


class OrmModel(BaseModel):
    """响应体基类：可直接从 ORM 实体读取。"""

    model_config = ConfigDict(from_attributes=True)


class ErrorCode(StrEnum):
    """统一错误码。

    前端按 `code` 分支处理，不解析 `message`（`message` 是给人看的，会改文案）。
    成员 2 的 `api.ts` 错误转换与成员 4 的 Worker 重试判断都依赖这份枚举。
    """

    VALIDATION_ERROR = "VALIDATION_ERROR"  # 400 参数不合法
    UNAUTHENTICATED = "UNAUTHENTICATED"  # 401 未登录或令牌失效
    PERMISSION_DENIED = "PERMISSION_DENIED"  # 403 资源属于你，但当前状态不允许该操作
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"  # 404 不存在，或不属于当前账号
    STATE_CONFLICT = "STATE_CONFLICT"  # 409 状态机不允许，如对 running 任务重试
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"  # 413 超出文件或请求体上限
    SCHEMA_INVALID = "SCHEMA_INVALID"  # 422 结构校验失败（含无证据结论被拦）
    RATE_LIMITED = "RATE_LIMITED"  # 429
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"  # 503 对象存储/ASR/模型不可用
    INTERNAL_ERROR = "INTERNAL_ERROR"  # 500


class ErrorBody(OrmModel):
    code: ErrorCode
    message: str = Field(description="面向教师的可读说明；不含堆栈、SQL、密钥或签名 URL。")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="结构化补充信息，如字段级校验错误 {field: reason}。",
    )
    trace_id: str = Field(
        description="与成员 5 的 agent/observability/tracing.py 共用同一 ID，"
        "用于把前端提示、后端日志和 Agent Trace 串成一条链。"
    )


class ErrorResponse(OrmModel):
    """所有非 2xx 响应的唯一外层结构：``{"error": {...}}``。"""

    error: ErrorBody


class PageParams(ApiModel):
    """列表查询统一分页参数。

    `limit` 必须有硬上限：否则一次 ``?limit=1000000`` 就能把数据库和内存拖死。
    """

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class Page[T](OrmModel):
    items: list[T]
    total: int = Field(description="满足条件的总数，供前端渲染分页控件。")
    limit: int
    offset: int


class UserRef(OrmModel):
    """用户的最小对外表示。

    结论、复核记录和审计事件都要标注"谁做的"，但不外泄口令哈希或多余身份信息。
    """

    id: ResourceId
    display_name: str


class Timestamped(OrmModel):
    created_at: datetime
    updated_at: datetime | None = None
