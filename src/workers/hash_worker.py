"""Qt worker that hashes a batch of files off the UI thread."""

from __future__ import annotations

from typing import Dict, Sequence

from PySide6.QtCore import QThread, Signal

from ..core.logger import get_logger
from ..hashing.file_hash import FileHashEngine
from ..hashing.perceptual_hash import PerceptualHashEngine

_log = get_logger("workers.hash")


class HashWorker(QThread):
    """Computes SHA-256 and perceptual hashes for a list of file paths."""

    progress = Signal(int, int)  # processed, total
    file_done = Signal(str, dict)  # path -> hashes
    finished_hashing = Signal(dict)  # path -> hashes
    failed = Signal(str)

    def __init__(self, paths: Sequence[str], include_perceptual: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.paths = list(paths)
        self.include_perceptual = include_perceptual
        self._cancel = False

    def run(self) -> None:
        file_engine = FileHashEngine()
        perceptual_engine = PerceptualHashEngine()
        results: Dict[str, dict] = {}
        total = len(self.paths)

        try:
            for index, path in enumerate(self.paths, start=1):
                if self._cancel:
                    break
                entry: Dict[str, object] = {"sha256": file_engine.hash_file(path)}
                if self.include_perceptual:
                    entry.update(perceptual_engine.compute_all(path))
                results[path] = entry
                self.file_done.emit(path, entry)
                if index % 25 == 0 or index == total:
                    self.progress.emit(index, total)
            self.finished_hashing.emit(results)
        except Exception as exc:
            _log.exception("Hash worker failed")
            self.failed.emit(str(exc))

    def cancel(self) -> None:
        self._cancel = True
