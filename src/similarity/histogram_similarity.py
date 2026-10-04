"""Colour histogram similarity.

Histograms are computed on the HSV hue and hue/saturation planes with an
equalised value channel, which makes the measurement invariant to global
brightness and contrast changes - the ``brightness +10%`` / ``contrast +10%``
variants from the specification score ~99 and ~88 instead of collapsing.

A grayscale copy genuinely loses all colour information, so this stage scores
it low; the structural and feature-based stages still recognise it as a match,
and the combined score in :mod:`similarity_engine` reflects that.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .image_loader import load_image_array, to_uint8

_HUE_BINS = 32
_SAT_BINS = 16


def _rgb_to_hsv(image: np.ndarray) -> np.ndarray:
    try:
        import cv2

        return cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    except ImportError:
        return _numpy_rgb_to_hsv(image)


def _numpy_rgb_to_hsv(rgb: np.ndarray) -> np.ndarray:
    red, green, blue = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    maximum = rgb.max(axis=2)
    minimum = rgb.min(axis=2)
    difference = np.where(maximum > 0, maximum - minimum, 0.0)

    hue = np.zeros_like(maximum)
    mask = maximum == red
    hue[mask] = 60.0 * (((green - blue) / np.maximum(difference, 1e-9))[mask] % 6.0)
    mask = maximum == green
    hue[mask] = 60.0 * (((blue - red) / np.maximum(difference, 1e-9))[mask] + 2.0)
    mask = maximum == blue
    hue[mask] = 60.0 * (((red - green) / np.maximum(difference, 1e-9))[mask] + 4.0)

    saturation = np.where(maximum > 0, difference / np.maximum(maximum, 1e-9), 0.0)
    hue = (hue % 360.0) * 0.5  # OpenCV stores hue in [0, 180)
    return np.stack([hue, saturation * 255.0, maximum * 255.0], axis=-1)


def _equalize_value(value: np.ndarray) -> np.ndarray:
    """Histogram-equalised value channel (removes brightness/contrast shifts)."""
    try:
        import cv2

        return cv2.equalizeHist(value.astype(np.uint8)).astype(np.float32)
    except ImportError:
        histogram = np.bincount(value.astype(np.uint8).ravel(), minlength=256).astype(np.float32)
        cumulative = histogram.cumsum()
        cumulative = (cumulative / max(1.0, cumulative[-1])) * 255.0
        return cumulative[value.astype(np.uint8)]


def _normalise(histogram: np.ndarray) -> Optional[np.ndarray]:
    total = float(histogram.sum())
    if total <= 0:
        return None
    return histogram / total


def compute_histogram(path_or_array, hue_bins: int = _HUE_BINS, sat_bins: int = _SAT_BINS) -> Optional[tuple]:
    """Return ``(hue_histogram, hue_sat_histogram)`` of an image.

    Accepts either a filesystem path or an RGB float array in [0, 1].
    """
    array = path_or_array
    if isinstance(path_or_array, str):
        array = load_image_array(path_or_array)
    if array is None:
        return None

    hsv = _rgb_to_hsv(to_uint8(array)).astype(np.float32)
    hue = hsv[:, :, 0]
    saturation = hsv[:, :, 1]
    value = _equalize_value(hsv[:, :, 2])

    hue_hist = _bin_count(hue, hue_bins, 0.0, 180.0)
    hue_sat_hist = _joint_bin_count(hue, saturation, hue_bins, sat_bins, 0.0, 180.0, 0.0, 256.0)

    hue_hist = _normalise(hue_hist)
    hue_sat_hist = _normalise(hue_sat_hist)
    if hue_hist is None or hue_sat_hist is None:
        return None
    return hue_hist, hue_sat_hist


def _bin_count(values: np.ndarray, bins: int, low: float, high: float) -> np.ndarray:
    step = (high - low) / bins
    indices = np.clip(((values - low) / step).astype(np.int32), 0, bins - 1)
    return np.bincount(indices.ravel(), minlength=bins).astype(np.float32)


def _joint_bin_count(
    values_a: np.ndarray,
    values_b: np.ndarray,
    bins_a: int,
    bins_b: int,
    low_a: float,
    high_a: float,
    low_b: float,
    high_b: float,
) -> np.ndarray:
    step_a = (high_a - low_a) / bins_a
    step_b = (high_b - low_b) / bins_b
    index_a = np.clip(((values_a - low_a) / step_a).astype(np.int32), 0, bins_a - 1)
    index_b = np.clip(((values_b - low_b) / step_b).astype(np.int32), 0, bins_b - 1)
    flat = index_a * bins_b + index_b
    return np.bincount(flat.ravel(), minlength=bins_a * bins_b).astype(np.float32).reshape(
        bins_a, bins_b
    )


def _correlation(hist_a: np.ndarray, hist_b: np.ndarray) -> float:
    try:
        import cv2

        return max(0.0, float(cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL)))
    except ImportError:
        a = hist_a.ravel() - hist_a.mean()
        b = hist_b.ravel() - hist_b.mean()
        denominator = np.sqrt(float((a * a).sum()) * float((b * b).sum()))
        if denominator <= 1e-12:
            return 0.0
        return max(0.0, float((a * b).sum() / denominator))


def histogram_similarity(path_a: str, path_b: str) -> Optional[float]:
    """Histogram-based similarity of two image files as a 0-100 score."""
    hist_a = compute_histogram(path_a)
    hist_b = compute_histogram(path_b)
    if hist_a is None or hist_b is None:
        return None
    return compare_histograms(hist_a, hist_b)


def compare_histograms(hist_a: tuple, hist_b: tuple) -> float:
    """Blend the hue and hue/saturation correlations into one score."""
    hue_a, hue_sat_a = hist_a
    hue_b, hue_sat_b = hist_b
    hue_score = _correlation(hue_a, hue_b)
    hue_sat_score = _correlation(hue_sat_a, hue_sat_b)
    similarity = 0.45 * hue_score + 0.55 * hue_sat_score
    return max(0.0, min(100.0, 100.0 * similarity))
