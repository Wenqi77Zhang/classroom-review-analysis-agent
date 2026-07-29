"""任务与账号范围内的证据检索；不负责读取对象存储或加工媒体。"""

from __future__ import annotations

from collections.abc import Iterable

from agent.contracts import EvidenceItem
from backend.app.schemas.common import ResourceId


class EvidenceNotFoundError(LookupError):
    pass


class EvidenceRetriever:
    def __init__(
        self,
        evidence: Iterable[EvidenceItem],
        *,
        task_id: ResourceId,
        owner_id: ResourceId,
    ) -> None:
        scoped = [
            item for item in evidence if item.task_id == task_id and item.owner_id == owner_id
        ]
        self._items = {item.id: item for item in scoped}

    def all(self, *, limit: int = 200) -> list[EvidenceItem]:
        if not 1 <= limit <= 200:
            raise ValueError("limit 必须在 1 到 200 之间。")
        return list(self._items.values())[:limit]

    def get_many(self, evidence_ids: Iterable[ResourceId]) -> list[EvidenceItem]:
        result: list[EvidenceItem] = []
        seen: set[ResourceId] = set()
        for evidence_id in evidence_ids:
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            try:
                result.append(self._items[evidence_id])
            except KeyError as exc:
                raise EvidenceNotFoundError(
                    f"模型引用了当前任务中不存在的证据：{evidence_id}"
                ) from exc
        return result

    def search(self, query: str, *, limit: int = 20) -> list[EvidenceItem]:
        if not 1 <= limit <= 200:
            raise ValueError("limit 必须在 1 到 200 之间。")
        needle = query.strip().casefold()
        if not needle:
            return self.all(limit=limit)
        return [
            item
            for item in self._items.values()
            if needle in item.text.casefold()
            or needle in (item.translation or "").casefold()
        ][:limit]
