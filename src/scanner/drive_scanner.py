"""Discovery of drives and removable media (USB, memory cards)."""

from __future__ import annotations

from typing import List, Optional

from ..core import system_info
from ..core.config import ScanSettings
from ..core.logger import get_logger
from .file_scanner import FileScanner, ScanContext
from ..models.image_model import ScannedFile

_log = get_logger("scanner.drive_scanner")


class DriveScanner:
    """Extends :class:`FileScanner` with whole-drive scanning support."""

    def __init__(self, settings: Optional[ScanSettings] = None) -> None:
        self.settings = settings or ScanSettings()
        self.scanner = FileScanner(self.settings)

    # ------------------------------------------------------------------
    # Drive discovery
    # ------------------------------------------------------------------

    def list_drives(self) -> List[system_info.DriveInfo]:
        """All fixed + removable volumes currently mounted."""
        return system_info.list_drives()

    def list_removable_drives(self) -> List[system_info.DriveInfo]:
        """USB sticks and memory cards that are safe to unplug."""
        return system_info.removable_drives()

    def drive_roots(self, include_removable: bool = True) -> List[str]:
        roots = []
        for drive in self.list_drives():
            if drive.is_removable and not include_removable:
                continue
            roots.append(drive.letter)
        return roots

    # ------------------------------------------------------------------
    # Whole-drive scans
    # ------------------------------------------------------------------

    def scan_drive(
        self,
        letter: str,
        context: Optional[ScanContext] = None,
    ) -> list[ScannedFile]:
        """Scan an entire drive and return the image files it contains."""
        root = letter if letter.endswith("\\") else letter + "\\"
        _log.info("Starting full-drive scan of %s", root)
        return list(self.scanner.scan([root], context))

    def scan_all_drives(
        self,
        include_removable: bool = True,
        context: Optional[ScanContext] = None,
    ) -> list[ScannedFile]:
        """Scan every mounted volume in a single pass."""
        return list(
            self.scanner.scan(self.drive_roots(include_removable=include_removable), context)
        )
