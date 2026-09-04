"""环境变量校验与运行配置。

负责人：成员 3。

两条设计约束：

* **启动即失败**：必填项缺失时在应用启动阶段就报错，而不是等到教师上传视频时才 500。
  四天冲刺里配置错误是最常见的"看起来像 bug 的非 bug"，早失败能省大量排查时间。
* **密钥不可打印**：所有敏感值用 `SecretStr`，这样 `repr(settings)`、日志、异常堆栈
  和 FastAPI 的报错页都不会带出明文。发布门禁里"密钥出现在前端、仓库或日志"是阻断项。

变量清单与 `.env.example` 一一对应；新增变量必须同时更新 `.env.example`，否则其他成员
拿不到可运行配置。
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class ObjectStorageProvider(StrEnum):
    """对象存储供应商。

    M1 定为 Backblaze B2（`main` 的 `19901dc`）。枚举而非自由字符串，是为了让
    "业务层不直接依赖 B2"这条要求有一个可检查的边界：Provider 抽象层按此分支，
    业务代码不读这个字段。

    `MINIO` 仅用于无 B2 凭据时的本地离线开发，不是交付目标。
    """

    BACKBLAZE_B2 = "backblaze_b2"
    MINIO = "minio"


# 按文件类型分别限制大小：课件和逐字稿没有理由达到视频量级，统一放宽等于给
# 对象存储和 Worker 留了一个廉价的资源耗尽入口。
MAX_UPLOAD_BYTES: dict[str, int] = {
    "video": 4 * 1024 * 1024 * 1024,  # 4 GiB，一节课的原始录像
    "courseware": 128 * 1024 * 1024,  # 128 MiB
    "transcript": 32 * 1024 * 1024,  # 32 MiB
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env 里还有 Worker 与模型相关变量，不属于后端
        case_sensitive=False,
    )

    # ---------------- Runtime ----------------
    app_env: AppEnv = AppEnv.DEVELOPMENT
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    frontend_origin: str = Field(
        default="http://localhost:3000",
        description="CORS 允许来源。不使用通配符：带凭据的跨域请求下 * 无效，也放大攻击面。",
    )
    backend_url: str = "http://127.0.0.1:8100"

    # ---------------- Database ----------------
    database_url: SecretStr = Field(
        description="必须是异步驱动形式 postgresql+asyncpg://…（含口令，故为 SecretStr）。"
    )

    # ---------------- Authentication ----------------
    jwt_secret: SecretStr
    access_token_expire_minutes: int = Field(default=120, ge=5, le=1440)
    demo_account_password: SecretStr | None = Field(
        default=None,
        description="演示账号口令。为空时不注册演示账号——绝不回退到硬编码默认口令。",
    )

    # ---------------- Internal service auth ----------------
    # Worker 与 Agent 各持一个令牌，不共用。共用意味着 Agent 也能覆盖逐字稿、
    # Worker 也能写入教学结论，违反最小权限（PR #6 审查意见 4）。
    # 端点与身份的对应关系见 schemas/task.py 的 INTERNAL_ENDPOINT_SCOPES。
    worker_service_token: SecretStr = Field(
        description="Worker 回写任务状态与逐字稿的服务令牌，与教师 JWT 分开，不绑定账号。"
    )
    agent_service_token: SecretStr = Field(
        description="Agent 回写分析结论的服务令牌，权限范围小于 Worker 令牌。"
    )

    # ---------------- Local model ----------------
    # 资料上传前的复盘澄清与资料处理后的证据分析复用同一台 loopback-only
    # Ollama 服务，但使用不同的结构化契约和提示词。模型地址不允许由浏览器提供。
    local_model_chat_completions_url: str = "http://127.0.0.1:11434/v1/chat/completions"
    local_model_name: str = "qwen3.5:4b"
    local_model_reasoning_effort: Literal["none", "low", "medium", "high"] = "none"

    # ---------------- Object storage ----------------
    # M1 默认 Backblaze B2（成员 1 确定），走其 S3 兼容 API。变量名保持通用，
    # 换供应商不必改前端、数据库与 Worker。
    object_storage_provider: ObjectStorageProvider = ObjectStorageProvider.BACKBLAZE_B2
    object_storage_endpoint: str
    object_storage_region: str = "us-east-1"
    object_storage_bucket: str
    object_storage_access_key_id: SecretStr
    object_storage_secret_access_key: SecretStr
    object_storage_use_path_style: bool = Field(
        default=False,
        description="B2 的 S3 API 用 virtual-host 风格，保持 false；仅本地 MinIO 替代时设为 true。",
    )
    object_storage_presigned_url_ttl_seconds: int = Field(
        default=900,
        ge=60,
        le=3600,
        description="预签名 URL 有效期。上限 1 小时：限时是 ../../docs/product-and-technology-handbook.md 的强制要求，"
        "过长的签名等同于把对象长期公开。",
    )
    object_storage_retention_days: int = Field(
        default=7,
        ge=1,
        le=90,
        description="对象保留天数，超期由清理流程删除；删除需同时处理业务记录与审计状态。",
    )

    @field_validator("database_url")
    @classmethod
    def _require_async_driver(cls, value: SecretStr) -> SecretStr:
        url = value.get_secret_value()
        if not url.startswith("postgresql+asyncpg://"):
            # 只报格式要求，不回显 URL 本身——它含口令。
            raise ValueError(
                "DATABASE_URL 必须以 postgresql+asyncpg:// 开头；"
                "同步驱动会阻塞事件循环并拖垮连接池。"
            )
        return value

    @field_validator("jwt_secret")
    @classmethod
    def _require_strong_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET 至少 32 个字符；短密钥可被离线暴力破解。")
        return value

    @model_validator(mode="after")
    def _service_tokens_must_differ(self) -> Settings:
        """两个服务令牌不能填成同一个值。

        否则「拆分令牌」只是名义上的：拿着同一个字符串，Agent 依然能冒充 Worker
        覆盖逐字稿。启动时就拒绝，好过上线后才发现权限边界形同虚设。
        """
        if (
            self.worker_service_token.get_secret_value()
            == self.agent_service_token.get_secret_value()
        ):
            raise ValueError(
                "WORKER_SERVICE_TOKEN 与 AGENT_SERVICE_TOKEN 必须不同，"
                "否则服务身份无法区分，端点权限范围形同虚设。"
            )
        if self.is_production:
            frontend = urlparse(self.frontend_origin)
            if frontend.scheme != "https" or not frontend.netloc:
                raise ValueError("生产环境 FRONTEND_ORIGIN 必须是完整 HTTPS 地址。")
            storage = urlparse(self.object_storage_endpoint)
            if storage.scheme != "https" or not storage.netloc:
                raise ValueError("生产环境对象存储端点必须使用 HTTPS。")
            if self.demo_account_password is not None and len(
                self.demo_account_password.get_secret_value()
            ) < 16:
                raise ValueError("生产环境演示账号口令至少 16 个字符。")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION

    def max_upload_bytes(self, kind: str) -> int:
        """按 AssetKind 取上限；未知类型退回最严格的限制。"""
        return MAX_UPLOAD_BYTES.get(kind, min(MAX_UPLOAD_BYTES.values()))


@lru_cache
def get_settings() -> Settings:
    """进程内缓存一次。

    用 `lru_cache` 而不是模块级实例：模块级实例会在 import 时读 `.env`，让测试无法
    注入配置，也会让"缺配置"的错误发生在 import 阶段、堆栈难读。
    """
    return Settings()  # type: ignore[call-arg]
