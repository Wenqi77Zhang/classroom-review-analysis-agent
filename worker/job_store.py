"""Persistence boundary: in-memory for local runs, HTTP for integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from uuid import UUID

import httpx

from backend.app.schemas.task import (
    InternalAssetRead,
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


class ClaimingJobStore(JobStore, Protocol):
    def claim(self, request: InternalTaskClaimRequest) -> InternalTaskClaim | None: ...

    def heartbeat(self, task_id: UUID, heartbeat: InternalTaskHeartbeat) -> None: ...


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
        transport: httpx.BaseTransport | None = None,
        download_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {service_token}"},
            transport=transport,
        )
        # 对象下载必须使用独立、无 Authorization 默认头的客户端。否则 Worker
        # 服务令牌会被转发到 B2/MinIO，造成跨服务凭据泄露。
        self.download_client = httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=False,
            transport=download_transport,
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

    def download_asset(self, asset: InternalAssetRead, target: Path) -> None:
        received = 0
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with self.download_client.stream("GET", asset.download_url) as response:
                response.raise_for_status()
                expected_etag = self._normalize_etag(asset.verified_etag)
                response_etag = self._normalize_etag(response.headers.get("etag"))
                if expected_etag is not None and response_etag != expected_etag:
                    raise WorkerError(
                        WorkerErrorCode.OBJECT_DOWNLOAD_FAILED,
                        "对象下载 ETag 与上传核验结果不一致。",
                        retryable=True,
                    )
                with target.open("wb") as output:
                    for chunk in response.iter_bytes():
                        received += len(chunk)
                        if received > asset.size_bytes:
                            raise WorkerError(
                                WorkerErrorCode.OBJECT_DOWNLOAD_FAILED,
                                "对象下载大小超过后端登记值。",
                                retryable=True,
                            )
                        output.write(chunk)
            if received != asset.size_bytes:
                raise WorkerError(
                    WorkerErrorCode.OBJECT_DOWNLOAD_FAILED,
                    "对象下载大小与后端登记值不一致。",
                    retryable=True,
                )
        except WorkerError:
            self._remove_partial_download(target)
            raise
        except (httpx.HTTPError, OSError):
            self._remove_partial_download(target)
            raise WorkerError(
                WorkerErrorCode.OBJECT_DOWNLOAD_FAILED,
                "无法从限时对象地址下载课堂视频。",
                retryable=True,
            ) from None

    @staticmethod
    def _normalize_etag(value: str | None) -> str | None:
        return value.strip().strip('"') if value else None

    @staticmethod
    def _remove_partial_download(target: Path) -> None:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            # 外层下载临时目录仍会执行递归清理；不得让清理异常覆盖原始下载错误。
            pass

    def close(self) -> None:
        self.client.close()
        self.download_client.close()
