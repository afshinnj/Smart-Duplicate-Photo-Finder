"""Local image-embedding engine.

Uses a small ONNX/TorchVision model to embed images semantically, so a photo of
a truck in the desert and a photo of the same truck from another angle can be
recognised as related even though almost no pixels match.

All heavyweight imports happen inside :meth:`load`. When the optional
dependencies are missing the engine simply reports itself as unavailable and
the rest of the application keeps working with the classical algorithms.
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence

import numpy as np

from ..core.config import AIEngineType, AISettings
from ..core.exceptions import AIEngineError
from ..core.logger import get_logger
from ..models.image_model import ImageRecord
from .ai_engine import AIEngine, AIEngineRegistry
from .model_manager import _lazy_import, _model_file_available, load_embedding_model

_log = get_logger("ai.embedding")


@AIEngineRegistry.register
class LocalEmbeddingEngine(AIEngine):
    """Semantic similarity with a locally stored embedding model."""

    engine_type = AIEngineType.LOCAL_EMBEDDING

    @classmethod
    def display_name(cls) -> str:
        return "Local Embedding Model"

    @classmethod
    def description(cls) -> str:
        return "Small local CNN embedding - understands content, not just pixels."

    @classmethod
    def is_available(cls) -> bool:
        # Offline-first: an ONNX runtime backend is only useful when the user
        # has actually placed a model file in the local models folder. The
        # TorchVision fallback would need to download weights, so it does not
        # count as "available" on its own.
        if _lazy_import("onnxruntime") is None:
            return False
        return _model_file_available()

    @classmethod
    def unavailable_reason(cls) -> Optional[str]:
        if _lazy_import("onnxruntime") is None:
            return (
                "Install 'onnxruntime' and place an ONNX image-embedding model in the "
                "models folder to enable local AI similarity. The rest of the "
                "application works without it."
            )
        if not _model_file_available():
            return (
                "No ONNX model found in the models folder. Drop an image-embedding "
                "model there (e.g. MobileNetV3) to enable AI similarity."
            )
        return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def load(self) -> None:
        if self._loaded:
            return
        try:
            self._model, self._preprocess = load_embedding_model(
                model_path=self.settings.model_path, use_gpu=self.settings.use_gpu
            )
        except Exception as exc:  # pragma: no cover - depends on optional deps
            raise AIEngineError(f"Cannot load the local embedding model: {exc}") from exc
        self._loaded = True
        _log.info("Local embedding model ready")

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def embed(self, records: Sequence[ImageRecord]) -> Dict[int, np.ndarray]:
        if not self._loaded:
            self.load()
        embeddings: Dict[int, np.ndarray] = {}
        for record in records:
            vector = self._embed_one(record)
            if vector is not None:
                embeddings[record.id] = vector  # type: ignore[index]
        return embeddings

    def _embed_one(self, record: ImageRecord) -> Optional[np.ndarray]:
        try:
            from PIL import Image

            with Image.open(record.path) as image:
                tensor = self._preprocess(image.convert("RGB"))
            output = self._model(tensor.unsqueeze(0) if tensor.ndim == 3 else tensor)
            vector = output.detach().cpu().numpy().ravel() if hasattr(output, "detach") else np.asarray(output).ravel()
            norm = np.linalg.norm(vector)
            if norm <= 0:
                return None
            return vector / norm
        except Exception as exc:
            _log.debug("Embedding failed for %s: %s", record.path, exc)
            return None

    def similarity(self, embedding_a: np.ndarray, embedding_b: np.ndarray) -> float:
        """Cosine similarity of two L2-normalised embeddings as a percentage."""
        if embedding_a is None or embedding_b is None:
            return 0.0
        dot = float(np.dot(embedding_a, embedding_b))
        return max(0.0, min(100.0, 100.0 * max(0.0, dot)))
