"""Local-feature matching with ORB/SIFT for crop and re-edit detection.

Pixel-based methods (perceptual hashes, SSIM) fail when a photo is cropped or
rotated, because the pixel grid no longer lines up. Local features describe
patches around salient keypoints and are matched invariantly to scale and
rotation, so a 1920x1080 original and its 1200x1080 crop still match strongly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from ..core.logger import get_logger
from .image_loader import load_grayscale_array, to_uint8

_log = get_logger("similarity.feature_matching")

_MIN_MATCHES = 8
_RATIO_THRESHOLD = 0.75


@dataclass
class FeatureMatchResult:
    """Outcome of matching two sets of keypoints."""

    score: float  # 0-100
    match_count: int
    inlier_count: int
    is_cropped: bool
    method: str


def _create_detector(method: str):
    import cv2

    if method == "sift":
        try:
            return cv2.SIFT_create(), "sift"
        except (AttributeError, cv2.error):  # SIFT not available in some builds
            _log.debug("SIFT unavailable, falling back to ORB")
    return cv2.ORB_create(nfeatures=500), "orb"


def _detect_and_compute(image: np.ndarray, method: str):
    import cv2

    detector, resolved = _create_detector(method)
    grayscale = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image
    keypoints, descriptors = detector.detectAndCompute(grayscale, None)
    return keypoints, descriptors, resolved


def _match_descriptors(descriptors_a, descriptors_b, method: str) -> List[tuple]:
    import cv2

    if descriptors_a is None or descriptors_b is None:
        return []
    if descriptors_a.dtype != descriptors_b.dtype:
        # ORB uses uint8 (Hamming), SIFT uses float32 (L2).
        descriptors_b = descriptors_b.astype(descriptors_a.dtype)

    if method == "sift":
        matcher = cv2.BFMatcher()
        raw_matches = matcher.knnMatch(descriptors_a, descriptors_b, k=2)
        good = []
        for first, second in raw_matches:
            if second.distance > 0 and first.distance < _RATIO_THRESHOLD * second.distance:
                good.append(first)
        return good

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    return list(matcher.match(descriptors_a, descriptors_b))


def _homography_inliers(
    keypoints_a, keypoints_b, matches, min_matches: int = _MIN_MATCHES
) -> Tuple[int, Optional[np.ndarray]]:
    """Count matches consistent with a single geometric transformation."""
    if len(matches) < min_matches:
        return 0, None

    import cv2

    source = np.float32([keypoints_a[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    destination = np.float32([keypoints_b[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)

    matrix, mask = cv2.findHomography(source, destination, cv2.RANSAC, 5.0)
    if mask is None:
        return 0, None
    return int(mask.ravel().sum()), matrix


def _area_ratio(matrix: Optional[np.ndarray]) -> float:
    """Scale factor implied by a homography - detects cropping/resizing."""
    if matrix is None:
        return 1.0
    try:
        determinant = float(matrix[0, 0] * matrix[1, 1] - matrix[0, 1] * matrix[1, 0])
        return abs(determinant)
    except (IndexError, TypeError):
        return 1.0


def feature_similarity(
    path_a: str,
    path_b: str,
    method: str = "orb",
    max_keypoints: int = 500,
) -> Optional[FeatureMatchResult]:
    """Compare two images using local features.

    Returns ``None`` when either image cannot be decoded. The score rewards a
    high ratio of geometrically consistent matches, which is what makes
    cropped versions of the same photo still group together.
    """
    image_a = load_grayscale_array(path_a, size=512)
    image_b = load_grayscale_array(path_b, size=512)
    if image_a is None or image_b is None:
        return None

    try:
        import cv2  # noqa: F401

        keypoints_a, descriptors_a, resolved_a = _detect_and_compute(
            to_uint8(image_a), method
        )
        keypoints_b, descriptors_b, resolved_b = _detect_and_compute(
            to_uint8(image_b), method
        )
    except ImportError:
        return None
    except Exception as exc:  # OpenCV can reject degenerate images
        _log.debug("Feature extraction failed for %s / %s: %s", path_a, path_b, exc)
        return None

    resolved = resolved_a
    matches = _match_descriptors(descriptors_a, descriptors_b, resolved)
    if not matches:
        return FeatureMatchResult(0.0, 0, 0, False, resolved)

    inliers, matrix = _homography_inliers(keypoints_a, keypoints_b, matches)
    keypoint_count = max(1, min(len(keypoints_a), len(keypoints_b), max_keypoints))

    # Strong matches as a fraction of the smaller keypoint set.
    strength = len(matches) / keypoint_count
    inlier_ratio = inliers / max(1, len(matches))
    score = 100.0 * min(1.0, strength * (0.4 + 0.6 * inlier_ratio))

    area_ratio = _area_ratio(matrix)
    is_cropped = bool(0.15 < area_ratio < 0.95 or 1.05 < area_ratio < 6.0)

    return FeatureMatchResult(
        score=max(0.0, min(100.0, score)),
        match_count=len(matches),
        inlier_count=inliers,
        is_cropped=is_cropped,
        method=resolved,
    )
