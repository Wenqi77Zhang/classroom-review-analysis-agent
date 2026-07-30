"""统一的结构化模型调用接口与 OpenAI-compatible HTTP 基础实现。"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ModelProviderError(RuntimeError):
    """可安全向上层记录的模型错误；消息不包含密钥或响应正文。"""


@dataclass(frozen=True, slots=True)
class ModelRequest:
    system_prompt: str
    user_prompt: str
    trace_id: str
    response_schema: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ModelResponse:
    data: dict[str, Any]
    model_name: str
    latency_ms: int
    usage: dict[str, int] = field(default_factory=dict)


class ModelProvider(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    async def generate_structured(self, request: ModelRequest) -> ModelResponse: ...


class OpenAICompatibleProvider(ModelProvider):
    """最小 HTTP 适配器；云端与本地端点的安全约束由子类负责。"""

    def __init__(
        self,
        *,
        endpoint: str,
        model: str,
        api_key: str | None,
        timeout_seconds: float = 60.0,
        reasoning_effort: Literal["none", "low", "medium", "high"] | None = None,
    ) -> None:
        if not model.strip():
            raise ValueError("model 不能为空。")
        if not 1 <= timeout_seconds <= 600:
            raise ValueError("timeout_seconds 必须在 1 到 600 之间。")
        if reasoning_effort not in {None, "none", "low", "medium", "high"}:
            raise ValueError("reasoning_effort 必须是 none、low、medium 或 high。")
        self._endpoint = endpoint
        self._model = model
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._reasoning_effort = reasoning_effort

    @property
    def model_name(self) -> str:
        return self._model

    async def generate_structured(self, request: ModelRequest) -> ModelResponse:
        started = perf_counter()
        raw = await asyncio.to_thread(self._post, request)
        latency_ms = round((perf_counter() - started) * 1000)
        try:
            choice = raw["choices"][0]
            content = choice["message"]["content"]
            data = json.loads(content) if isinstance(content, str) else content
            if not isinstance(data, dict):
                raise TypeError("结构化内容不是 JSON object")
            usage_raw = raw.get("usage") or {}
            usage = {
                key: int(value)
                for key, value in usage_raw.items()
                if isinstance(value, int) and not isinstance(value, bool)
            }
            return ModelResponse(
                data=data,
                model_name=str(raw.get("model") or self._model),
                latency_ms=latency_ms,
                usage=usage,
            )
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ModelProviderError("模型返回不符合结构化响应契约。") from exc

    def _post(self, request: ModelRequest) -> dict[str, Any]:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "classroom_analysis",
                    "strict": True,
                    "schema": self._prepare_response_schema(request.response_schema),
                },
            },
            "temperature": 0,
        }
        if self._reasoning_effort is not None:
            payload["reasoning_effort"] = self._reasoning_effort
        headers = {
            "Content-Type": "application/json",
            "X-Trace-Id": request.trace_id,
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        http_request = Request(
            self._endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(http_request, timeout=self._timeout_seconds) as response:
                body = response.read(4 * 1024 * 1024 + 1)
        except HTTPError as exc:
            raise ModelProviderError(f"模型服务返回 HTTP {exc.code}。") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ModelProviderError("模型服务当前不可用。") from exc
        if len(body) > 4 * 1024 * 1024:
            raise ModelProviderError("模型响应超过 4 MiB 安全上限。")
        try:
            decoded = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelProviderError("模型服务返回了无效 JSON。") from exc
        if not isinstance(decoded, dict):
            raise ModelProviderError("模型服务响应不是 JSON object。")
        return decoded

    def _prepare_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Allow provider-specific generation schemas; callers still validate the full schema."""
        return schema
