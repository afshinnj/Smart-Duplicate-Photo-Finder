"""Core constants and branding for the application.

All user-visible product names live here so the application can be re-branded
by editing a single module.
"""

from __future__ import annotations

import os
from enum import Enum, auto

# ---------------------------------------------------------------------------
# Branding (change here to re-brand the whole application)
# ---------------------------------------------------------------------------

APP_NAME: str = "Smart Duplicate Photo Finder"
APP_SHORT_NAME: str = "Photo Finder"
APP_VERSION: str = "1.0.0"
APP_AUTHOR: str = "Afshin"
ORG_NAME: str = "Afshin Software"
ORG_DOMAIN: str = "afshin.software"

# ---------------------------------------------------------------------------
# File system locations
# ---------------------------------------------------------------------------

APP_DIR_NAME: str = "SmartDuplicatePhotoFinder"


def app_data_dir() -> str:
    """Return the per-user application data directory (created lazily)."""
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~")
    path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def logs_dir() -> str:
    path = os.path.join(app_data_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def cache_dir() -> str:
    path = os.path.join(app_data_dir(), "cache")
    os.makedirs(path, exist_ok=True)
    return path


def thumbnails_dir() -> str:
    path = os.path.join(cache_dir(), "thumbnails")
    os.makedirs(path, exist_ok=True)
    return path


def quarantine_dir() -> str:
    """Folder used to safely stage removed files so they can be undone."""
    path = os.path.join(app_data_dir(), "quarantine")
    os.makedirs(path, exist_ok=True)
    return path


def database_path() -> str:
    return os.path.join(app_data_dir(), "database.sqlite")


def config_path() -> str:
    return os.path.join(app_data_dir(), "config.json")


# ---------------------------------------------------------------------------
# Supported image formats
# ---------------------------------------------------------------------------

DEFAULT_IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".bmp",
        ".gif",
        ".tif",
        ".tiff",
        ".heic",
        ".heif",
    }
)

# Folders that are excluded from full-disk scans by default.
DEFAULT_EXCLUDED_FOLDERS: frozenset[str] = frozenset(
    {
        "$Recycle.Bin",
        "$WinREAgent",
        "System Volume Information",
        "Windows",
        "Program Files",
        "Program Files (x86)",
        "ProgramData",
        "AppData",
        "node_modules",
        ".git",
    }
)

# ---------------------------------------------------------------------------
# Hashing / similarity defaults
# ---------------------------------------------------------------------------

HASH_SIZE: int = 8  # 8x8 -> 64 bit perceptual hashes
PHASH_BITS: int = HASH_SIZE * HASH_SIZE
THUMBNAIL_SIZE: int = 256
SHA256_CHUNK_SIZE: int = 8 * 1024 * 1024  # 8 MiB

# Default similarity bands (percentages)
DEFAULT_DUPLICATE_THRESHOLD: float = 98.0
DEFAULT_SIMILAR_THRESHOLD: float = 85.0
DEFAULT_AI_THRESHOLD: float = 75.0

# Similarity rating bands used by the UI labels.
RATING_EXACT: float = 100.0
RATING_ALMOST_SAME: float = 95.0
RATING_VERY_SIMILAR: float = 85.0
RATING_SIMILAR: float = 70.0
RATING_POSSIBLY_RELATED: float = 50.0


class SimilarityRating(Enum):
    """Human-readable classification of a similarity score."""

    EXACT = auto()
    ALMOST_SAME = auto()
    VERY_SIMILAR = auto()
    SIMILAR = auto()
    POSSIBLY_RELATED = auto()
    DIFFERENT = auto()


def rate_similarity(score: float) -> SimilarityRating:
    """Classify a 0-100 similarity score into a rating band."""
    if score >= RATING_EXACT:
        return SimilarityRating.EXACT
    if score >= RATING_ALMOST_SAME:
        return SimilarityRating.ALMOST_SAME
    if score >= RATING_VERY_SIMILAR:
        return SimilarityRating.VERY_SIMILAR
    if score >= RATING_SIMILAR:
        return SimilarityRating.SIMILAR
    if score >= RATING_POSSIBLY_RELATED:
        return SimilarityRating.POSSIBLY_RELATED
    return SimilarityRating.DIFFERENT


# ---------------------------------------------------------------------------
# Scan session status
# ---------------------------------------------------------------------------


class ScanStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CleanupMethod(Enum):
    """How a file should be removed from disk."""

    QUARANTINE = "quarantine"  # move to app-managed recovery folder (undoable)
    RECYCLE_BIN = "recycle_bin"  # send to the Windows Recycle Bin
    PERMANENT = "permanent"  # delete immediately (dangerous)


class DuplicateType(Enum):
    EXACT = "exact"
    SIMILAR = "similar"
