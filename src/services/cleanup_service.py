"""Safe cleanup with undo support.

Nothing is ever deleted without the caller asking for it, and the default
removal method (:attr:`CleanupMethod.QUARANTINE`) does not delete at all: the
file is moved into a recovery folder inside the application data directory so
the operation can be undone. Sending files to the Windows Recycle Bin and
permanent deletion are explicit opt-ins.

System files and protected locations are refused outright.
"""

from __future__ import annotations

import ctypes
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Sequence

from ..core import constants
from ..core.config import CleanupSettings
from ..core.exceptions import CleanupError
from ..core.logger import get_logger
from ..database.database import Database
from ..database.repositories.scan_repository import DeletedFileRepository
from ..models.image_model import ImageRecord

_log = get_logger("services.cleanup")

# Locations that must never be touched by the cleanup service.
_PROTECTED_PATTERNS = (
    "\\windows\\",
    "\\program files\\",
    "\\program files (x86)\\",
    "\\programdata\\",
    "\\$recycle.bin\\",
    "\\system volume information\\",
    "\\windowsapps\\",
    "\\appdata\\local\\",
)


@dataclass
class CleanupResult:
    """Outcome of a single cleanup operation."""

    method: constants.CleanupMethod
    removed: List[ImageRecord] = field(default_factory=list)
    failed: List[tuple[ImageRecord, str]] = field(default_factory=list)
    total_size: int = 0
    operation_ids: List[int] = field(default_factory=list)

    @property
    def removed_count(self) -> int:
        return len(self.removed)

    @property
    def failed_count(self) -> int:
        return len(self.failed)


def is_protected_path(path: str) -> bool:
    """Refuse to touch system folders and protected application locations."""
    normalized = os.path.normcase(os.path.abspath(path))
    lower = normalized.replace("/", "\\")
    if lower.endswith(".exe") or lower.endswith(".dll") or lower.endswith(".sys"):
        return True
    return any(pattern in lower for pattern in _PROTECTED_PATTERNS)


class CleanupService:
    """Removes or quarantines duplicate files."""

    def __init__(self, database: Database, settings: Optional[CleanupSettings] = None) -> None:
        self.database = database
        self.settings = settings or CleanupSettings()
        self._repository = DeletedFileRepository(database)

    # ------------------------------------------------------------------
    # Safety checks
    # ------------------------------------------------------------------

    def assert_safe(self, record: ImageRecord) -> None:
        if not record.path:
            raise CleanupError("Empty file path")
        if is_protected_path(record.path):
            raise CleanupError(f"Refusing to touch a protected system location: {record.path}")
        if not os.path.exists(record.path):
            raise CleanupError(f"File no longer exists: {record.path}")

    # ------------------------------------------------------------------
    # Removal
    # ------------------------------------------------------------------

    def remove(
        self,
        records: Sequence[ImageRecord],
        method: Optional[constants.CleanupMethod] = None,
        confirm: Optional[callable] = None,
    ) -> CleanupResult:
        """Remove ``records`` using ``method`` (defaults to the configured one).

        ``confirm`` is an optional callable that receives the planned operation
        summary (count + size + method) and returns ``True`` to proceed. It is
        the last safety net before any file is touched.
        """
        method = method or self.settings.method
        records = [record for record in records if record is not None]
        if not records:
            return CleanupResult(method=method)

        total_size = sum(record.size for record in records)
        if confirm is not None and not confirm(records, total_size, method):
            raise CleanupError("User did not confirm the cleanup operation")

        result = CleanupResult(method=method, total_size=total_size)
        for record in records:
            try:
                self.assert_safe(record)
                operation_id = self._remove_one(record, method)
                result.removed.append(record)
                result.operation_ids.append(operation_id)
            except CleanupError as exc:
                result.failed.append((record, str(exc)))
                _log.warning("Cleanup skipped %s: %s", record.path, exc)
            except Exception as exc:
                result.failed.append((record, f"{type(exc).__name__}: {exc}"))
                _log.exception("Unexpected cleanup failure for %s", record.path)

        _log.info(
            "Cleanup (%s): %d files removed, %d failed, %s recovered",
            method.value,
            result.removed_count,
            result.failed_count,
            _format_size(result.total_size),
        )
        return result

    def _remove_one(self, record: ImageRecord, method: constants.CleanupMethod) -> int:
        if method == constants.CleanupMethod.QUARANTINE:
            backup_path = self._quarantine(record)
            return self._repository.add(
                image_id=record.id,
                original_path=record.path,
                backup_path=backup_path,
                method=method,
                size=record.size,
            )
        if method == constants.CleanupMethod.RECYCLE_BIN:
            self._send_to_recycle_bin(record.path)
            return self._repository.add(
                image_id=record.id,
                original_path=record.path,
                backup_path=None,
                method=method,
                size=record.size,
            )
        # Permanent deletion is destructive: keep the record so the user can
        # at least see what was removed.
        os.remove(record.path)
        return self._repository.add(
            image_id=record.id,
            original_path=record.path,
            backup_path=None,
            method=method,
            size=record.size,
        )

    # ------------------------------------------------------------------
    # Quarantine
    # ------------------------------------------------------------------

    @staticmethod
    def _quarantine_name(record: ImageRecord) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe_name = os.path.basename(record.path).replace(":", "_")
        return f"{timestamp}_{safe_name}"

    def _quarantine(self, record: ImageRecord) -> str:
        quarantine = constants.quarantine_dir()
        destination = os.path.join(quarantine, self._quarantine_name(record))
        counter = 1
        while os.path.exists(destination):
            base, extension = os.path.splitext(destination)
            destination = f"{base}_{counter}{extension}"
            counter += 1
        try:
            shutil.move(record.path, destination)
        except OSError as exc:
            raise CleanupError(f"Cannot quarantine {record.path}: {exc}") from exc
        return destination

    # ------------------------------------------------------------------
    # Windows Recycle Bin
    # ------------------------------------------------------------------

    @staticmethod
    def _send_to_recycle_bin(path: str) -> None:
        """Move a file to the Recycle Bin via the Win32 shell (undoable there)."""
        if os.name != "nt":  # pragma: no cover - Windows only feature
            raise CleanupError("Recycle Bin is only available on Windows")

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.c_void_p),
                ("wFunc", ctypes.c_uint),
                ("pFrom", ctypes.c_wchar_p),
                ("pTo", ctypes.c_wchar_p),
                ("fFlags", ctypes.c_uint16),
                ("fAnyOperationsAborted", ctypes.c_int),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", ctypes.c_wchar_p),
            ]

        FO_DELETE = 0x0003
        FOF_ALLOWUNDO = 0x0040
        FOF_NOCONFIRMATION = 0x0010
        FOF_SILENT = 0x0004

        operation = SHFILEOPSTRUCTW()
        operation.hwnd = None
        operation.wFunc = FO_DELETE
        operation.pFrom = path + "\0"  # SHFileOperation requires a double-null-terminated string
        operation.pTo = None
        operation.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
        operation.fAnyOperationsAborted = 0
        operation.hNameMappings = None
        operation.lpszProgressTitle = None

        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))  # type: ignore[attr-defined]
        if result != 0:
            raise CleanupError(f"Recycle Bin operation failed (error {result}) for {path}")

    # ------------------------------------------------------------------
    # Undo
    # ------------------------------------------------------------------

    def undo(self, operation_ids: Optional[Sequence[int]] = None, limit: int = 100) -> int:
        """Restore quarantined files. Returns the number of files restored."""
        if operation_ids:
            rows = self.database.query(
                "SELECT * FROM deleted_files WHERE id IN (%s) AND restored = 0"
                % ",".join("?" for _ in operation_ids),
                tuple(operation_ids),
            )
        else:
            rows = self.database.query(
                "SELECT * FROM deleted_files WHERE restored = 0 ORDER BY id DESC LIMIT ?", (limit,)
            )

        restored = 0
        for row in rows:
            record = dict(row)
            if record["method"] == constants.CleanupMethod.QUARANTINE.value and record["backup_path"]:
                if self._restore_from_quarantine(record):
                    self._repository.mark_restored(record["id"])
                    restored += 1
        return restored

    def _restore_from_quarantine(self, record: dict) -> bool:
        original_path = record["original_path"]
        backup_path = record["backup_path"]
        if not backup_path or not os.path.exists(backup_path):
            _log.warning("Quarantine backup missing for %s", original_path)
            return False

        destination = original_path
        counter = 1
        while os.path.exists(destination):
            base, extension = os.path.splitext(original_path)
            destination = f"{base}_restored_{counter}{extension}"
            counter += 1

        try:
            shutil.move(backup_path, destination)
            return True
        except OSError as exc:
            _log.error("Cannot restore %s: %s", original_path, exc)
            return False

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def purge_expired_quarantine(self) -> int:
        """Permanently delete quarantine entries older than the retention window."""
        days = self.settings.quarantine_auto_purge_days
        if days <= 0:
            return 0
        rows = self.database.query(
            "SELECT id, backup_path FROM deleted_files "
            "WHERE method = ? AND restored = 0 AND backup_path IS NOT NULL "
            "AND deleted_at < datetime('now', ?)",
            (constants.CleanupMethod.QUARANTINE.value, f"-{days} days"),
        )
        purged = 0
        for row in rows:
            backup_path = row["backup_path"]
            if backup_path and os.path.exists(backup_path):
                try:
                    os.remove(backup_path)
                    self._repository.mark_restored(row["id"])
                    purged += 1
                except OSError as exc:
                    _log.warning("Cannot purge %s: %s", backup_path, exc)
        return purged

    def pending_undo_count(self) -> int:
        return self._repository.pending_count()

    def pending_undo_size(self) -> int:
        return self._repository.pending_size()


def _format_size(size_bytes: int) -> str:
    from .progress import format_size

    return format_size(size_bytes)
