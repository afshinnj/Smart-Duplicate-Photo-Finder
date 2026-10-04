"""Scan history access for the history page and the dashboard."""

from __future__ import annotations

from typing import List, Optional

from ..core.logger import get_logger
from ..database.database import Database
from ..database.repositories.image_repository import ImageRepository
from ..database.repositories.scan_repository import GroupRepository, ScanRepository
from ..models.duplicate_group import DuplicateGroup
from ..models.scan_session import ScanSession

_log = get_logger("services.history")


class HistoryService:
    """Reads and prunes past scan sessions."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.scan_repository = ScanRepository(database)
        self.group_repository = GroupRepository(database)
        self.image_repository = ImageRepository(database)

    def list_sessions(self, limit: int = 50) -> List[ScanSession]:
        """Most recent sessions first."""
        return self.scan_repository.list_recent(limit)

    def get_session(self, session_id: int) -> Optional[ScanSession]:
        return self.scan_repository.get(session_id)

    def load_groups(self, session_id: int) -> List[DuplicateGroup]:
        """Reload the groups produced by a finished scan."""
        return self.group_repository.load_groups(session_id, self.image_repository)

    def delete_session(self, session_id: int) -> None:
        """Remove a session together with its groups and image records."""
        self.group_repository.delete_groups_for_scan(session_id)
        self.image_repository.delete_for_scan(session_id)
        self.scan_repository.delete(session_id)
        _log.info("Deleted scan session %s", session_id)

    def latest_session(self) -> Optional[ScanSession]:
        sessions = self.list_sessions(limit=1)
        return sessions[0] if sessions else None

    def total_images(self) -> int:
        return self.image_repository.total_images()

    def total_size(self) -> int:
        return self.image_repository.total_size()

    def total_groups(self) -> int:
        return self.group_repository.group_count()
