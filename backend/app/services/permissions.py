"""Owner-scoped database access helpers.

Cross-account access deliberately returns NotFoundError, never PermissionDeniedError, so callers
cannot use response status to discover whether another account owns a guessed UUID.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import Base
from backend.app.errors import NotFoundError


async def get_owned_or_404[OwnedModel: Base](
    session: AsyncSession,
    model: type[OwnedModel],
    resource_id: UUID,
    owner_id: UUID,
) -> OwnedModel:
    if not hasattr(model, "owner_id"):
        raise TypeError(f"{model.__name__} is not an owner-scoped model")
    result = await session.scalar(
        select(model).where(model.id == resource_id, model.owner_id == owner_id)  # type: ignore[attr-defined]
    )
    if result is None:
        raise NotFoundError()
    return result


def assert_same_owner(owner_id: UUID, *resources: Any) -> None:
    """Reject cross-owner object graphs before they are flushed.

    PostgreSQL foreign keys verify that referenced rows exist, but a normal FK cannot prove that
    Asset.owner_id equals Classroom.owner_id. Repositories call this for every cross-table write.
    """
    if any(getattr(resource, "owner_id", None) != owner_id for resource in resources):
        raise NotFoundError()
