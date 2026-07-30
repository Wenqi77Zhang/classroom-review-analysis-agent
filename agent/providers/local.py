"""私有课堂的本地模型 Provider；拒绝把私有内容路由到远程主机。"""

from ipaddress import ip_address
from typing import Any, Literal
from urllib.parse import urlparse

from agent.providers.base import OpenAICompatibleProvider


def _is_loopback(hostname: str | None) -> bool:
    if hostname == "localhost":
        return True
    if hostname is None:
        return False
    try:
        return ip_address(hostname).is_loopback
    except ValueError:
        return False


class LocalModelProvider(OpenAICompatibleProvider):
    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        timeout_seconds: float = 120.0,
        reasoning_effort: Literal["none", "low", "medium", "high"] | None = "none",
    ) -> None:
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not _is_loopback(parsed.hostname):
            raise ValueError("本地模型 endpoint 必须指向 localhost 或 loopback 地址。")
        super().__init__(
            endpoint=endpoint,
            model=model,
            api_key=None,
            timeout_seconds=timeout_seconds,
            # Qwen3.5 等推理模型若先输出长篇隐藏推理，可能在本地有限上下文中
            # 尚未生成结构化正文就耗尽预算。调用方仍可按模型能力显式覆盖。
            reasoning_effort=reasoning_effort,
        )

    def _prepare_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Remove constraints Ollama 0.32 cannot compile into a response grammar.

        The orchestrator still validates the returned object against the complete Pydantic
        schema, so this only affects model-side generation guidance, not the evidence gate.
        """
        unsupported = {
            "description",
            "format",
            "maxItems",
            "maxLength",
            "minItems",
            "minLength",
            "title",
        }

        def visit(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: visit(item) for key, item in value.items() if key not in unsupported}
            if isinstance(value, list):
                return [visit(item) for item in value]
            return value

        return visit(schema)
