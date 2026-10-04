"""Data access for the ``images`` table."""

from __future__ import annotations

import json
from typing import Iterable, List, Optional, Sequence

from ...models.image_model import ImageRecord
from ...models.scan_session import ScanSession
from ..database import Database


class ImageRepository:
    """Insert, cache and query image records."""

    def __init__(self, database: Database) -> None:
        self._db = database

    _INSERT_SQL = (
        "INSERT INTO images (path, filename, extension, size, width, height, "
        "created_at, modified_at, sha256, ahash, dhash, phash, whash, "
        "embedding, scan_id, error) "
        "VALUES (:path, :filename, :extension, :size, :width, :height, "
        ":created_at, :modified_at, :sha256, :ahash, :dhash, :phash, :whash, "
        ":embedding, :scan_id, :error)"
    )

    @staticmethod
    def _row_to_record(row) -> ImageRecord:
        return ImageRecord(
            id=row["id"],
            path=row["path"],
            filename=row["filename"],
            extension=row["extension"],
            size=row["size"],
            width=row["width"],
            height=row["height"],
            created_at=row["created_at"],
            modified_at=row["modified_at"],
            sha256=row["sha256"],
            ahash=row["ahash"],
            dhash=row["dhash"],
            phash=row["phash"],
            whash=row["whash"],
            embedding=row["embedding"],
            scan_id=row["scan_id"],
            error=row["error"],
        )

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def insert(self, record: ImageRecord) -> Optional[int]:
        """Insert one record and return its new id."""
        try:
            cursor = self._db.execute(self._INSERT_SQL, self._record_params(record))
            self._db.commit()
            return cursor.lastrowid
        except Exception:
            return None

    def insert_many(self, records: Sequence[ImageRecord]) -> int:
        """Insert a batch of records, returning the number stored."""
        if not records:
            return 0
        params = [self._record_params(record) for record in records]
        try:
            self._db.executemany(self._INSERT_SQL, params)
            self._db.commit()
            return len(params)
        except Exception:
            # Fall back to row-by-row inserts so one bad file cannot abort the
            # whole batch.
            stored = 0
            for record in records:
                if self.insert(record) is not None:
                    stored += 1
            return stored

    @staticmethod
    def _record_params(record: ImageRecord) -> dict:
        return {
            "path": record.path,
            "filename": record.filename,
            "extension": record.extension,
            "size": record.size,
            "width": record.width,
            "height": record.height,
            "created_at": record.created_at,
            "modified_at": record.modified_at,
            "sha256": record.sha256,
            "ahash": record.ahash,
            "dhash": record.dhash,
            "phash": record.phash,
            "whash": record.whash,
            "embedding": record.embedding,
            "scan_id": record.scan_id,
            "error": record.error,
        }

    def insert_and_assign_ids(self, records: Sequence[ImageRecord]) -> None:
        """Insert records one-by-one and store the assigned ids on each object.

        ``executemany`` cannot report per-row ids, but the grouping stage needs
        them, so inserts run inside a transaction that is committed in chunks.
        """
        if not records:
            return
        import sqlite3

        with self._db.lock:
            connection = self._db.connection
            for index, record in enumerate(records, start=1):
                try:
                    cursor = connection.execute(self._INSERT_SQL, self._record_params(record))
                    record.id = cursor.lastrowid
                except sqlite3.IntegrityError:
                    record.id = self._existing_id(record)
                if index % 1000 == 0:
                    connection.commit()
            connection.commit()

    def _existing_id(self, record: ImageRecord) -> Optional[int]:
        row = self._db.query_one(
            "SELECT id FROM images WHERE path = ? AND size = ? AND modified_at = ? "
            "ORDER BY id DESC LIMIT 1",
            (record.path, record.size, record.modified_at),
        )
        return int(row["id"]) if row else None

    def update_scan_ids(self, records: Sequence[ImageRecord]) -> None:
        """Reassign cached records to the current scan session."""
        if not records:
            return
        self._db.executemany(
            "UPDATE images SET scan_id = ? WHERE id = ?",
            [(record.scan_id, record.id) for record in records if record.id is not None],
        )
        self._db.commit()

    def update_hashes(self, record: ImageRecord) -> None:
        if record.id is None:
            return
        self._db.execute(
            "UPDATE images SET sha256 = :sha256, ahash = :ahash, dhash = :dhash, "
            "phash = :phash, whash = :whash, embedding = :embedding, "
            "width = :width, height = :height, error = :error WHERE id = :id",
            {
                "sha256": record.sha256,
                "ahash": record.ahash,
                "dhash": record.dhash,
                "phash": record.phash,
                "whash": record.whash,
                "embedding": record.embedding,
                "width": record.width,
                "height": record.height,
                "error": record.error,
                "id": record.id,
            },
        )
        self._db.commit()

    # ------------------------------------------------------------------
    # Cache lookups
    # ------------------------------------------------------------------

    def find_cached(self, path: str, size: int, modified_at: float) -> Optional[ImageRecord]:
        """Return a cached record only if the file has not changed."""
        row = self._db.query_one(
            "SELECT * FROM images WHERE path = ? AND size = ? AND modified_at = ? "
            "ORDER BY id DESC LIMIT 1",
            (path, size, modified_at),
        )
        return self._row_to_record(row) if row else None

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def count_for_scan(self, scan_id: int) -> int:
        row = self._db.query_one(
            "SELECT COUNT(*) AS total FROM images WHERE scan_id = ?", (scan_id,)
        )
        return int(row["total"]) if row else 0

    def get_by_id(self, image_id: int) -> Optional[ImageRecord]:
        row = self._db.query_one("SELECT * FROM images WHERE id = ?", (image_id,))
        return self._row_to_record(row) if row else None

    def get_by_ids(self, image_ids: Iterable[int]) -> List[ImageRecord]:
        ids = list(image_ids)
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = self._db.query(
            f"SELECT * FROM images WHERE id IN ({placeholders})", tuple(ids)
        )
        return [self._row_to_record(row) for row in rows]

    def list_for_scan(self, scan_id: int, limit: int = 0, offset: int = 0) -> List[ImageRecord]:
        sql = "SELECT * FROM images WHERE scan_id = ? ORDER BY id"
        params: tuple = (scan_id,)
        if limit > 0:
            sql += " LIMIT ? OFFSET ?"
            params = (scan_id, limit, offset)
        rows = self._db.query(sql, params)
        return [self._row_to_record(row) for row in rows]

    def list_with_hashes(self, scan_id: int) -> List[ImageRecord]:
        """All records of a scan that were successfully hashed."""
        rows = self._db.query(
            "SELECT * FROM images WHERE scan_id = ? AND phash IS NOT NULL AND error IS NULL",
            (scan_id,),
        )
        return [self._row_to_record(row) for row in rows]

    def delete_for_scan(self, scan_id: int) -> int:
        cursor = self._db.execute("DELETE FROM images WHERE scan_id = ?", (scan_id,))
        self._db.commit()
        return cursor.rowcount

    # ------------------------------------------------------------------
    # Aggregates
    # ------------------------------------------------------------------

    def total_images(self) -> int:
        row = self._db.query_one("SELECT COUNT(*) AS total FROM images")
        return int(row["total"]) if row else 0

    def total_size(self) -> int:
        row = self._db.query_one("SELECT COALESCE(SUM(size), 0) AS total FROM images")
        return int(row["total"]) if row else 0
