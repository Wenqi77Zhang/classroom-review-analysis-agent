"""后端领域异常与 trace_id 上下文。

负责人：成员 3。

**这是相对 `../../docs/product-and-technology-handbook.md` §2.2 文件清单的新增文件**，原因是异常类不能放在
`main.py`：`services/` 与 `repositories/` 需要抛这些异常，而 `main.py` 要 import 它们，
放一起会形成循环 import。属 `backend/` 内部结构、不改跨模块契约，已记录在
`../../docs/product-and-technology-handbook.md` 的后端模块部分，待成员 1 确认文件清单。

设计要点：业务代码只抛语义异常（"这个资源不属于你"），不关心 HTTP 状态码和响应格式；
状态码与 `{"error": {...}}` 外层由 `main.py` 的处理器统一生成。这样错误格式只有一处
实现，不会出现"某个路由忘了包装、直接漏出 500"。
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from backend.app.schemas.common import ErrorCode

# 当前请求的 trace_id。用 ContextVar 而不是层层传参：审计、日志和异常处理都要用它，
# 传参会污染每个函数签名，而 ContextVar 在 asyncio 下天然按任务隔离。
current_trace_id: ContextVar[str] = ContextVar("current_trace_id", default="-")


class AppError(Exception):
    """所有后端领域异常的基类。"""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    http_status: int = 500
    default_message: str = "服务内部错误。"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        commit_changes: bool = False,
    ) -> None:
        self.message = message or self.default_message
        self.details = details or {}
        self.commit_changes = commit_changes
        super().__init__(self.message)


class UnauthenticatedError(AppError):
    code = ErrorCode.UNAUTHENTICATED
    http_status = 401
    default_message = "请先登录。"


class PermissionDeniedError(AppError):
    """资源确实属于当前账号，但当前状态不允许该操作。

    注意：跨账号访问**不要**用这个异常，用 `NotFoundError`——否则 403 会泄漏
    "这个 ID 存在"。见 `../../docs/product-and-technology-handbook.md` 的安全取舍。
    """

    code = ErrorCode.PERMISSION_DENIED
    http_status = 403
    default_message = "当前状态不允许该操作。"


class NotFoundError(AppError):
    code = ErrorCode.RESOURCE_NOT_FOUND
    http_status = 404
    default_message = "资源不存在。"


class StateConflictError(AppError):
    code = ErrorCode.STATE_CONFLICT
    http_status = 409
    default_message = "当前状态不允许该变更。"


class ValidationFailedError(AppError):
    code = ErrorCode.VALIDATION_ERROR
    http_status = 400
    default_message = "参数不合法。"


class PayloadTooLargeError(AppError):
    code = ErrorCode.PAYLOAD_TOO_LARGE
    http_status = 413
    default_message = "文件超出允许大小。"


class UpstreamUnavailableError(AppError):
    """对象存储、ASR 或模型服务不可用。

    单独成类是因为它是**可重试**错误：前端据此显示"重试"而不是"参数错误"，
    Worker 也据此决定是否让任务回到可重试状态。
    """

    code = ErrorCode.UPSTREAM_UNAVAILABLE
    http_status = 503
    default_message = "依赖服务暂时不可用，请稍后重试。"
