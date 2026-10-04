"""Domain model for a scan session."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from ..core.constants import ScanStatus


@dataclass
class ScanSession:
    """A single execution of the duplicate detection pipeline."""

    id: Optional[int] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    folders: List[str] = field(default_factory=list)
    files_scanned: int = 0
    images_found: int = 0
    duplicates_found: int = 0
    space_recoverable: int = 0
    status: ScanStatus = ScanStatus.PENDING
    error: Optional[str] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

    @property
    def is_finished(self) -> bool:
        return self.status in {ScanStatus.COMPLETED, ScanStatus.CANCELLED, ScanStatus.FAILED}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "folders": self.folders,
            "files_scanned": self.files_scanned,
            "images_found": self.images_found,
            "duplicates_found": self.duplicates_found,
            "space_recoverable": self.space_recoverable,
            "status": self.status.value,
            "error": self.error,
        }
