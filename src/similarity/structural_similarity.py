"""Structural similarity (SSIM) and a fast structural fallback.

SSIM compares local patterns of pixel intensities that have been normalised for
luminance and contrast, which makes it sensitive to the *structure* of a scene
while ignoring global brightness or contrast shifts.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .image_loader import load_grayscale_array

_WINDOW_SIZE = 8
_C1 = (0.01 * 255.0) ** 2
_C2 = (0.03 * 255.0) ** 2


def ssim_similarity(path_a: str, path_b: str, size: int = 256) -> Optional[float]:
    """SSIM index of two images expressed as a 0-100 score."""
    image_a = load_grayscale_array(path_a, size)
    image_b = load_grayscale_array(path_b, size)
    if image_a is None or image_b is None:
        return None
    return ssim_score(image_a, image_b)


def ssim_score(image_a: np.ndarray, image_b: np.ndarray) -> float:
    """Mean SSIM over non-overlapping 8x8 windows between two grayscale arrays."""
    if image_a.shape != image_b.shape:
        image_b = _resize_to(image_b, image_a.shape)

    a = (image_a * 255.0).astype(np.float64)
    b = (image_b * 255.0).astype(np.float64)

    height, width = a.shape
    window = _WINDOW_SIZE
    if height < window or width < window:
        return _global_ssim(a, b) * 100.0

    scores = []
    for y in range(0, window * (height // window), window):
        for x in range(0, window * (width // window), window):
            patch_a = a[y : y + window, x : x + window]
            patch_b = b[y : y + window, x : x + window]
            scores.append(_global_ssim(patch_a, patch_b))
    return float(np.mean(scores)) * 100.0


def _global_ssim(a: np.ndarray, b: np.ndarray) -> float:
    mean_a = a.mean()
    mean_b = b.mean()
    variance_a = a.var()
    variance_b = b.var()
    covariance = float(((a - mean_a) * (b - mean_b)).mean())

    numerator = (2.0 * mean_a * mean_b + _C1) * (2.0 * covariance + _C2)
    denominator = (mean_a * mean_a + mean_b * mean_b + _C1) * (
        variance_a + variance_b + _C2
    )
    if denominator <= 0:
        return 0.0
    return max(-1.0, min(1.0, numerator / denominator))


def _resize_to(image: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    try:
        import cv2

        return cv2.resize(image, (shape[1], shape[0]), interpolation=cv2.INTER_AREA)
    except ImportError:
        # Nearest-neighbour fallback used only when OpenCV is unavailable.
        rows = np.linspace(0, image.shape[0] - 1, shape[0]).round().astype(int)
        cols = np.linspace(0, image.shape[1] - 1, shape[1]).round().astype(int)
        return image[np.ix_(rows, cols)]


def mean_absolute_difference(path_a: str, path_b: str, size: int = 128) -> Optional[float]:
    """Fast pixel-difference score used when SSIM is disabled."""
    image_a = load_grayscale_array(path_a, size)
    image_b = load_grayscale_array(path_b, size)
    if image_a is None or image_b is None:
        return None
    if image_a.shape != image_b.shape:
        image_b = _resize_to(image_b, image_a.shape)
    difference = float(np.mean(np.abs(image_a - image_b)))
    return max(0.0, min(100.0, 100.0 * (1.0 - difference)))
