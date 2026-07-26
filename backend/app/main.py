"""FastAPI 应用、中间件、统一异常处理与健康检查。

负责人：成员 3。

这里集中三件全局性的事，避免散落到每个路由：

1. **trace_id**：请求入口生成，写入 ContextVar 与响应头 `X-Trace-Id`，与成员 5 的
   Agent Trace 共用同一 ID。
2. **统一错误格式**：所有异常都转成 ``{"error": {...}}``。业务代码只抛
   `errors.AppError` 子类，不自己拼 HTTP 响应，这样格式只有一处实现。
3. **日志脱敏**：发布门禁里"密钥出现在前端、仓库或日志"是阻断项，所以在 logging
   层强制过滤，而不是依赖每个调用点记得别打印。
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.config import Settings, get_settings
from backend.app.database import dispose_engine, get_session_factory
from backend.app.errors import AppError, current_trace_id
from backend.app.schemas.common import ErrorBody, ErrorCode, ErrorResponse

logger = logging.getLogger("backend")


# --------------------------------------------------------------------------- #
# 日志脱敏
# --------------------------------------------------------------------------- #

_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Authorization: Bearer xxx
    # 必须显式吃掉 Bearer/Basic 前缀，否则 (\S+) 只匹配到 "Bearer"，
    # 真正的令牌会原样留在日志里。
    (
        re.compile(
            r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?)"
            r"(?:bearer\s+|basic\s+|token\s+)?([^\s\"',&}]+)"
        ),
        r"\1***",
    ),
    # key/token/secret/password = xxx（含 JSON 与 querystring 形态）
    (
        re.compile(
            r"(?i)((?:api[_-]?key|access[_-]?key|secret[_-]?\w*|token|password)"
            r"[\"']?\s*[:=]\s*[\"']?)([^\s\"',&}]+)"
        ),
        r"\1***",
    ),
    # 对象存储预签名 URL 的签名参数
    (
        re.compile(
            r"(?i)([?&](?:X-Amz-Signature|X-Amz-Credential|X-Amz-Security-Token)=)([^&\s]+)"
        ),
        r"\1***",
    ),
)


class RedactingFilter(logging.Filter):
    """把疑似密钥的片段替换成 ``***``。

    在 filter 层做而不是在格式化层：filter 对所有 handler 生效，
    第三方库（uvicorn、sqlalchemy、botocore）打印的内容也会被覆盖。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._scrub(record.msg)
        # 只处理字符串参数，保留原类型。早期版本把所有 args 都 str() 化，
        # 结果第三方库的 "%d" 格式串收到字符串直接抛 TypeError
        # （httpx 的 'HTTP Request: %s %s "%s %d %s"' 就会炸）。
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (self._scrub(v) if isinstance(v, str) else v) for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self._scrub(a) if isinstance(a, str) else a for a in record.args
                )
        return True

    @staticmethod
    def _scrub(text_value: str) -> str:
        for pattern, replacement in _REDACTIONS:
            text_value = pattern.sub(replacement, text_value)
        return text_value


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s [trace=%(trace_id)s] %(message)s")
    )
    handler.addFilter(RedactingFilter())
    handler.addFilter(_TraceIdLogFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level)

    # 这些库默认较吵，且可能把 SQL 参数或 HTTP 头打出来。
    for noisy in ("sqlalchemy.engine", "botocore", "boto3", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class _TraceIdLogFilter(logging.Filter):
    """把当前 trace_id 注入日志记录，供格式串使用。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = current_trace_id.get()
        return True


# --------------------------------------------------------------------------- #
# 错误响应
# --------------------------------------------------------------------------- #


def _error_response(
    status_code: int,
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            details=details or {},
            trace_id=current_trace_id.get(),
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))


# HTTP 状态码 → 错误码。FastAPI/Starlette 内部抛的 HTTPException 也要落进统一格式。
_STATUS_TO_CODE: dict[int, ErrorCode] = {
    400: ErrorCode.VALIDATION_ERROR,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.PERMISSION_DENIED,
    404: ErrorCode.RESOURCE_NOT_FOUND,
    405: ErrorCode.VALIDATION_ERROR,
    409: ErrorCode.STATE_CONFLICT,
    413: ErrorCode.PAYLOAD_TOO_LARGE,
    422: ErrorCode.SCHEMA_INVALID,
    429: ErrorCode.RATE_LIMITED,
    503: ErrorCode.UPSTREAM_UNAVAILABLE,
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        # 4xx 属于预期内的调用错误，按 info 记；5xx 才是需要排查的。
        log = logger.warning if exc.http_status < 500 else logger.error
        log("AppError %s: %s", exc.code, exc.message)
        return _error_response(exc.http_status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # 只回字段与原因，不回收到的值——请求体里可能带口令或令牌。
        fields = {
            ".".join(str(p) for p in err.get("loc", ()) if p != "body"): err.get("msg", "")
            for err in exc.errors()
        }
        return _error_response(
            422,
            ErrorCode.SCHEMA_INVALID,
            "请求结构校验失败。",
            {"fields": fields},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
        return _error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # 记完整堆栈供排查，但**不**把异常文本回给前端：它可能含 SQL、路径或凭据。
        logger.exception("未处理异常: %s", type(exc).__name__)
        return _error_response(500, ErrorCode.INTERNAL_ERROR, "服务内部错误，请稍后重试。")


# --------------------------------------------------------------------------- #
# 应用
# --------------------------------------------------------------------------- #


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    logger.info("后端启动，环境=%s", settings.app_env)
    yield
    await dispose_engine()
    logger.info("后端关闭，连接池已释放")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)

    app = FastAPI(
        title="课堂复盘与教学分析系统 后端 API",
        version="0.1.0",
        # 生产环境关闭交互文档：它会暴露完整内部接口面，包括 /api/internal/*。
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        # 不用 "*"：前端带凭据跨域时通配符无效，也无谓放大攻击面。
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Trace-Id"],
    )

    @app.middleware("http")
    async def trace_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # 允许上游（成员 5 的 Agent、Worker）透传 trace_id，从而串起同一条链路。
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex
        token = current_trace_id.set(trace_id)
        try:
            response = await call_next(request)
        finally:
            current_trace_id.reset(token)
        response.headers["X-Trace-Id"] = trace_id
        return response

    register_exception_handlers(app)

    @app.get("/health", tags=["health"], summary="存活检查")
    async def health() -> dict[str, str]:
        """不查数据库：存活检查必须在依赖故障时仍能回答，否则无法区分"进程死了"和"数据库挂了"。"""
        return {"status": "ok", "app_env": settings.app_env.value}

    @app.get("/health/ready", tags=["health"], summary="就绪检查（含数据库）")
    async def ready() -> dict[str, str]:
        factory = get_session_factory()
        async with factory() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}

    # TODO(成员 3)：注册 auth / classrooms / uploads / tasks / transcripts /
    # analyses / reports 以及 internal 路由。当前仅健康检查可用。
    return app


# 刻意不提供模块级 `app` 实例。启动方式：
#   uvicorn --factory backend.app.main:create_app --port 8000
# 用工厂而非模块级实例，是为了让配置缺失在启动命令处明确报错，而不是在 import
# 阶段抛出——后者的堆栈看不出到底缺哪个环境变量。测试也可以注入自己的 Settings。
