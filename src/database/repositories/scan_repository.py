"""Data access for duplicate groups, scan sessions and undo records."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Sequence

from ...core.constants import CleanupMethod, DuplicateType, ScanStatus
from ...models.duplicate_group import DuplicateGroup
from ...models.scan_session import ScanSession
from ..database import Database


class ScanRepository:
    """Persistence of scan sessions."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def create(self, session: ScanSession) -> int:
        cursor = self._db.execute(
            "INSERT INTO scan_sessions (start_time, folders, status) VALUES (?, ?, ?)",
            (
                session.start_time.isoformat() if session.start_time else datetime.now().isoformat(),
                _dump_folders(session.folders),
                session.status.value,
            ),
        )
        self._db.commit()
        session_id = int(cursor.lastrowid)
        session.id = session_id
        return session_id

    def update(self, session: ScanSession) -> None:
        if session.id is None:
            return
        self._db.execute(
            "UPDATE scan_sessions SET start_time = ?, end_time = ?, folders = ?, "
            "files_scanned = ?, images_found = ?, duplicates_found = ?, "
            "space_recoverable = ?, status = ?, error = ? WHERE id = ?",
            (
                session.start_time.isoformat() if session.start_time else None,
                session.end_time.isoformat() if session.end_time else None,
                _dump_folders(session.folders),
                session.files_scanned,
                session.images_found,
                session.duplicates_found,
                session.space_recoverable,
                session.status.value,
                session.error,
                session.id,
            ),
        )
        self._db.commit()

    def finish(
        self,
        session_id: int,
        status: ScanStatus,
        files_scanned: int,
        images_found: int,
        duplicates_found: int,
        space_recoverable: int,
        error: Optional[str] = None,
    ) -> None:
        self._db.execute(
            "UPDATE scan_sessions SET end_time = ?, status = ?, files_scanned = ?, "
            "images_found = ?, duplicates_found = ?, space_recoverable = ?, error = ? "
            "WHERE id = ?",
            (
                datetime.now().isoformat(),
                status.value,
                files_scanned,
                images_found,
                duplicates_found,
                space_recoverable,
                error,
                session_id,
            ),
        )
        self._db.commit()

    def list_recent(self, limit: int = 50) -> List[ScanSession]:
        rows = self._db.query(
            "SELECT * FROM scan_sessions ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [self._row_to_session(row) for row in rows]

    def get(self, session_id: int) -> Optional[ScanSession]:
        row = self._db.query_one("SELECT * FROM scan_sessions WHERE id = ?", (session_id,))
        return self._row_to_session(row) if row else None

    def delete(self, session_id: int) -> None:
        self._db.execute("DELETE FROM scan_sessions WHERE id = ?", (session_id,))
        self._db.commit()

    @staticmethod
    def _row_to_session(row) -> ScanSession:
        import json

        start = row["start_time"]
        end = row["end_time"]
        return ScanSession(
            id=row["id"],
            start_time=datetime.fromisoformat(start) if start else None,
            end_time=datetime.fromisoformat(end) if end else None,
            folders=json.loads(row["folders"] or "[]"),
            files_scanned=row["files_scanned"],
            images_found=row["images_found"],
            duplicates_found=row["duplicates_found"],
            space_recoverable=row["space_recoverable"],
            status=ScanStatus(row["status"]),
            error=row["error"],
        )


def _dump_folders(folders: Sequence[str]) -> str:
    import json

    return json.dumps(list(folders), ensure_ascii=False)


class GroupRepository:
    """Persistence of duplicate groups and their members."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def store_group(self, group: DuplicateGroup, image_repo: ImageRepository) -> Optional[int]:
        """Persist a group together with its items in one transaction."""
        if group.scan_id is None or not group.items:
            return None

        with self._db.lock:
            try:
                cursor = self._db.execute(
                    "INSERT INTO duplicate_groups (scan_id, group_type, similarity_score, keep_id) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        group.scan_id,
                        group.group_type.value,
                        group.similarity_score,
                        group.keep_id,
                    ),
                )
                group_id = int(cursor.lastrowid)
                group.id = group_id

                self._db.executemany(
                    "INSERT OR IGNORE INTO group_items (group_id, image_id) VALUES (?, ?)",
                    [(group_id, item.id) for item in group.items if item.id is not None],
                )
                self._db.commit()
                return group_id
            except Exception:
                self._db.commit()
                return None

    def store_groups(
        self, groups: Sequence[DuplicateGroup], image_repo: ImageRepository
    ) -> int:
        stored = 0
        for group in groups:
            if self.store_group(group, image_repo) is not None:
                stored += 1
        return stored

    def group_count(self, scan_id: Optional[int] = None) -> int:
        if scan_id is None:
            row = self._db.query_one("SELECT COUNT(*) AS total FROM duplicate_groups")
        else:
            row = self._db.query_one(
                "SELECT COUNT(*) AS total FROM duplicate_groups WHERE scan_id = ?", (scan_id,)
            )
        return int(row["total"]) if row else 0

    def load_groups(self, scan_id: int, image_repo: ImageRepository) -> List[DuplicateGroup]:
        rows = self._db.query(
            "SELECT * FROM duplicate_groups WHERE scan_id = ? ORDER BY similarity_score DESC, id",
            (scan_id,),
        )
        groups: List[DuplicateGroup] = []
        for row in rows:
            group = DuplicateGroup(
                id=row["id"],
                scan_id=row["scan_id"],
                group_type=DuplicateType(row["group_type"]),
                similarity_score=row["similarity_score"],
                keep_id=row["keep_id"],
            )
            item_rows = self._db.query(
                "SELECT image_id FROM group_items WHERE group_id = ?", (row["id"],)
            )
            records = image_repo.get_by_ids([item["image_id"] for item in item_rows])
            by_id = {record.id: record for record in records}
            for item in item_rows:
                record = by_id.get(item["image_id"])
                if record is not None:
                    group.items.append(record)
            group.sort_by_rank()
            groups.append(group)
        return groups

    def delete_groups_for_scan(self, scan_id: int) -> None:
        self._db.execute("DELETE FROM duplicate_groups WHERE scan_id = ?", (scan_id,))
        self._db.commit()


class DeletedFileRepository:
    """Undo bookkeeping for the cleanup service."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def add(
        self,
        image_id: Optional[int],
        original_path: str,
        backup_path: Optional[str],
        method: CleanupMethod,
        size: int,
    ) -> int:
        cursor = self._db.execute(
            "INSERT INTO deleted_files (image_id, original_path, backup_path, method, size) "
            "VALUES (?, ?, ?, ?, ?)",
            (image_id, original_path, backup_path, method.value, size),
        )
        self._db.commit()
        return int(cursor.lastrowid)

    def mark_restored(self, record_id: int) -> None:
        self._db.execute(
            "UPDATE deleted_files SET restored = 1 WHERE id = ?", (record_id,)
        )
        self._db.commit()

    def pending(self, limit: int = 100) -> List[dict]:
        rows = self._db.query(
            "SELECT * FROM deleted_files WHERE restored = 0 ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(row) for row in rows]

    def pending_count(self) -> int:
        row = self._db.query_one(
            "SELECT COUNT(*) AS total FROM deleted_files WHERE restored = 0"
        )
        return int(row["total"]) if row else 0

    def pending_size(self) -> int:
        row = self._db.query_one(
            "SELECT COALESCE(SUM(size), 0) AS total FROM deleted_files WHERE restored = 0"
        )
        return int(row["total"]) if row else 0
