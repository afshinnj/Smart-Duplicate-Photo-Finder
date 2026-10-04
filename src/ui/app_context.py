"""Shared application state passed to every page.

Grouping the database, configuration and services in one object keeps page
constructors small and guarantees that all widgets talk to the same backend.
"""

from __future__ import annotations

from typing import Optional

from ..core.config import AppConfig
from ..core.logger import get_logger, setup_logging
from ..database.database import Database
from ..services.cleanup_service import CleanupService
from ..services.history_service import HistoryService
from ..services.scan_service import ScanService
from .thumbnail_cache import ThumbnailCache, ThumbnailLoader

_log = get_logger("ui.context")


class AppContext:
    """The backend objects the UI layers share."""

    def __init__(self, database: Optional[Database] = None, config: Optional[AppConfig] = None) -> None:
        setup_logging()
        self.database = database or Database()
        self.config = config or AppConfig.load()
        self.thumbnail_cache = ThumbnailCache()
        self.thumbnail_loader = ThumbnailLoader(self.thumbnail_cache)
        self.history_service = HistoryService(self.database)
        self.cleanup_service = CleanupService(self.database, self.config.cleanup)
        self.scan_service = ScanService(self.database, self.config)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def save_config(self) -> None:
        try:
            self.config.save()
        except Exception as exc:  # a settings write must never crash the app
            _log.error("Cannot save configuration: %s", exc)

    def make_scan_service(self) -> ScanService:
        """Fresh pipeline instance for a new run (picks up edited settings)."""
        self.scan_service = ScanService(self.database, self.config)
        return self.scan_service

    def make_cleanup_service(self) -> CleanupService:
        self.cleanup_service = CleanupService(self.database, self.config.cleanup)
        return self.cleanup_service

    def close(self) -> None:
        try:
            self.database.close()
        except Exception:
            pass
