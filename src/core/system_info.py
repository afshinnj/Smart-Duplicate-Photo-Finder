"""Read-only access to system resources.

``psutil`` is used when it is available so that memory and disk statistics are
accurate. When it is not installed the module falls back to the standard
library so the application keeps working fully offline.
"""

from __future__ import annotations

import ctypes
import os
import shutil
from dataclasses import dataclass
from typing import List, Optional

from .logger import get_logger

_log = get_logger("core.system_info")

try:  # pragma: no cover - depends on the environment
    import psutil  # type: ignore

    _HAS_PSUTIL = True
except Exception:  # pragma: no cover
    psutil = None  # type: ignore
    _HAS_PSUTIL = False


@dataclass(frozen=True)
class DriveInfo:
    """A physical or logical drive discovered on the system."""

    letter: str  # e.g. "C:\\"
    label: str
    is_removable: bool
    total_bytes: int
    free_bytes: int


def has_psutil() -> bool:
    return _HAS_PSUTIL


def cpu_count() -> int:
    """Number of logical CPUs usable for worker pools."""
    if _HAS_PSUTIL:
        try:
            count = psutil.cpu_count(logical=True)  # type: ignore[union-attr]
            if count:
                return max(1, count)
        except Exception:
            pass
    return max(1, os.cpu_count() or 1)


def available_memory_mb() -> Optional[int]:
    """Free system memory in megabytes, or ``None`` when unknown."""
    if _HAS_PSUTIL:
        try:
            return int(psutil.virtual_memory().available / (1024 * 1024))  # type: ignore[union-attr]
        except Exception:
            return None
    if os.name == "nt":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))  # type: ignore[attr-defined]
            return int(stat.ullAvailPhys / (1024 * 1024))
        except Exception:
            return None
    return None


def disk_usage(path: str) -> shutil._ntuple_diskusage:
    return shutil.disk_usage(path)


def _query_dos_devices() -> List[str]:
    buffer = ctypes.create_unicode_buffer(1024)
    length = ctypes.windll.kernel32.GetLogicalDriveStringsW(  # type: ignore[attr-defined]
        ctypes.sizeof(buffer) // 2, buffer
    )
    if not length:
        return []
    # Slicing a c_wchar array already yields the decoded text, so this avoids
    # the ``raw`` attribute that was removed from unicode buffers in newer
    # CPython releases.
    return [part for part in buffer[:length].split("\0") if part]


def _drive_label(root: str) -> str:
    volume_name = ctypes.create_unicode_buffer(1024)
    file_system = ctypes.create_unicode_buffer(1024)
    ok = ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
        ctypes.c_wchar_p(root),
        volume_name,
        ctypes.sizeof(volume_name) // 2,
        None,
        None,
        None,
        file_system,
        ctypes.sizeof(file_system) // 2,
    )
    if ok and volume_name.value:
        return volume_name.value
    return "Local Disk"


def list_drives() -> List[DriveInfo]:
    """Enumerate fixed and removable volumes (Windows)."""
    if os.name != "nt":
        return []
    drives: List[DriveInfo] = []
    for letter in _query_dos_devices():
        try:
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(letter))  # type: ignore[attr-defined]
            removable = drive_type == 2  # DRIVE_REMOVABLE
            fixed = drive_type == 3  # DRIVE_FIXED
            if not (removable or fixed):
                continue
            usage = shutil.disk_usage(letter)
            drives.append(
                DriveInfo(
                    letter=letter,
                    label=_drive_label(letter),
                    is_removable=removable,
                    total_bytes=usage.total,
                    free_bytes=usage.free,
                )
            )
        except Exception as exc:  # a drive that cannot be queried is skipped
            _log.debug("Cannot query drive %s: %s", letter, exc)
    return drives


def removable_drives() -> List[DriveInfo]:
    """USB sticks, memory cards and other removable media."""
    return [drive for drive in list_drives() if drive.is_removable]
