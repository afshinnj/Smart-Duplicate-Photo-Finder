"""Shared image loading helpers for the similarity engines."""

from __future__ import annotations

import os
from typing import Optional, Tuple

import numpy as np

from ..core.exceptions import ImageProcessingError
from ..core.logger import get_logger

_log = get_logger("similarity.loader")

# Comparison is always done at this resolution. It is high enough to be
# discriminative and low enough that 100k images stay in budget.
COMPARISON_SIZE = 256


def load_image_array(path: str, size: int = COMPARISON_SIZE) -> Optional[np.ndarray]:
    """Decode an image as an RGB float array of shape (size, size, 3)."""
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:  # pragma: no cover
        raise ImageProcessingError("Pillow is required to load images") from exc

    if not os.path.exists(path):
        return None
    try:
        with Image.open(path) as image:
            image = image.convert("RGB").resize((size, size), Image.Resampling.LANCZOS)
            return np.asarray(image, dtype=np.float32) / 255.0
    except UnidentifiedImageError:
        return None
    except (OSError, ValueError) as exc:
        _log.debug("Cannot load %s: %s", path, exc)
        return None
    except Exception as exc:  # never let one bad file kill a scan
        _log.debug("Unexpected load error for %s: %s", path, exc)
        return None


def load_grayscale_array(path: str, size: int = COMPARISON_SIZE) -> Optional[np.ndarray]:
    """Decode an image as a grayscale float array of shape (size, size)."""
    rgb = load_image_array(path, size)
    if rgb is None:
        return None
    # Rec. 601 luma weights, matching PIL's ``convert("L")``.
    return 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]


def to_uint8(array: np.ndarray) -> np.ndarray:
    return np.clip(array * 255.0, 0, 255).astype(np.uint8)


def safe_normalize(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(0.0, min(1.0, (value - low) / max(1e-9, high - low)))
