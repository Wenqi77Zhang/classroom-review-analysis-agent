"""Agent 与后端之间的最小权限 HTTP 边界。"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

import httpx

from backend.app.schemas.agent_runtime import (
    InternalAgentClaimRequest,
    InternalAgentHeartbeat,
    InternalAgentTaskClaim,
)
from backend.app.schemas.analysis_report import InternalConclusionBatchWrite
from backend.app.schemas.task import InternalTaskStateUpdate


class AgentJobStoreError(RuntimeError):
    """不包含响应正文、令牌或课堂文本的后端调用错误。"""


class AgentJobStore(Protocol):
    def claim(self, request: InternalAgentClaimRequest) -> InternalAgentTaskClaim | None: ...

    def heartbeat(self, task_id: UUID, heartbeat: InternalAgentHeartbeat) -> None: ...

    def update_state(self, task_id: UUID, update: InternalTaskStateUpdate) -> None: ...

    def save_conclusions(
        self,
        task_id: UUID,
        conclusions: InternalConclusionBatchWrite,
    ) -> None: ...


class HttpAgentJobStore:
    """仅使用 Agent 服务令牌调用内部 Agent 端点。"""

    def __init__(
        self,
        base_url: str,
        service_token: str,
        *,
        timeout_seconds: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not service_token:
            raise ValueError("AGENT_SERVICE_TOKEN 未配置。")
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {service_token}"},
            transport=transport,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object],
    ) -> httpx.Response:
        try:
            response = self._client.request(method, path, json=json)
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise AgentJobStoreError(
                f"后端内部接口调用失败：{method} {path}"
            ) from exc

    def claim(self, request: InternalAgentClaimRequest) -> InternalAgentTaskClaim | None:
        response = self._request(
            "POST",
            "/api/internal/agent/tasks/claim",
            json=request.model_dump(mode="json"),
        )
        if response.status_code == 204 or not response.content:
            return None
        try:
            payload = response.json()
            if payload is None:
                return None
            return InternalAgentTaskClaim.model_validate(payload)
        except (ValueError, TypeError) as exc:
            raise AgentJobStoreError("后端返回的 Agent 任务包不符合契约。") from exc

    def heartbeat(self, task_id: UUID, heartbeat: InternalAgentHeartbeat) -> None:
        self._request(
            "POST",
            f"/api/internal/agent/tasks/{task_id}/heartbeat",
            json=heartbeat.model_dump(mode="json"),
        )

    def update_state(self, task_id: UUID, update: InternalTaskStateUpdate) -> None:
        self._request(
            "PATCH",
            f"/api/internal/tasks/{task_id}/state",
            json=update.model_dump(mode="json"),
        )

    def save_conclusions(
        self,
        task_id: UUID,
        conclusions: InternalConclusionBatchWrite,
    ) -> None:
        self._request(
            "POST",
            f"/api/internal/tasks/{task_id}/conclusions",
            json=conclusions.model_dump(mode="json"),
        )

    def close(self) -> None:
        self._client.close()
