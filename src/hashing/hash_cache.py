"""Hash cache backed by the SQLite database.

A file is only re-hashed when its path, size and modification time have all
changed, which makes incremental scans orders of magnitude cheaper than the
first one.
"""

from __future__ import annotations

from typing import Optional

from ..core.logger import get_logger
from ..database.database import Database
from ..database.repositories.image_repository import ImageRepository
from ..models.image_model import ImageRecord

_log = get_logger("hashing.hash_cache")


class HashCache:
    """Persistent cache of previously computed hashes."""

    def __init__(self, database: Database) -> None:
        self._repository = ImageRepository(database)

    def lookup(self, path: str, size: int, modified_at: float) -> Optional[ImageRecord]:
        """Return the cached record for an unchanged file, else ``None``."""
        try:
            return self._repository.find_cached(path, size, modified_at)
        except Exception as exc:  # a cache miss must never abort a scan
            _log.debug("Cache lookup failed for %s: %s", path, exc)
            return None

    def store(self, record: ImageRecord) -> None:
        try:
            self._repository.insert(record)
        except Exception as exc:
            _log.debug("Cache store failed for %s: %s", record.path, exc)

    def store_many(self, records: list[ImageRecord]) -> int:
        try:
            return self._repository.insert_many(records)
        except Exception as exc:
            _log.debug("Batch cache store failed: %s", exc)
            return 0
