"""Qt worker that runs a scan on a background thread.

All heavy work happens here so the UI event loop never blocks. Progress updates
arrive as Qt signals, and the user can pause, resume or cancel the run at any
time through the controller slots.
"""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import QThread, Signal, Slot

from ..core.config import AppConfig
from ..core.logger import get_logger
from ..database.database import Database
from ..models.scan_session import ScanSession
from ..services.progress import ProgressUpdate
from ..services.scan_service import ScanController, ScanResult, ScanService

_log = get_logger("workers.scan")


class ScanWorker(QThread):
    """Background scan executed via :class:`ScanService`."""

    progress = Signal(ProgressUpdate)
    finished_scan = Signal(ScanResult)
    failed = Signal(str)
    stage_changed = Signal(str)

    def __init__(
        self,
        database: Database,
        config: AppConfig,
        folders: Optional[Sequence[str]] = None,
        scan_drives: bool = False,
        include_removable: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.config = config
        self.folders = list(folders) if folders else []
        self.scan_drives = scan_drives
        self.include_removable = include_removable
        self.controller = ScanController()
        self._service = ScanService(database, config)
        self._last_stage = None

    # ------------------------------------------------------------------
    # Thread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            if self.scan_drives:
                result = self._service.scan_drives(
                    include_removable=self.include_removable,
                    progress=self._on_progress,
                    controller=self.controller,
                )
            else:
                result = self._service.scan_folders(
                    self.folders, progress=self._on_progress, controller=self.controller
                )
            self.finished_scan.emit(result)
        except Exception as exc:
            _log.exception("Scan worker failed")
            self.failed.emit(str(exc))

    def _on_progress(self, update: ProgressUpdate) -> None:
        if update.stage is not self._last_stage:
            self._last_stage = update.stage
            self.stage_changed.emit(update.stage.value)
        self.progress.emit(update)

    # ------------------------------------------------------------------
    # Control slots (safe to call from the UI thread)
    # ------------------------------------------------------------------

    @Slot()
    def pause(self) -> None:
        self.controller.pause()

    @Slot()
    def resume(self) -> None:
        self.controller.resume()

    @Slot()
    def cancel(self) -> None:
        self.controller.cancel()

    @property
    def is_paused(self) -> bool:
        return self.controller.is_paused

    @property
    def is_cancelled(self) -> bool:
        return self.controller.is_cancelled
