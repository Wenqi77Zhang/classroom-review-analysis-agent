"""Persistence boundary: in-memory for local runs, HTTP for integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

import httpx

from backend.app.schemas.task import (
    InternalTaskClaim,
    InternalTaskClaimRequest,
    InternalTaskHeartbeat,
    InternalTaskStateUpdate,
)
from backend.app.schemas.transcript import InternalTranscriptWrite
from worker.errors import WorkerError, WorkerErrorCode


class JobStore(Protocol):
    def update_state(self, task_id: UUID, update: InternalTaskStateUpdate) -> None: ...

    def save_transcript(self, task_id: UUID, transcript: InternalTranscriptWrite) -> None: ...


@dataclass(slots=True)
class LocalJobStore:
    events: dict[UUID, list[InternalTaskStateUpdate]] = field(default_factory=dict)
    transcripts: dict[UUID, InternalTranscriptWrite] = field(default_factory=dict)

    def update_state(self, task_id: UUID, update: InternalTaskStateUpdate) -> None:
        self.events.setdefault(task_id, []).append(update)

    def save_transcript(self, task_id: UUID, transcript: InternalTranscriptWrite) -> None:
        self.transcripts[task_id] = transcript


class HttpJobStore:
    """Client for member 3's frozen internal worker endpoints."""

    def __init__(
        self,
        base_url: str,
        service_token: str,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {service_token}"},
        )

    def _request(self, method: str, path: str, *, json: dict[str, object]) -> httpx.Response:
        try:
            response = self.client.request(method, path, json=json)
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise WorkerError(
                WorkerErrorCode.JOB_STORE_FAILED,
                f"后端内部接口调用失败：{method} {path}",
                retryable=True,
            ) from exc

    def claim(self, request: InternalTaskClaimRequest) -> InternalTaskClaim | None:
        response = self._request(
            "POST",
            "/api/internal/tasks/claim",
            json=request.model_dump(mode="json"),
        )
        if response.status_code == 204 or not response.content:
            return None
        return InternalTaskClaim.model_validate(response.json())

    def heartbeat(self, task_id: UUID, heartbeat: InternalTaskHeartbeat) -> None:
        self._request(
            "POST",
            f"/api/internal/tasks/{task_id}/heartbeat",
            json=heartbeat.model_dump(mode="json"),
        )

    def update_state(self, task_id: UUID, update: InternalTaskStateUpdate) -> None:
        self._request(
            "PATCH",
            f"/api/internal/tasks/{task_id}/state",
            json=update.model_dump(mode="json"),
        )

    def save_transcript(self, task_id: UUID, transcript: InternalTranscriptWrite) -> None:
        self._request(
            "POST",
            f"/api/internal/tasks/{task_id}/transcript",
            json=transcript.model_dump(mode="json"),
        )

    def close(self) -> None:
        self.client.close()
