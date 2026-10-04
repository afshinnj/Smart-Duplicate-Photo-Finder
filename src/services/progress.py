"""Progress reporting shared between the scan pipeline and the UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class ScanStage(Enum):
    """Ordered stages of the duplicate detection pipeline."""

    IDLE = "idle"
    PREPARING = "preparing"
    SCANNING = "scanning"
    METADATA = "metadata"
    EXACT_DUPLICATES = "exact_duplicates"
    PERCEPTUAL = "perceptual"
    SIMILARITY = "similarity"
    GROUPING = "grouping"
    FINALIZING = "finalizing"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"

    @property
    def label_key(self) -> str:
        return f"stage_{self.value}"


@dataclass
class ProgressUpdate:
    """One progress tick emitted by :class:`~services.scan_service.ScanService`."""

    stage: ScanStage
    files_scanned: int = 0
    images_found: int = 0
    total_files: int = 0
    total_images: int = 0
    current_path: str = ""
    stage_progress: float = 0.0  # 0-100 inside the current stage
    overall_progress: float = 0.0  # 0-100 across the whole pipeline
    elapsed_seconds: float = 0.0
    eta_seconds: float = 0.0
    rate: float = 0.0  # files per second
    message: str = ""
    error: Optional[str] = None
    groups_found: int = 0
    duplicates_found: int = 0
    space_recoverable: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def eta_label(self) -> str:
        return format_duration(self.eta_seconds)


def format_duration(seconds: float) -> str:
    """Human readable duration, e.g. ``1h 05m``, ``42s``, ``--``."""
    if seconds <= 0:
        return "--"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes:02d}m"
    if minutes > 0:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def format_size(size_bytes: float) -> str:
    """Convert a byte count into a compact human readable string."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024.0:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


ProgressCallback = Callable[[ProgressUpdate], None]
