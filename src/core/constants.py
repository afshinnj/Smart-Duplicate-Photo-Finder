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

APP_NAME: str = "DupliPix"
APP_SHORT_NAME: str = "DupliPix"
APP_VERSION: str = "1.0.0"
APP_AUTHOR: str = "Afshin"
ORG_NAME: str = "Afshin Software"
ORG_DOMAIN: str = "afshin.software"

# ---------------------------------------------------------------------------
# File system locations
# ---------------------------------------------------------------------------

APP_DIR_NAME: str = "DupliPix"

# Folder used before the rename to DupliPix. Kept only so an upgrade can adopt
# the user's existing data (see ``_adopt_legacy_data_dir``).
_LEGACY_DIR_NAME: str = "SmartDuplicatePhotoFinder"


# When set, every user-data path (config, database, quarantine, thumbnails,
# logs) is resolved underneath this directory instead of the real per-user
# location. Tests use it to stay isolated from the user's actual data; the
# shipped application never sets it.
DATA_DIR_ENV: str = "SDPF_DATA_DIR"


def app_data_dir() -> str:
    """Return the per-user application data directory (created lazily)."""
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        path = os.path.abspath(override)
    else:
        base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~")
        path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def migrate_legacy_data_dir() -> None:
    """Adopt the data directory of the previous product name, exactly once.

    The application used to live in ``%APPDATA%\\SmartDuplicatePhotoFinder``.
    After the rename to DupliPix this moves the user's settings, scan history,
    cached thumbnails and quarantined files into the new folder so nothing is
    orphaned. It must run once at startup, *before* the database is opened, so
    no lock can interfere with the move.
    """
    if os.environ.get(DATA_DIR_ENV):  # test/offscreen runs stay isolated
        return
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~")
    target = os.path.join(base, APP_DIR_NAME)
    _adopt_legacy_data_dir(base, target)


def _adopt_legacy_data_dir(base: str, target: str) -> None:
    """Move the contents of the renamed ``SmartDuplicatePhotoFinder`` folder.

    Runs only when the target folder is still fresh (no config or database) and
    the legacy folder holds real data. Everything is moved, so the quarantine
    entries stay restorable and the scan history survives the rename.
    """
    legacy = os.path.join(base, _LEGACY_DIR_NAME)
    if not os.path.isdir(legacy):
        return
    legacy_config = os.path.join(legacy, "config.json")
    legacy_database = os.path.join(legacy, "database.sqlite")
    if not os.path.exists(legacy_config) and not os.path.exists(legacy_database):
        return
    # Already migrated (or in use) - never overwrite existing user data.
    if os.path.exists(os.path.join(target, "config.json")) or os.path.exists(
        os.path.join(target, "database.sqlite")
    ):
        return

    import logging
    import shutil

    log = logging.getLogger("core.constants")
    log.info("Migrating user data from %s to %s", legacy, target)
    try:
        os.makedirs(target, exist_ok=True)
        for entry in os.listdir(legacy):
            source = os.path.join(legacy, entry)
            destination = os.path.join(target, entry)
            if os.path.exists(destination):
                continue
            shutil.move(source, destination)
        # Remove the old folder only when nothing was left behind.
        if not os.listdir(legacy):
            shutil.rmtree(legacy, ignore_errors=True)
    except OSError as exc:
        log.warning("User-data migration incomplete: %s", exc)


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
