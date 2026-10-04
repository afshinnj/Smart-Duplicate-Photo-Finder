"""Plugin architecture for optional AI-based semantic similarity.

The core application never imports a deep-learning framework. Engines are
discovered through a small registry, and every engine reports whether its
dependencies are present. When they are not - or when the user keeps AI
disabled - the application runs entirely offline with the classical algorithms.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

from ..core.config import AIEngineType, AISettings
from ..core.exceptions import AIEngineError
from ..core.logger import get_logger
from ..models.image_model import ImageRecord

_log = get_logger("ai.engine")


@dataclass
class AIEngineInfo:
    """Static description of a plugin shown in the settings page."""

    engine_type: AIEngineType
    name: str
    description: str
    requires_download: bool
    available: bool
    unavailable_reason: Optional[str] = None


class AIEngine(abc.ABC):
    """Common interface for every semantic similarity plugin."""

    engine_type: AIEngineType = AIEngineType.DISABLED

    def __init__(self, settings: AISettings) -> None:
        self.settings = settings
        self._loaded = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @classmethod
    @abc.abstractmethod
    def is_available(cls) -> bool:
        """Whether the optional dependencies of this engine are installed."""

    @classmethod
    @abc.abstractmethod
    def unavailable_reason(cls) -> Optional[str]:
        """Human-readable explanation when the engine cannot be used."""

    def load(self) -> None:
        """Perform the (possibly slow) model initialisation."""
        self._loaded = True

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def embed(self, records: Sequence[ImageRecord]) -> Dict[int, np.ndarray]:
        """Map every image record to a fixed-size embedding vector."""

    @abc.abstractmethod
    def similarity(self, embedding_a: np.ndarray, embedding_b: np.ndarray) -> float:
        """Semantic similarity of two embeddings as a 0-100 score."""

    def embed_and_score(
        self, record_a: ImageRecord, record_b: ImageRecord
    ) -> Optional[float]:
        """Convenience helper returning the similarity of two records."""
        embeddings = self.embed([record_a, record_b])
        if len(embeddings) < 2:
            return None
        return self.similarity(embeddings[record_a.id], embeddings[record_b.id])


class DisabledAIEngine(AIEngine):
    """No-op engine used when AI is switched off (the default)."""

    engine_type = AIEngineType.DISABLED

    @classmethod
    def is_available(cls) -> bool:
        return True

    @classmethod
    def unavailable_reason(cls) -> Optional[str]:
        return None

    def load(self) -> None:
        self._loaded = True

    def embed(self, records: Sequence[ImageRecord]) -> Dict[int, np.ndarray]:
        return {}

    def similarity(self, embedding_a: np.ndarray, embedding_b: np.ndarray) -> float:
        return 0.0


class AIEngineRegistry:
    """Discovers and instantiates the available AI plugins."""

    _engines: Dict[AIEngineType, type[AIEngine]] = {}

    @classmethod
    def register(cls, engine_class: type[AIEngine]) -> type[AIEngine]:
        cls._engines[engine_class.engine_type] = engine_class
        return engine_class

    @classmethod
    def engine_types(cls) -> List[AIEngineType]:
        return list(cls._engines)

    @classmethod
    def describe_all(cls) -> List[AIEngineInfo]:
        infos = [
            AIEngineInfo(
                engine_type=AIEngineType.DISABLED,
                name="Disabled",
                description="Run without AI - fully offline, classical algorithms only.",
                requires_download=False,
                available=True,
            )
        ]
        from .clip_engine import CLIPEngine
        from .embedding_engine import LocalEmbeddingEngine

        for engine_class in (LocalEmbeddingEngine, CLIPEngine):
            infos.append(
                AIEngineInfo(
                    engine_type=engine_class.engine_type,
                    name=engine_class.display_name(),
                    description=engine_class.description(),
                    requires_download=True,
                    available=engine_class.is_available(),
                    unavailable_reason=engine_class.unavailable_reason(),
                )
            )
        return infos

    @classmethod
    def create(cls, settings: AISettings) -> AIEngine:
        """Build the engine chosen in the settings (falls back to Disabled)."""
        if settings.engine == AIEngineType.DISABLED:
            return DisabledAIEngine(settings)

        engine_class = cls._engines.get(settings.engine)
        if engine_class is None:
            _log.warning("Unknown AI engine %s, falling back to Disabled", settings.engine)
            return DisabledAIEngine(settings)
        if not engine_class.is_available():
            raise AIEngineError(
                f"AI engine '{engine_class.display_name()}' is unavailable: "
                f"{engine_class.unavailable_reason() or 'dependencies missing'}"
            )
        return engine_class(settings)


def create_ai_engine(settings: AISettings) -> AIEngine:
    """Factory honouring the user configuration."""
    try:
        return AIEngineRegistry.create(settings)
    except AIEngineError as exc:
        _log.warning("AI engine unavailable, continuing without AI: %s", exc)
        return DisabledAIEngine(settings)
