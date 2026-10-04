"""Central similarity engine that blends every algorithm into one score.

The pipeline stages (file hash, perceptual hash, histogram, SSIM, features, AI)
are all optional. When a stage is disabled its weight is redistributed across
the remaining ones, so the combined score always stays meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from ..core.config import SimilaritySettings
from ..core.logger import get_logger
from ..hashing import perceptual_hash
from ..models.image_model import ImageRecord
from ..models.similarity_result import SimilarityResult

_log = get_logger("similarity.engine")

# Default weights of the perceptual-hash components inside the pHash stage.
_PERCEPTUAL_WEIGHTS = {"ahash": 0.25, "dhash": 0.25, "phash": 0.35, "whash": 0.15}

# Default weights of the stages that need the image re-decoded from disk.
_STAGE_WEIGHTS = {
    "perceptual": 0.55,
    "histogram": 0.15,
    "ssim": 0.15,
    "features": 0.15,
}


@dataclass
class ComparisonPlan:
    """Which expensive stages actually have to run for a candidate pair."""

    needs_histogram: bool = False
    needs_ssim: bool = False
    needs_features: bool = False
    exact: bool = False


class SimilarityEngine:
    """Combines hash, histogram, structural and feature-based similarity."""

    def __init__(self, settings: Optional[SimilaritySettings] = None) -> None:
        self.settings = settings or SimilaritySettings()
        self._weights = dict(_STAGE_WEIGHTS)
        if not self.settings.enable_histogram:
            self._weights.pop("histogram", None)
        if not self.settings.enable_ssim:
            self._weights.pop("ssim", None)
        if not self.settings.enable_feature_matching:
            self._weights.pop("features", None)

    # ------------------------------------------------------------------
    # Cheap pre-checks
    # ------------------------------------------------------------------

    @staticmethod
    def exact_duplicate(record_a: ImageRecord, record_b: ImageRecord) -> bool:
        return (
            bool(record_a.sha256)
            and record_a.sha256 == record_b.sha256
        )

    def perceptual_score(self, record_a: ImageRecord, record_b: ImageRecord) -> Optional[float]:
        """Weighted score over the four perceptual hashes."""
        hashes_a = {
            "ahash": record_a.ahash,
            "dhash": record_a.dhash,
            "phash": record_a.phash,
            "whash": record_a.whash,
        }
        hashes_b = {
            "ahash": record_b.ahash,
            "dhash": record_b.dhash,
            "phash": record_b.phash,
            "whash": record_b.whash,
        }
        return perceptual_hash.PerceptualHashEngine.combined_similarity(hashes_a, hashes_b)

    def plan(self, record_a: ImageRecord, record_b: ImageRecord, perceptual_score: Optional[float]) -> ComparisonPlan:
        """Decide which expensive stages are worth running for a candidate pair.

        Feature matching is by far the most expensive stage, so it is only used
        when the cheap hashes already suggest the images are related.
        """
        if self.exact_duplicate(record_a, record_b):
            return ComparisonPlan(exact=True)

        score = perceptual_score
        if score is None:
            score = 0.0
        plan = ComparisonPlan(
            needs_histogram="histogram" in self._weights,
            needs_ssim="ssim" in self._weights,
            needs_features=False,
        )
        # Only run feature matching for pairs the cheap hashes find promising,
        # including cases where a crop makes perceptual hashes disagree.
        if "features" in self._weights and (score >= 45.0 or record_a.size != record_b.size):
            plan.needs_features = True
        return plan

    # ------------------------------------------------------------------
    # Full comparison
    # ------------------------------------------------------------------

    def compare(
        self,
        record_a: ImageRecord,
        record_b: ImageRecord,
        ai_similarity: Optional[callable] = None,
    ) -> SimilarityResult:
        """Produce the final similarity result for a pair of images."""
        result = SimilarityResult(
            image_a_id=record_a.id or -1,
            image_b_id=record_b.id or -1,
            score=0.0,
        )

        if self.exact_duplicate(record_a, record_b):
            result.is_exact_duplicate = True
            result.score = 100.0
            result.add_score("sha256", 100.0)
            return result

        perceptual = self.perceptual_score(record_a, record_b)
        if perceptual is not None:
            result.add_score("perceptual", perceptual)
        plan = self.plan(record_a, record_b, perceptual)

        if plan.needs_histogram:
            from .histogram_similarity import histogram_similarity

            score = histogram_similarity(record_a.path, record_b.path)
            if score is not None:
                result.add_score("histogram", score)

        if plan.needs_ssim:
            from .structural_similarity import ssim_similarity

            score = ssim_similarity(record_a.path, record_b.path)
            if score is not None:
                result.add_score("ssim", score)

        if plan.needs_features:
            from .feature_similarity import feature_similarity

            feature_result = feature_similarity(
                record_a.path, record_b.path, max_keypoints=self.settings.feature_max_matches
            )
            if feature_result is not None and feature_result.match_count > 0:
                result.add_score("features", feature_result.score)
                result.matched_keypoints = feature_result.match_count

        if ai_similarity is not None:
            ai_score = ai_similarity(record_a, record_b)
            if ai_score is not None:
                result.add_score("ai", ai_score)

        result.score = self._blend(result.method_scores)

        # When every perceptual hash agrees almost perfectly the images contain
        # the same content even if a global transform (e.g. desaturation)
        # tanks the colour histogram. Floor the score so such variants are
        # still grouped instead of being split apart by a single weak stage.
        if perceptual is not None and perceptual >= 98.0:
            result.score = max(result.score, 95.0)

        return result

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _blend(self, method_scores: Dict[str, float]) -> float:
        """Weighted mean of the contributing stage scores (already 0-100)."""
        weights = self._weights_for(method_scores)
        total_weight = sum(weights.values())
        if total_weight <= 0:
            return 0.0
        total = sum(weights[method] * score for method, score in method_scores.items())
        return max(0.0, min(100.0, total / total_weight))

    def _weights_for(self, method_scores: Dict[str, float]) -> Dict[str, float]:
        weights: Dict[str, float] = {}
        for method in method_scores:
            if method == "ai":
                # AI is semantic and is always reported separately; the final
                # score treats it as an additional signal rather than a stage.
                continue
            weight = self._weights.get(method)
            if weight is None and method in _PERCEPTUAL_WEIGHTS:
                weight = self._weights.get("perceptual")
            if weight is not None:
                weights[method] = weight
        return weights

    @staticmethod
    def rating_label(score: float) -> str:
        from ..core.constants import SimilarityRating, rate_similarity

        mapping = {
            SimilarityRating.EXACT: "identical",
            SimilarityRating.ALMOST_SAME: "almost identical",
            SimilarityRating.VERY_SIMILAR: "very similar",
            SimilarityRating.SIMILAR: "similar",
            SimilarityRating.POSSIBLY_RELATED: "possibly related",
            SimilarityRating.DIFFERENT: "different",
        }
        return mapping[rate_similarity(score)]
