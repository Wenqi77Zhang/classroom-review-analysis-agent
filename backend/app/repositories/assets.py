"""Owner-scoped asset persistence operations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import Asset
from backend.app.schemas.task import AssetKind, UploadStatus


async def create_asset(
    session: AsyncSession,
    *,
    asset_id: UUID,
    owner_id: UUID,
    classroom_id: UUID,
    kind: AssetKind,
    filename: str,
    content_type: str,
    size_bytes: int,
    object_key: str,
) -> Asset:
    asset = Asset(
        id=asset_id,
        owner_id=owner_id,
        classroom_id=classroom_id,
        kind=kind,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        upload_status=UploadStatus.PENDING,
        object_key=object_key,
    )
    session.add(asset)
    await session.flush()
    return asset


async def asset_task_count(session: AsyncSession, asset_id: UUID, owner_id: UUID) -> int:
    from backend.app.models.processing import task_assets

    value = await session.scalar(
        select(func.count())
        .select_from(task_assets)
        .where(task_assets.c.asset_id == asset_id, task_assets.c.owner_id == owner_id)
    )
    return int(value or 0)
