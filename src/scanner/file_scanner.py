"""Recursive file system scanner.

The scanner walks one or more roots and yields :class:`ScannedFile` instances
while honouring the user's filters. Long scans stay responsive because the walk
is a generator: callers receive files as they are discovered and can pause or
cancel between directory visits.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Iterator, List, Optional, Sequence

from ..core.config import ScanSettings
from ..core.exceptions import ScanCancelled
from ..core.logger import get_logger
from ..models.image_model import ScannedFile

_log = get_logger("scanner.file_scanner")


class ScanEvent(Enum):
    FILE_FOUND = auto()
    DIRECTORY_VISITED = auto()
    ACCESS_DENIED = auto()


@dataclass
class ScanContext:
    """Mutable state shared between the scanner and its caller."""

    cancel_requested: bool = False
    pause_requested: bool = False
    files_scanned: int = 0
    images_found: int = 0
    current_path: str = ""
    start_time: float = field(default_factory=time.time)
    errors: List[str] = field(default_factory=list)

    def request_cancel(self) -> None:
        self.cancel_requested = True

    def request_pause(self) -> None:
        self.pause_requested = True

    def request_resume(self) -> None:
        self.pause_requested = False

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    @property
    def files_per_second(self) -> float:
        elapsed = self.elapsed_seconds
        if elapsed <= 0:
            return 0.0
        return self.files_scanned / elapsed

    def eta_seconds(self, remaining: int) -> float:
        rate = self.files_per_second
        if rate <= 0:
            return 0.0
        return remaining / rate


class FileScanner:
    """Applies user filters while walking the file system."""

    def __init__(self, settings: Optional[ScanSettings] = None) -> None:
        self.settings = settings or ScanSettings()
        self._excluded_lower = {name.lower() for name in self.settings.excluded_folders}
        self._extensions = {
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in self.settings.image_extensions
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(
        self,
        roots: Sequence[str],
        context: Optional[ScanContext] = None,
        wanted_extensions: Optional[set[str]] = None,
    ) -> Iterator[ScannedFile]:
        """Yield every file under ``roots`` that passes the filters.

        ``wanted_extensions`` lets the caller restrict results to image formats
        without touching the general settings.
        """
        context = context or ScanContext()
        extensions = wanted_extensions if wanted_extensions is not None else self._extensions

        for root in roots:
            normalized = os.path.normpath(root)
            if not self._is_scannable(normalized):
                continue
            yield from self._walk(normalized, context, extensions)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _walk(
        self, root: str, context: ScanContext, extensions: set[str]
    ) -> Iterator[ScannedFile]:
        try:
            entries = list(os.scandir(root))
        except (PermissionError, OSError) as exc:
            context.errors.append(root)
            _log.debug("Access denied: %s (%s)", root, exc)
            return

        directories = []
        for entry in entries:
            if context.cancel_requested:
                raise ScanCancelled()
            if context.pause_requested:
                self._wait_for_resume(context)

            try:
                is_dir = entry.is_dir()
            except OSError:
                continue

            if is_dir:
                if self._is_scannable(entry.path):
                    directories.append(entry.path)
                continue

            try:
                if not entry.is_file():
                    continue
                info = entry.stat()
            except (PermissionError, OSError):
                context.errors.append(entry.path)
                continue

            if not self._pass_filters(entry.name, info.st_size, info):
                continue

            context.files_scanned += 1
            context.current_path = entry.path

            extension = os.path.splitext(entry.name)[1].lower()
            if extension not in extensions:
                continue

            context.images_found += 1
            yield ScannedFile(
                path=entry.path,
                size=info.st_size,
                modified_at=info.st_mtime,
                created_at=getattr(info, "st_ctime", info.st_mtime),
                is_hidden=self._is_hidden(entry.name),
            )

        for directory in directories:
            yield from self._walk(directory, context, extensions)

    def _wait_for_resume(self, context: ScanContext) -> None:
        """Block while the scan is paused, aborting if cancelled."""
        while context.pause_requested and not context.cancel_requested:
            time.sleep(0.05)
        if context.cancel_requested:
            raise ScanCancelled()

    def _is_scannable(self, path: str) -> bool:
        name = os.path.basename(os.path.normpath(path)).lower()
        if name in self._excluded_lower:
            return False
        if not self.settings.include_hidden_files and self._is_hidden(name):
            return False
        return True

    @staticmethod
    def _is_hidden(name: str) -> bool:
        if not name:
            return False
        if name.startswith("."):
            return True
        return os.name == "nt" and name.lower() in {"$recycle.bin", "system volume information"}

    def _pass_filters(self, name: str, size: int, stat) -> bool:
        if not self.settings.include_hidden_files and self._is_hidden(name):
            return False
        min_bytes = int(self.settings.min_file_size_mb * 1024 * 1024)
        if min_bytes and size < min_bytes:
            return False
        max_bytes = int(self.settings.max_file_size_mb * 1024 * 1024)
        if max_bytes and size > max_bytes:
            return False
        return True
