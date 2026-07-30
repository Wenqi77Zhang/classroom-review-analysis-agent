"""Owner-scoped presigned upload, verification, download, and deletion routes."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import Settings
from backend.app.dependencies import get_app_settings, get_current_user, get_db
from backend.app.errors import (
    PayloadTooLargeError,
    StateConflictError,
    ValidationFailedError,
)
from backend.app.models import Asset, Classroom, User
from backend.app.repositories.assets import asset_task_count, create_asset
from backend.app.schemas.task import (
    AssetCompleteRequest,
    AssetRead,
    DownloadUrlResponse,
    PresignRequest,
    PresignResponse,
    UploadStatus,
)
from backend.app.services.audit import record_audit_event
from backend.app.services.permissions import get_owned_or_404
from backend.app.services.storage import ObjectStorage, get_object_storage

router = APIRouter(tags=["uploads"])
Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Storage = Annotated[ObjectStorage, Depends(get_object_storage)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


def _safe_display_filename(filename: str) -> str:
    value = filename.strip().replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not value or value in {".", ".."} or _CONTROL_CHARACTERS.search(value):
        raise ValidationFailedError("文件名不合法。")
    return value


def _normalize_etag(value: str | None) -> str | None:
    return value.strip().strip('"') if value else None


@router.post(
    "/classrooms/{classroom_id}/uploads/presign",
    response_model=PresignResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_presign(
    classroom_id: UUID,
    body: PresignRequest,
    session: Db,
    user: CurrentUser,
    storage: Storage,
    settings: AppSettings,
) -> PresignResponse:
    await get_owned_or_404(session, Classroom, classroom_id, user.id)
    maximum = settings.max_upload_bytes(body.kind.value)
    if body.size_bytes > maximum:
        raise PayloadTooLargeError(
            "文件超出该类型允许大小。",
            details={"kind": body.kind.value, "max_bytes": maximum},
        )

    asset_id = uuid4()
    filename = _safe_display_filename(body.filename)
    object_key = f"owners/{user.id}/classrooms/{classroom_id}/assets/{asset_id}/source"
    await create_asset(
        session,
        asset_id=asset_id,
        owner_id=user.id,
        classroom_id=classroom_id,
        kind=body.kind,
        filename=filename,
        content_type=body.content_type.strip().lower(),
        size_bytes=body.size_bytes,
        object_key=object_key,
    )
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="asset.upload_requested",
        resource_type="asset",
        resource_id=asset_id,
        details={"kind": body.kind.value, "size_bytes": body.size_bytes},
    )
    upload_url = await storage.presign_upload(object_key, body.content_type.strip().lower())
    expires_at = datetime.now(UTC) + timedelta(
        seconds=settings.object_storage_presigned_url_ttl_seconds
    )
    return PresignResponse(
        asset_id=asset_id,
        object_key=object_key,
        upload_url=upload_url,
        headers={"Content-Type": body.content_type.strip().lower()},
        expires_at=expires_at,
    )


@router.post("/assets/{asset_id}/complete", response_model=AssetRead)
async def post_complete(
    asset_id: UUID,
    body: AssetCompleteRequest,
    session: Db,
    user: CurrentUser,
    storage: Storage,
) -> AssetRead:
    asset = await get_owned_or_404(session, Asset, asset_id, user.id)
    if UploadStatus(asset.upload_status) is UploadStatus.UPLOADED:
        return AssetRead.model_validate(asset)

    metadata = await storage.head(asset.object_key)
    problems: list[str] = []
    if metadata is None:
        problems.append("对象不存在")
    else:
        if metadata.size_bytes != asset.size_bytes:
            problems.append("文件大小不一致")
        if metadata.content_type.lower() != asset.content_type.lower():
            problems.append("Content-Type 不一致")
        expected_etag = _normalize_etag(body.etag)
        if expected_etag and metadata.etag and expected_etag != metadata.etag:
            problems.append("ETag 不一致")
        if body.checksum and metadata.checksum and body.checksum != metadata.checksum:
            problems.append("校验值不一致")

    if problems:
        asset.upload_status = UploadStatus.FAILED
        await record_audit_event(
            session,
            owner_id=user.id,
            actor_user_id=user.id,
            action="asset.upload_verification_failed",
            resource_type="asset",
            resource_id=asset.id,
            details={"failed_check_count": len(problems)},
        )
        await session.flush()
        raise ValidationFailedError(
            "上传文件核验失败。",
            details={"checks": problems},
            commit_changes=True,
        )

    assert metadata is not None
    asset.upload_status = UploadStatus.UPLOADED
    asset.etag = metadata.etag
    asset.checksum = metadata.checksum
    await session.flush()
    await session.refresh(asset)
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="asset.upload_verified",
        resource_type="asset",
        resource_id=asset.id,
    )
    return AssetRead.model_validate(asset)


@router.get("/assets/{asset_id}/download-url", response_model=DownloadUrlResponse)
async def get_download_url(
    asset_id: UUID,
    session: Db,
    user: CurrentUser,
    storage: Storage,
    settings: AppSettings,
) -> DownloadUrlResponse:
    asset = await get_owned_or_404(session, Asset, asset_id, user.id)
    if UploadStatus(asset.upload_status) is not UploadStatus.UPLOADED:
        raise StateConflictError("文件尚未通过上传核验。")
    url = await storage.presign_download(asset.object_key)
    return DownloadUrlResponse(
        url=url,
        expires_at=datetime.now(UTC)
        + timedelta(seconds=settings.object_storage_presigned_url_ttl_seconds),
    )


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: UUID,
    session: Db,
    user: CurrentUser,
    storage: Storage,
) -> Response:
    asset = await get_owned_or_404(session, Asset, asset_id, user.id)
    if await asset_task_count(session, asset.id, user.id):
        raise StateConflictError("文件已关联处理任务，不能删除。")
    await storage.delete(asset.object_key)
    asset_id = asset.id
    await session.delete(asset)
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="asset.deleted",
        resource_type="asset",
        resource_id=asset_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
