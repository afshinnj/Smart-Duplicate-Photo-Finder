"""Qt worker that scores the similarity of image pairs."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import QThread, Signal

from ..core.config import SimilaritySettings
from ..core.logger import get_logger
from ..models.image_model import ImageRecord
from ..models.similarity_result import SimilarityResult
from ..similarity.similarity_engine import SimilarityEngine

_log = get_logger("workers.similarity")


class SimilarityWorker(QThread):
    """Runs pairwise comparisons off the UI thread (used by the viewer)."""

    pair_done = Signal(SimilarityResult)
    all_done = Signal(list)  # list[SimilarityResult]
    progress = Signal(int, int)
    failed = Signal(str)

    def __init__(
        self,
        pairs: Sequence[Tuple[ImageRecord, ImageRecord]],
        settings: Optional[SimilaritySettings] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.pairs = list(pairs)
        self.engine = SimilarityEngine(settings)
        self._cancel = False

    def run(self) -> None:
        results: List[SimilarityResult] = []
        total = len(self.pairs)
        try:
            for index, (record_a, record_b) in enumerate(self.pairs, start=1):
                if self._cancel:
                    break
                result = self.engine.compare(record_a, record_b)
                results.append(result)
                self.pair_done.emit(result)
                if index % 5 == 0 or index == total:
                    self.progress.emit(index, total)
            self.all_done.emit(results)
        except Exception as exc:
            _log.exception("Similarity worker failed")
            self.failed.emit(str(exc))

    def cancel(self) -> None:
        self._cancel = True
