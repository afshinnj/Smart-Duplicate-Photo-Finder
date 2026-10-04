"""Domain model for a group of duplicate/similar images."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..core.constants import DuplicateType, rate_similarity
from .image_model import ImageRecord


@dataclass
class DuplicateGroup:
    """A set of two or more images that are considered the same content."""

    id: Optional[int] = None
    scan_id: Optional[int] = None
    group_type: DuplicateType = DuplicateType.SIMILAR
    similarity_score: float = 100.0
    items: List[ImageRecord] = field(default_factory=list)
    keep_id: Optional[int] = None  # smart-selection recommendation

    @property
    def rating(self):
        return rate_similarity(self.similarity_score)

    @property
    def is_exact(self) -> bool:
        return self.group_type == DuplicateType.EXACT

    @property
    def wasted_bytes(self) -> int:
        """Space that would be recovered by keeping only the best item."""
        if len(items := self.items) < 2:
            return 0
        keeper = self.keeper
        return sum(item.size for item in items if item.id != keeper.id)

    @property
    def keeper(self) -> ImageRecord:
        """The recommended item to keep (first item by default)."""
        for item in self.items:
            if item.id == self.keep_id:
                return item
        return self.items[0]

    @property
    def duplicates(self) -> List[ImageRecord]:
        keeper_id = self.keeper.id
        return [item for item in self.items if item.id != keeper_id]

    def sort_by_rank(self) -> None:
        """Sort items so the recommended keeper comes first."""
        if self.keep_id is None:
            return
        self.items.sort(key=lambda item: item.id != self.keep_id)

    def add(self, record: ImageRecord) -> None:
        if all(existing.id != record.id for existing in self.items):
            self.items.append(record)


@dataclass
class GroupSummary:
    """Lightweight aggregate used by the results UI."""

    group_id: int
    group_type: DuplicateType
    similarity_score: float
    item_count: int
    total_size: int
    wasted_size: int
    keeper_path: str
    keeper_resolution: str
