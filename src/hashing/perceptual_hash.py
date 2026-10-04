"""Perceptual hashing: aHash, dHash, pHash and wHash.

Perceptual hashes describe the *content* of an image rather than its bytes, so
resized, re-compressed or re-encoded copies of the same photo still produce
nearly identical hashes. All hashes are 64 bits stored as 16 hex characters.
"""

from __future__ import annotations

import os
from typing import Optional

import numpy as np

from ..core import constants
from ..core.exceptions import ImageProcessingError
from ..core.logger import get_logger

_log = get_logger("hashing.perceptual_hash")

HASH_BITS = constants.HASH_SIZE * constants.HASH_SIZE


def _load_grayscale(path: str, size: int) -> Optional[np.ndarray]:
    """Decode an image as a float grayscale matrix of the given square size."""
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:  # pragma: no cover
        raise ImageProcessingError("Pillow is required for perceptual hashing") from exc

    try:
        with Image.open(path) as image:
            image = image.convert("L").resize((size, size), Image.Resampling.LANCZOS)
            return np.asarray(image, dtype=np.float64)
    except UnidentifiedImageError:
        _log.debug("Unidentified image: %s", path)
        return None
    except (OSError, ValueError) as exc:
        _log.debug("Cannot decode %s: %s", path, exc)
        return None
    except Exception as exc:  # corrupted images must not break the scan
        _log.debug("Unexpected decode error for %s: %s", path, exc)
        return None


def _bits_to_hex(bits: np.ndarray) -> str:
    """Pack a boolean bit matrix into a hex string (row-major, MSB first)."""
    flat = bits.flatten().astype(np.uint8)
    value = int("".join(str(int(bit)) for bit in flat), 2)
    return format(value, f"0{(len(flat) + 3) // 4}x")


def _hex_to_bits(value: str, length: int = HASH_BITS) -> np.ndarray:
    try:
        integer = int(value, 16)
    except (TypeError, ValueError):
        return np.zeros(length, dtype=bool)
    bits = [(integer >> i) & 1 for i in range(length - 1, -1, -1)]
    return np.array(bits, dtype=bool)


# ---------------------------------------------------------------------------
# Individual algorithms
# ---------------------------------------------------------------------------


def a_hash(path: str, size: int = constants.HASH_SIZE) -> Optional[str]:
    """Average hash: bit set when pixel is above the mean intensity."""
    matrix = _load_grayscale(path, size)
    if matrix is None:
        return None
    return _bits_to_hex(matrix > matrix.mean())


def d_hash(path: str, size: int = constants.HASH_SIZE) -> Optional[str]:
    """Difference hash: captures the horizontal gradient (aspect ratio aware)."""
    matrix = _load_grayscale(path, size + 1)
    if matrix is None:
        return None
    return _bits_to_hex(matrix[:, 1:] > matrix[:, :-1])


def p_hash(path: str, size: int = constants.HASH_SIZE) -> Optional[str]:
    """Perceptual hash based on the low-frequency DCT coefficients."""
    matrix = _load_grayscale(path, size * 4)
    if matrix is None:
        return None
    try:
        from scipy.fftpack import dct  # type: ignore

        coefficients = dct(dct(matrix, axis=0, norm="ortho"), axis=1, norm="ortho")
    except ImportError:
        # SciPy is optional: fall back to a pure-NumPy DCT-II.
        coefficients = _dct2(matrix)

    top_left = coefficients[:size, :size]
    # Drop the DC term so overall brightness does not dominate.
    values = top_left.flatten()[1:]
    median = np.median(values)
    bits = values > median
    return format(int("".join(str(int(bit)) for bit in bits), 2), f"0{(len(bits) + 3) // 4}x")


def w_hash(path: str, size: int = constants.HASH_SIZE) -> Optional[str]:
    """Wavelet hash based on Haar wavelet LL coefficients."""
    matrix = _load_grayscale(path, size * 2)
    if matrix is None:
        return None
    try:
        import pywt  # type: ignore

        coefficients = pywt.wavedec2(matrix, "haar", level=1)
        low = coefficients[0]
    except ImportError:
        low = _haar_low_pass(matrix)

    values = low.flatten()
    median = np.median(values)
    bits = values > median
    return format(int("".join(str(int(bit)) for bit in bits), 2), f"0{(len(bits) + 3) // 4}x")


# ---------------------------------------------------------------------------
# Pure NumPy fallbacks (keep the app working without SciPy/PyWavelets)
# ---------------------------------------------------------------------------


def _dct2(matrix: np.ndarray) -> np.ndarray:
    def dct1d(vector: np.ndarray) -> np.ndarray:
        size = len(vector)
        index = np.arange(size)
        scale = np.sqrt(2.0 / size) * np.cos(np.pi * (2 * index + 1) * index[:, None] / (2 * size))
        scale[0] *= np.sqrt(0.5)
        return scale @ vector

    return dct1d(dct1d(matrix.T).T)


def _haar_low_pass(matrix: np.ndarray) -> np.ndarray:
    size = matrix.shape[0] // 2
    rows = (matrix[0 : 2 * size : 2, :] + matrix[1 : 2 * size : 2, :]) / 2.0
    return (rows[:, 0 : 2 * size : 2] + rows[:, 1 : 2 * size : 2]) / 2.0


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------


def hamming_distance(hash_a: Optional[str], hash_b: Optional[str]) -> Optional[int]:
    """Number of differing bits between two perceptual hashes."""
    if not hash_a or not hash_b:
        return None
    bits_a = _hex_to_bits(hash_a)
    bits_b = _hex_to_bits(hash_b)
    length = min(len(bits_a), len(bits_b))
    return int(np.count_nonzero(bits_a[:length] != bits_b[:length]))


def similarity_percentage(hash_a: Optional[str], hash_b: Optional[str]) -> Optional[float]:
    """Convert a Hamming distance into a 0-100 similarity score."""
    distance = hamming_distance(hash_a, hash_b)
    if distance is None:
        return None
    return max(0.0, min(100.0, 100.0 * (1.0 - distance / HASH_BITS)))


class PerceptualHashEngine:
    """Computes every perceptual hash for an image in one decode pass."""

    def __init__(self, size: int = constants.HASH_SIZE) -> None:
        self.size = size

    def compute_all(self, path: str) -> dict[str, Optional[str]]:
        """Return aHash/dHash/pHash/wHash for ``path`` (values may be ``None``)."""
        try:
            return {
                "ahash": a_hash(path, self.size),
                "dhash": d_hash(path, self.size),
                "phash": p_hash(path, self.size),
                "whash": w_hash(path, self.size),
            }
        except Exception as exc:  # noqa: BLE001 - hashing must never crash
            _log.debug("Perceptual hashing failed for %s: %s", path, exc)
            return {"ahash": None, "dhash": None, "phash": None, "whash": None}

    @staticmethod
    def combined_similarity(
        hashes_a: dict[str, Optional[str]], hashes_b: dict[str, Optional[str]]
    ) -> Optional[float]:
        """Weighted mean of the four perceptual hash similarity scores."""
        weights = {"ahash": 0.25, "dhash": 0.25, "phash": 0.35, "whash": 0.15}
        total_weight = 0.0
        total_score = 0.0
        for key, weight in weights.items():
            score = similarity_percentage(hashes_a.get(key), hashes_b.get(key))
            if score is None:
                continue
            total_score += weight * score
            total_weight += weight
        if total_weight == 0.0:
            return None
        return total_score / total_weight
