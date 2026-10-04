"""Domain model for a single discovered image file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from ..core.constants import HASH_SIZE


@dataclass
class ImageRecord:
    """Metadata + hashes for one image file.

    Hash fields store perceptual hashes as hexadecimal strings so they can be
    persisted directly into SQLite.
    """

    id: Optional[int] = None
    path: str = ""
    filename: str = ""
    extension: str = ""
    size: int = 0
    width: int = 0
    height: int = 0
    created_at: float = 0.0
    modified_at: float = 0.0
    sha256: Optional[str] = None
    ahash: Optional[str] = None
    dhash: Optional[str] = None
    phash: Optional[str] = None
    whash: Optional[str] = None
    scan_id: Optional[int] = None
    # Optional pre-computed embeddings from the (optional) AI engine.
    embedding: Optional[bytes] = None
    error: Optional[str] = None

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    @property
    def hash_bits(self) -> int:
        return HASH_SIZE * HASH_SIZE

    @property
    def resolution(self) -> str:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return "unknown"

    @property
    def megapixels(self) -> float:
        return (self.width * self.height) / 1_000_000.0

    @property
    def size_mb(self) -> float:
        return self.size / (1024.0 * 1024.0)

    @property
    def is_readable(self) -> bool:
        return self.error is None

    def phash_int(self) -> Optional[int]:
        return _hex_to_int(self.phash)

    def dhash_int(self) -> Optional[int]:
        return _hex_to_int(self.dhash)

    def ahash_int(self) -> Optional[int]:
        return _hex_to_int(self.ahash)

    def whash_int(self) -> Optional[int]:
        return _hex_to_int(self.whash)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "path": self.path,
            "filename": self.filename,
            "extension": self.extension,
            "size": self.size,
            "width": self.width,
            "height": self.height,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "sha256": self.sha256,
            "ahash": self.ahash,
            "dhash": self.dhash,
            "phash": self.phash,
            "whash": self.whash,
            "scan_id": self.scan_id,
            "error": self.error,
        }


def _hex_to_int(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        return int(value, 16)
    except ValueError:
        return None


@dataclass
class ScannedFile:
    """A raw filesystem entry produced by the file scanner."""

    path: str
    size: int
    modified_at: float
    created_at: float
    is_hidden: bool = False

    @staticmethod
    def from_path(path: str) -> "ScannedFile":
        stat = os.stat(path)
        return ScannedFile(
            path=path,
            size=stat.st_size,
            modified_at=stat.st_mtime,
            created_at=getattr(stat, "st_ctime", stat.st_mtime),
            is_hidden=os.path.basename(path).startswith("."),
        )


@dataclass
class ImageMetadata:
    """Dimensions decoded from an image file."""

    width: int
    height: int


@dataclass
class ImageBatch:
    """A chunk of image records used for batch processing."""

    records: list[ImageRecord] = field(default_factory=list)
    scan_id: Optional[int] = None
