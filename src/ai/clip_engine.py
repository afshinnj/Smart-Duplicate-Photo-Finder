"""CLIP image-encoder plugin (reserved for a future release).

The architecture already supports plugging in a CLIP encoder for true content
understanding - recognising that two photos show the same object from
different angles. The model weights are deliberately not bundled or downloaded;
this engine reports itself as unavailable until a future release ships them.
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from ..core.config import AIEngineType
from ..models.image_model import ImageRecord
from .ai_engine import AIEngine, AIEngineRegistry


@AIEngineRegistry.register
class CLIPEngine(AIEngine):
    """Semantic similarity with a CLIP image encoder."""

    engine_type = AIEngineType.CLIP

    @classmethod
    def display_name(cls) -> str:
        return "CLIP"

    @classmethod
    def description(cls) -> str:
        return (
            "CLIP image embeddings understand image content semantically "
            "(e.g. the same object photographed from different angles)."
        )

    @classmethod
    def is_available(cls) -> bool:
        return False

    @classmethod
    def unavailable_reason(cls) -> Optional[str]:
        return "The CLIP plugin is reserved for a future release."

    def load(self) -> None:
        raise ImportError("CLIP support is not implemented yet")

    def embed(self, records: Sequence[ImageRecord]) -> dict[int, np.ndarray]:
        return {}

    def similarity(self, embedding_a: np.ndarray, embedding_b: np.ndarray) -> float:
        return 0.0
