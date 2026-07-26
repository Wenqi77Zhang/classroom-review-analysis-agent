"""后端契约、配置、错误格式与日志脱敏测试。

负责人：成员 3。

覆盖范围（当前）：

* 跨模块 Schema 的校验器：无证据结论、证据定位信息、复核动作、任务状态回写。
* 配置的"启动即失败"与"密钥不可打印"。
* 统一错误格式、trace_id 贯通、CORS。
* 日志脱敏，含两条回归用例（见 `test_redaction_*`）。

尚未覆盖（TODO(成员 3)）：API 路由、权限与账号隔离、任务状态机迁移、
对象存储归属、持久化。这些随对应实现一起补。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from backend.app.config import ObjectStorageProvider, Settings
from backend.app.errors import NotFoundError, UpstreamUnavailableError, current_trace_id
from backend.app.main import RedactingFilter, create_app
from backend.app.schemas.analysis_report import (
    REPORTABLE_REVIEW_STATUSES,
    AnalysisConclusion,
    ConclusionType,
    EvidenceReference,
    EvidenceSourceType,
    InternalConclusionWrite,
    ReviewAction,
    ReviewRequest,
    ReviewStatus,
)
from backend.app.schemas.common import ErrorBody, ErrorCode, ErrorResponse, Page
from backend.app.schemas.task import (
    ALLOWED_STATUS_TRANSITIONS,
    InternalTaskStateUpdate,
    TaskStage,
    TaskStatus,
)
from backend.app.schemas.transcript import TranscriptSegment, TranscriptSegmentUpdate

# 测试用配置：显式传入而不读 .env，保证结果与本机配置无关。
TEST_SETTINGS_VALUES = {
    "database_url": "postgresql+asyncpg://classroom_review:pw@localhost:5432/classroom_review",
    "jwt_secret": "t" * 32,
    "worker_service_token": "worker-service-token",
    "object_storage_endpoint": "http://localhost:9000",
    "object_storage_bucket": "classroom-review",
    "object_storage_access_key_id": "testkey",
    "object_storage_secret_access_key": "testsecret",
    "frontend_origin": "http://localhost:3000",
}


def make_settings(**overrides: object) -> Settings:
    values = dict(TEST_SETTINGS_VALUES)
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(make_settings())

    # 仅测试用路由，验证领域异常与未处理异常都能落进统一错误格式。
    @app.get("/_test/notfound")
    async def _notfound() -> None:
        raise NotFoundError("课堂不存在。")

    @app.get("/_test/upstream")
    async def _upstream() -> None:
        raise UpstreamUnavailableError()

    @app.get("/_test/boom")
    async def _boom() -> None:
        raise RuntimeError("数据库口令是 hunter2，绝不能回给前端")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# --------------------------------------------------------------------------- #
# 证据与结论契约
# --------------------------------------------------------------------------- #


def test_conclusion_requires_at_least_one_evidence() -> None:
    """无证据结论必须在 Schema 层被拒，Agent 无法绕过证据门禁。"""
    with pytest.raises(ValidationError):
        InternalConclusionWrite(
            type=ConclusionType.JUDGMENT,
            content="提问密度偏低",
            evidence_refs=[],
            trace_id="t-1",
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"source_type": EvidenceSourceType.VIDEO}, id="video-缺时间范围"),
        pytest.param(
            {"source_type": EvidenceSourceType.TRANSCRIPT, "start_ms": 1000},
            id="transcript-只有起点",
        ),
        pytest.param(
            {"source_type": EvidenceSourceType.TRANSCRIPT, "start_ms": 5000, "end_ms": 5000},
            id="时间范围为空区间",
        ),
        pytest.param({"source_type": EvidenceSourceType.COURSEWARE}, id="课件-无页码无画面"),
        pytest.param({"source_type": EvidenceSourceType.FRAME}, id="画面-无时间无引用"),
    ],
)
def test_evidence_requires_locator(kwargs: dict[str, object]) -> None:
    """定位信息缺失的证据必须被拒，否则前端无法从结论跳回证据。"""
    with pytest.raises(ValidationError):
        EvidenceReference(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param(
            {"source_type": EvidenceSourceType.VIDEO, "start_ms": 1000, "end_ms": 8000},
            id="video-带时间范围",
        ),
        pytest.param(
            {"source_type": EvidenceSourceType.COURSEWARE, "page_no": 12}, id="课件-带页码"
        ),
        pytest.param(
            {"source_type": EvidenceSourceType.FRAME, "start_ms": 42000}, id="画面-带时间点"
        ),
    ],
)
def test_evidence_accepts_valid_locator(kwargs: dict[str, object]) -> None:
    assert EvidenceReference(**kwargs)  # type: ignore[arg-type]


def test_modified_conclusion_uses_reviewed_content_in_report() -> None:
    """review_status=modified 时报告必须采用教师改写内容，而不是原始 content。"""
    conclusion = AnalysisConclusion(
        id=uuid4(),
        classroom_id=uuid4(),
        task_id=uuid4(),
        type=ConclusionType.SUGGESTION,
        content="原始建议",
        evidence_refs=[
            EvidenceReference(source_type=EvidenceSourceType.VIDEO, start_ms=0, end_ms=1000)
        ],
        review_status=ReviewStatus.MODIFIED,
        reviewed_content="教师改写后的建议",
        created_at=datetime.now(UTC),
        trace_id="t-9",
    )
    assert conclusion.reportable_content() == "教师改写后的建议"


def test_only_accepted_and_modified_are_reportable() -> None:
    """未复核或已驳回内容进入报告是发布门禁的阻断项。"""
    assert REPORTABLE_REVIEW_STATUSES == {ReviewStatus.ACCEPTED, ReviewStatus.MODIFIED}
    assert ReviewStatus.PENDING not in REPORTABLE_REVIEW_STATUSES
    assert ReviewStatus.REJECTED not in REPORTABLE_REVIEW_STATUSES


# --------------------------------------------------------------------------- #
# 复核与任务状态
# --------------------------------------------------------------------------- #


def test_modify_requires_edited_content() -> None:
    with pytest.raises(ValidationError):
        ReviewRequest(action=ReviewAction.MODIFY)
    with pytest.raises(ValidationError):
        ReviewRequest(action=ReviewAction.MODIFY, edited_content="   ")


def test_non_modify_must_not_carry_edited_content() -> None:
    with pytest.raises(ValidationError):
        ReviewRequest(action=ReviewAction.ACCEPT, edited_content="偷偷改写")


def test_failed_state_update_requires_error_code() -> None:
    """没有 error_code 的失败无法给教师任何可操作提示。"""
    with pytest.raises(ValidationError):
        InternalTaskStateUpdate(stage=TaskStage.TRANSCRIBE, status=TaskStatus.FAILED)

    assert InternalTaskStateUpdate(
        stage=TaskStage.TRANSCRIBE,
        status=TaskStatus.FAILED,
        error_code=ErrorCode.UPSTREAM_UNAVAILABLE,
    )


def test_progress_must_be_within_zero_and_one() -> None:
    with pytest.raises(ValidationError):
        InternalTaskStateUpdate(stage=TaskStage.TRANSLATE, status=TaskStatus.RUNNING, progress=1.5)


def test_failed_task_can_be_retried_and_success_is_terminal() -> None:
    assert TaskStatus.QUEUED in ALLOWED_STATUS_TRANSITIONS[TaskStatus.FAILED]
    assert ALLOWED_STATUS_TRANSITIONS[TaskStatus.SUCCEEDED] == frozenset()
    assert ALLOWED_STATUS_TRANSITIONS[TaskStatus.CANCELLED] == frozenset()


# --------------------------------------------------------------------------- #
# 逐字稿
# --------------------------------------------------------------------------- #


def test_transcript_segment_rejects_inverted_time_range() -> None:
    with pytest.raises(ValidationError):
        TranscriptSegment(
            id=uuid4(),
            task_id=uuid4(),
            index=0,
            start_ms=9000,
            end_ms=1000,
            text="hello",
            source_language="en",
        )


def test_empty_transcript_patch_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TranscriptSegmentUpdate()
    assert TranscriptSegmentUpdate(speaker="教师")


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "missing",
    ["database_url", "jwt_secret", "worker_service_token", "object_storage_bucket"],
)
def test_missing_required_setting_fails_at_startup(missing: str) -> None:
    values = {k: v for k, v in TEST_SETTINGS_VALUES.items() if k != missing}
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://u:p@localhost:5432/db",
        "postgresql+psycopg://u:p@localhost:5432/db",
        "sqlite+aiosqlite:///./test.db",
    ],
)
def test_sync_or_wrong_driver_is_rejected(url: str) -> None:
    """同步驱动会阻塞事件循环；SQLite 无法验证账号隔离与 JSONB 语义。"""
    with pytest.raises(ValidationError):
        make_settings(database_url=url)


def test_weak_jwt_secret_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(jwt_secret="short")


@pytest.mark.parametrize("seconds", [10, 7200])
def test_presign_expiry_must_stay_within_bounds(seconds: int) -> None:
    """限时是 docs/data-security.md 的强制要求：过长的签名等同于长期公开对象。"""
    with pytest.raises(ValidationError):
        make_settings(object_storage_presigned_url_ttl_seconds=seconds)


def test_secrets_are_not_printable() -> None:
    settings = make_settings()
    secret = TEST_SETTINGS_VALUES["jwt_secret"]
    for rendered in (repr(settings), str(settings), str(settings.model_dump())):
        assert secret not in rendered
    # 明文只能通过显式调用取到
    assert settings.jwt_secret.get_secret_value() == secret


def test_object_storage_defaults_target_backblaze_b2() -> None:
    """M1 默认供应商是 B2；B2 的 S3 API 用 virtual-host 寻址，故 path-style 默认 false。

    默认值写错会导致"本地 MinIO 能传、切到 B2 传不上"这类难查的问题。
    """
    settings = make_settings()
    assert settings.object_storage_provider is ObjectStorageProvider.BACKBLAZE_B2
    assert settings.object_storage_use_path_style is False
    assert settings.object_storage_presigned_url_ttl_seconds == 900


def test_unknown_object_storage_provider_is_rejected() -> None:
    """供应商用枚举而非自由字符串，让"业务层不直接依赖 B2"有可检查的边界。"""
    with pytest.raises(ValidationError):
        make_settings(object_storage_provider="aliyun_oss")


@pytest.mark.parametrize("days", [0, 91])
def test_object_retention_days_must_stay_within_bounds(days: int) -> None:
    with pytest.raises(ValidationError):
        make_settings(object_storage_retention_days=days)


def test_upload_limit_differs_by_kind() -> None:
    settings = make_settings()
    assert settings.max_upload_bytes("video") > settings.max_upload_bytes("courseware")
    # 未知类型退回最严格值，避免新增类型时意外获得视频级上限
    assert settings.max_upload_bytes("unknown") == settings.max_upload_bytes("transcript")


# --------------------------------------------------------------------------- #
# 统一错误格式与中间件
# --------------------------------------------------------------------------- #


async def test_health_is_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "X-Trace-Id" in response.headers


async def test_trace_id_from_upstream_is_reused(client: httpx.AsyncClient) -> None:
    """Worker 与 Agent 透传的 trace_id 必须被沿用，否则跨模块链路串不起来。"""
    response = await client.get("/health", headers={"X-Trace-Id": "trace-from-agent"})
    assert response.headers["X-Trace-Id"] == "trace-from-agent"


async def test_trace_id_context_is_reset_after_request(client: httpx.AsyncClient) -> None:
    await client.get("/health")
    assert current_trace_id.get() == "-"


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/does-not-exist", 404, "RESOURCE_NOT_FOUND"),
        ("/_test/notfound", 404, "RESOURCE_NOT_FOUND"),
        ("/_test/upstream", 503, "UPSTREAM_UNAVAILABLE"),
        ("/_test/boom", 500, "INTERNAL_ERROR"),
    ],
)
async def test_errors_use_unified_envelope(
    client: httpx.AsyncClient, path: str, status: int, code: str
) -> None:
    response = await client.get(path)
    body = response.json()
    assert response.status_code == status
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert body["error"]["trace_id"]


async def test_unhandled_exception_does_not_leak_details(client: httpx.AsyncClient) -> None:
    """异常文本可能含 SQL、路径或凭据，绝不能回给前端。"""
    response = await client.get("/_test/boom")
    assert "hunter2" not in response.text


async def test_cors_allows_only_configured_origin(client: httpx.AsyncClient) -> None:
    allowed = await client.options(
        "/health",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"},
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"

    denied = await client.options(
        "/health",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert denied.headers.get("access-control-allow-origin") is None


def test_error_envelope_serializes_to_json() -> None:
    body = ErrorResponse(
        error=ErrorBody(code=ErrorCode.PERMISSION_DENIED, message="无权访问", trace_id="t-2")
    )
    assert body.model_dump(mode="json")["error"]["code"] == "PERMISSION_DENIED"


def test_page_generic_serializes() -> None:
    page = Page[TranscriptSegment](items=[], total=0, limit=50, offset=0)
    assert page.model_dump(mode="json") == {"items": [], "total": 0, "limit": 50, "offset": 0}


# --------------------------------------------------------------------------- #
# 日志脱敏
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        ("Authorization: Bearer abc.def.ghi", "abc.def.ghi"),
        ("authorization=plainTokenNoScheme", "plainTokenNoScheme"),
        ('{"Authorization": "Basic dXNlcjpwYXNz"}', "dXNlcjpwYXNz"),
        ('{"jwt_secret": "s3cr3tvalue"}', "s3cr3tvalue"),
        ("OBJECT_STORAGE_SECRET_ACCESS_KEY=minio-secret-xyz", "minio-secret-xyz"),
        ("password=hunter2", "hunter2"),
        ("https://s3/b/k?X-Amz-Signature=deadbeefcafe&X-Amz-Expires=900", "deadbeefcafe"),
    ],
)
def test_redaction_masks_secrets(raw: str, secret: str) -> None:
    """发布门禁：密钥不得出现在日志。"""
    record = logging.LogRecord("t", logging.INFO, "f", 1, raw, None, None)
    RedactingFilter().filter(record)
    assert secret not in str(record.msg)


def test_redaction_does_not_touch_ordinary_messages() -> None:
    record = logging.LogRecord(
        "t", logging.INFO, "f", 1, "任务 abc123 进入 transcribe 阶段", None, None
    )
    RedactingFilter().filter(record)
    assert "transcribe" in str(record.msg)


@pytest.mark.parametrize(
    ("template", "args", "expected"),
    [
        pytest.param('HTTP %s "%s %d %s"', ("GET", "HTTP/1.1", 200, "OK"), "200", id="int-%d"),
        pytest.param("进度 %.2f", (0.75,), "0.75", id="float-%.2f"),
        pytest.param("重试 %d/%d 次", (2, 3), "2/3", id="多个 int"),
    ],
)
def test_redaction_preserves_non_string_arg_types(
    template: str, args: tuple[object, ...], expected: str
) -> None:
    """回归：早期版本把 args 全部 str() 化，导致 %d/%f 抛 TypeError。

    httpx 的 'HTTP Request: %s %s "%s %d %s"' 会因此让整个请求日志报错。
    """
    record = logging.LogRecord("t", logging.INFO, "f", 1, template, args, None)
    RedactingFilter().filter(record)
    assert expected in record.getMessage()
