"""Domain model for the similarity result between two images."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from ..core.constants import rate_similarity


@dataclass
class SimilarityResult:
    """Pairwise comparison outcome with the individual algorithm scores."""

    image_a_id: int
    image_b_id: int
    score: float  # final combined score, 0-100
    method_scores: Dict[str, float] = field(default_factory=dict)
    matched_keypoints: Optional[int] = None
    is_exact_duplicate: bool = False

    @property
    def rating(self):
        return rate_similarity(self.score)

    def add_score(self, method: str, value: float) -> None:
        self.method_scores[method] = max(0.0, min(100.0, value))

    @property
    def confidence_label(self) -> str:
        """Short label describing the strongest contributing method."""
        if self.is_exact_duplicate:
            return "sha256"
        if not self.method_scores:
            return "none"
        return max(self.method_scores.items(), key=lambda item: item[1])[0]
