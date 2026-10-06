"""Image detection and metadata extraction."""

from __future__ import annotations

import os
from typing import Iterable, List, Optional, Sequence

from ..core.constants import DEFAULT_IMAGE_EXTENSIONS
from ..core.exceptions import ImageProcessingError
from ..core.image_formats import decodable_extensions
from ..core.logger import get_logger
from ..models.image_model import ImageMetadata, ScannedFile

_log = get_logger("scanner.image_detector")


class ImageDetector:
    """Decides which scanned files are images and reads their dimensions."""

    def __init__(self, extensions: Optional[Iterable[str]] = None) -> None:
        requested = {ext.lower().lstrip(".") for ext in (extensions or DEFAULT_IMAGE_EXTENSIONS)}
        # Drop formats Pillow cannot open (e.g. HEIC without pillow-heif).
        # They would be counted as images here and then fail silently during
        # hashing and similarity, so report them once up front instead.
        decodable = decodable_extensions({f".{ext}" for ext in requested})
        unsupported = {f".{ext}" for ext in requested} - decodable
        if unsupported:
            _log.warning(
                "Ignoring %d image format(s) with no decoder available: %s",
                len(unsupported),
                ", ".join(sorted(unsupported)),
            )
        self.extensions = decodable

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def is_image(self, path: str) -> bool:
        return os.path.splitext(path)[1].lower() in self.extensions

    def filter_images(self, files: Iterable[ScannedFile]) -> List[ScannedFile]:
        return [file for file in files if self.is_image(file.path)]

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def read_metadata(self, path: str) -> Optional[ImageMetadata]:
        """Return the pixel dimensions of an image.

        Uses Pillow's lazy ``verify``-free path so huge files are not fully
        loaded into memory. Returns ``None`` for files that cannot be decoded.
        """
        try:
            from PIL import Image, UnidentifiedImageError
        except ImportError as exc:  # pragma: no cover
            raise ImageProcessingError("Pillow is required to read image metadata") from exc

        try:
            with Image.open(path) as image:
                return ImageMetadata(width=int(image.width), height=int(image.height))
        except UnidentifiedImageError:
            _log.debug("Unidentified image format: %s", path)
            return None
        except (OSError, ValueError, Image.UnidentifiedImageError) as exc:
            _log.debug("Cannot read metadata for %s: %s", path, exc)
            return None
        except Exception as exc:  # corrupted/locked file - never crash the scan
            _log.debug("Unexpected error reading %s: %s", path, exc)
            return None

    def detect_error(self, path: str) -> Optional[str]:
        """Classify why an image could not be processed, if at all."""
        if not os.path.exists(path):
            return "missing"
        try:
            from PIL import Image

            with Image.open(path) as image:
                image.verify()
        except Exception as exc:
            return type(exc).__name__
        return None

    # ------------------------------------------------------------------
    # Bulk helpers
    # ------------------------------------------------------------------

    def build_records(self, files: Sequence[ScannedFile], scan_id: Optional[int] = None):
        """Create ``ImageRecord`` objects for every image in ``files``."""
        from ..models.image_model import ImageRecord

        records = []
        for file in files:
            filename = os.path.basename(file.path)
            records.append(
                ImageRecord(
                    path=file.path,
                    filename=filename,
                    extension=os.path.splitext(filename)[1].lower(),
                    size=file.size,
                    created_at=file.created_at,
                    modified_at=file.modified_at,
                    scan_id=scan_id,
                )
            )
        return records
