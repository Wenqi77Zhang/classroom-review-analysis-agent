"""Owner-scoped report persistence with a server-side review gate."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import Settings
from backend.app.dependencies import get_app_settings, get_current_user, get_db
from backend.app.errors import NotFoundError
from backend.app.models import Report, User
from backend.app.repositories.reviews import get_report, get_report_for_export, upsert_report
from backend.app.schemas.analysis_report import (
    REPORTABLE_REVIEW_STATUSES,
    ReportExportFormat,
    ReportExportRequest,
    ReportExportResponse,
    ReportRead,
    ReportUpdate,
    ReviewStatus,
)
from backend.app.services.audit import record_audit_event
from backend.app.services.report_exports import render_report_export, report_export_metadata
from backend.app.services.storage import ObjectStorage, get_object_storage

router = APIRouter(tags=["reports"])
Db = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
Storage = Annotated[ObjectStorage, Depends(get_object_storage)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]


def _export_object_key(report: Report, extension: str) -> str:
    content_version = sha256(
        f"{report.title}\x00{report.content}".encode()
    ).hexdigest()[:16]
    return (
        f"owners/{report.owner_id}/classrooms/{report.classroom_id}/reports/"
        f"{report.id}/{content_version}.{extension}"
    )


def _expires_at(ttl_seconds: int) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=ttl_seconds)


def _report_read(report: Report) -> ReportRead:
    included_ids = [
        item.id
        for item in sorted(
            report.conclusions,
            key=lambda conclusion: (conclusion.created_at, conclusion.id),
        )
        if ReviewStatus(item.review_status) in REPORTABLE_REVIEW_STATUSES
    ]
    return ReportRead(
        id=report.id,
        classroom_id=report.classroom_id,
        title=report.title,
        content=report.content,
        included_conclusion_ids=included_ids,
        updated_at=report.updated_at,
    )


@router.get("/classrooms/{classroom_id}/report", response_model=ReportRead)
async def get_classroom_report(
    classroom_id: UUID,
    session: Db,
    user: CurrentUser,
) -> ReportRead:
    return _report_read(
        await get_report(session, owner_id=user.id, classroom_id=classroom_id)
    )


@router.put("/classrooms/{classroom_id}/report", response_model=ReportRead)
async def put_classroom_report(
    classroom_id: UUID,
    body: ReportUpdate,
    session: Db,
    user: CurrentUser,
) -> ReportRead:
    return _report_read(
        await upsert_report(
            session,
            owner_id=user.id,
            user=user,
            classroom_id=classroom_id,
            body=body,
        )
    )


@router.post(
    "/reports/{report_id}/export",
    response_model=ReportExportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def post_report_export(
    report_id: UUID,
    body: ReportExportRequest,
    session: Db,
    user: CurrentUser,
    storage: Storage,
    settings: AppSettings,
) -> ReportExportResponse:
    report = await get_report_for_export(session, owner_id=user.id, report_id=report_id)
    content, content_type, extension = render_report_export(
        body.format, title=report.title, content=report.content
    )
    object_key = _export_object_key(report, extension)
    await storage.put(object_key, content, content_type)
    report.export_object_key = object_key
    await session.flush()
    await record_audit_event(
        session,
        owner_id=user.id,
        actor_user_id=user.id,
        action="report.exported",
        resource_type="report",
        resource_id=report.id,
        details={"format": body.format.value},
    )
    return ReportExportResponse(
        format=body.format,
        download_url=await storage.presign_download(object_key),
        expires_at=_expires_at(settings.object_storage_presigned_url_ttl_seconds),
    )


@router.get("/reports/{report_id}/export/{export_format}", response_model=ReportExportResponse)
async def get_report_export(
    report_id: UUID,
    export_format: ReportExportFormat,
    session: Db,
    user: CurrentUser,
    storage: Storage,
    settings: AppSettings,
) -> ReportExportResponse:
    report = await get_report_for_export(session, owner_id=user.id, report_id=report_id)
    _, extension = report_export_metadata(export_format)
    object_key = _export_object_key(report, extension)
    if await storage.head(object_key) is None:
        raise NotFoundError("该格式的报告导出尚未创建。")
    return ReportExportResponse(
        format=export_format,
        download_url=await storage.presign_download(object_key),
        expires_at=_expires_at(settings.object_storage_presigned_url_ttl_seconds),
    )
