"""Duplicate grouping and smart "keep this" selection."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from ..core.config import AppConfig
from ..core.constants import DuplicateType
from ..core.logger import get_logger
from ..models.duplicate_group import DuplicateGroup
from ..models.image_model import ImageRecord
from ..models.similarity_result import SimilarityResult

_log = get_logger("services.duplicate")


class UnionFind:
    """Disjoint-set forest used to merge related images into groups."""

    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, index: int) -> int:
        root = index
        while self._parent[root] != root:
            root = self._parent[root]
        # Path compression keeps near-constant amortised cost.
        while self._parent[index] != root:
            self._parent[index], index = root, self._parent[index]
        return root

    def union(self, first: int, second: int) -> None:
        root_a = self.find(first)
        root_b = self.find(second)
        if root_a != root_b:
            self._parent[root_b] = root_a


class SmartKeeper:
    """Ranks images inside a group to recommend which one should be kept.

    The ranking rewards high resolution, good quality (bytes per pixel), a
    sensible file size, original creation date and a clean file name, while
    penalising copies that look like exports or downloads.
    """

    # File name patterns that suggest a derived copy rather than an original.
    _COPY_NAME_HINTS = ("copy", "copy_", "edit", "resized", "compress", "export", "tmp", "untitled", "_small", "_low")

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self.config = config or AppConfig()

    def rank(self, records: Sequence[ImageRecord]) -> List[Tuple[float, ImageRecord]]:
        """Return ``(score, record)`` pairs sorted from best to worst."""
        scored = [(self._score(record), record) for record in records]
        return sorted(scored, key=lambda item: (-item[0], item[1].path.lower()))

    def recommend(self, records: Sequence[ImageRecord]) -> Optional[ImageRecord]:
        ranked = self.rank(records)
        return ranked[0][1] if ranked else None

    # ------------------------------------------------------------------
    # Individual criteria
    # ------------------------------------------------------------------

    def _score(self, record: ImageRecord) -> float:
        return (
            self._resolution_score(record)
            + self._quality_score(record)
            + self._size_score(record)
            + self._date_score(record)
            + self._name_score(record)
            + self._path_score(record)
        )

    @staticmethod
    def _resolution_score(record: ImageRecord) -> float:
        return min(40.0, record.megapixels * 6.0)

    @staticmethod
    def _quality_score(record: ImageRecord) -> float:
        """Bytes per pixel: lossless or lightly compressed files score higher."""
        pixels = record.width * record.height
        if pixels <= 0:
            return 0.0
        bytes_per_pixel = record.size / pixels
        # ~1.0 byte/px is typical of a high quality JPEG; 3+ is near-lossless.
        return min(25.0, 25.0 * bytes_per_pixel)

    @staticmethod
    def _size_score(record: ImageRecord) -> float:
        """Reasonable file sizes win; both empty and absurd files lose."""
        if record.size <= 0:
            return -10.0
        if record.size_mb > 100:
            return -5.0
        return 5.0

    @staticmethod
    def _date_score(record: ImageRecord) -> float:
        """Older creation dates suggest the original rather than an edit."""
        if record.created_at <= 0:
            return 0.0
        # Normalize against the Unix epoch in days.
        age_days = record.created_at / 86400.0
        return min(15.0, age_days / 365.25 * 0.4)

    def _name_score(self, record: ImageRecord) -> float:
        name = record.filename.lower()
        if any(hint in name for hint in self._COPY_NAME_HINTS):
            return -8.0
        # Camera-style names (IMG_1234, DSC01234) usually mean an untouched original.
        digits = sum(character.isdigit() for character in name)
        if 3 <= digits <= 8 and "_" in name:
            return 6.0
        return 2.0

    @staticmethod
    def _path_score(record: ImageRecord) -> float:
        path = record.path.lower()
        if "download" in path or "temp" in path or "cache" in path:
            return -6.0
        if "original" in path or "camera" in path or "dcim" in path:
            return 6.0
        return 0.0


class DuplicateService:
    """Turns pairwise similarity results into duplicate groups."""

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self.config = config or AppConfig()
        self.keeper = SmartKeeper(self.config)

    # ------------------------------------------------------------------
    # Exact duplicates
    # ------------------------------------------------------------------

    def group_exact(self, records: Iterable[ImageRecord], scan_id: Optional[int] = None) -> List[DuplicateGroup]:
        """Group files that share a SHA-256 digest (byte-identical content)."""
        by_hash: Dict[str, List[ImageRecord]] = {}
        for record in records:
            if not record.sha256 or not record.is_readable:
                continue
            by_hash.setdefault(record.sha256, []).append(record)

        groups: List[DuplicateGroup] = []
        for members in by_hash.values():
            if len(members) < 2:
                continue
            keeper = self.keeper.recommend(members)
            group = DuplicateGroup(
                scan_id=scan_id,
                group_type=DuplicateType.EXACT,
                similarity_score=100.0,
                items=list(members),
                keep_id=keeper.id if keeper else members[0].id,
            )
            group.sort_by_rank()
            groups.append(group)
        return groups

    # ------------------------------------------------------------------
    # Similar images
    # ------------------------------------------------------------------

    def group_similar(
        self,
        records: Sequence[ImageRecord],
        results: Iterable[SimilarityResult],
        scan_id: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> List[DuplicateGroup]:
        """Cluster related images with union-find over the pairwise results."""
        threshold = threshold if threshold is not None else self.config.similarity.similar_threshold

        index_by_id = {record.id: position for position, record in enumerate(records)}
        union_find = UnionFind(len(records))
        best_score: Dict[int, float] = {}

        for result in results:
            position_a = index_by_id.get(result.image_a_id)
            position_b = index_by_id.get(result.image_b_id)
            if position_a is None or position_b is None:
                continue
            if result.score < threshold:
                continue
            union_find.union(position_a, position_b)
            for position in (position_a, position_b):
                image_id = records[position].id
                best_score[image_id] = max(best_score.get(image_id, 0.0), result.score)

        clusters: Dict[int, List[ImageRecord]] = {}
        for position, record in enumerate(records):
            root = union_find.find(position)
            clusters.setdefault(root, []).append(record)

        groups: List[DuplicateGroup] = []
        for members in clusters.values():
            if len(members) < 2:
                continue
            score = min(best_score.get(record.id, threshold) for record in members)
            keeper = self.keeper.recommend(members)
            group = DuplicateGroup(
                scan_id=scan_id,
                group_type=DuplicateType.SIMILAR,
                similarity_score=round(score, 2),
                items=members,
                keep_id=keeper.id if keeper else members[0].id,
            )
            group.sort_by_rank()
            groups.append(group)
        return groups

    # ------------------------------------------------------------------
    # Aggregates
    # ------------------------------------------------------------------

    @staticmethod
    def recoverable_space(groups: Iterable[DuplicateGroup]) -> int:
        return sum(group.wasted_bytes for group in groups)

    @staticmethod
    def duplicate_count(groups: Iterable[DuplicateGroup]) -> int:
        return sum(len(group.duplicates) for group in groups)
