"""Thumbnail loading with an on-disk cache and an async thread pool.

Decoding happens on worker threads (via :class:`ThumbnailJob`) so scrolling a
large results list never blocks the UI thread. Once decoded, a thumbnail is
stored both in the per-process LRU cache and on disk under
``constants.thumbnails_dir()`` so later runs of the application reuse it.
"""

from __future__ import annotations

import hashlib
import os
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QPixmap

from ..core import constants
from ..core.logger import get_logger

_log = get_logger("ui.thumbnails")

_CACHE_LIMIT = 400


def _pixmap_from_pil(image) -> QPixmap:
    """Convert a PIL image to a QPixmap without touching the clipboard."""
    from io import BytesIO

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    pixmap = QPixmap()
    pixmap.loadFromData(buffer.getvalue(), "PNG")
    return pixmap


class ThumbnailCache:
    """LRU cache of decoded thumbnails backed by files on disk."""

    def __init__(self, size: int = constants.THUMBNAIL_SIZE, limit: int = _CACHE_LIMIT) -> None:
        self.size = size
        self._limit = limit
        self._memory: OrderedDict[str, QPixmap] = OrderedDict()

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _cache_path(self, path: str) -> str:
        digest = hashlib.sha256(os.path.abspath(path).encode("utf-8")).hexdigest()
        return os.path.join(
            constants.thumbnails_dir(), f"{digest}_{self.size}.png"
        )

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get(self, path: str) -> Optional[QPixmap]:
        """Return the cached thumbnail, or ``None`` when it must be decoded."""
        if path in self._memory:
            self._memory.move_to_end(path)
            return self._memory[path]

        cached_file = self._cache_path(path)
        if os.path.exists(cached_file):
            pixmap = QPixmap(cached_file)
            if not pixmap.isNull():
                self._remember(path, pixmap)
                return pixmap
        return None

    def load(self, path: str) -> Optional[QPixmap]:
        """Decode ``path`` when the cache has no thumbnail for it yet."""
        pixmap = self.get(path)
        if pixmap is not None:
            return pixmap
        pixmap = self._decode(path)
        if pixmap is not None:
            self.store(path, pixmap)
        return pixmap

    def _decode(self, path: str) -> Optional[QPixmap]:
        try:
            from PIL import Image

            with Image.open(path) as image:
                image.load()
                thumbnail = image.convert("RGB")
                thumbnail.thumbnail((self.size, self.size))
                return _pixmap_from_pil(thumbnail)
        except Exception as exc:  # unsupported / corrupt files are skipped
            _log.debug("Cannot create thumbnail for %s: %s", path, exc)
            return None

    def store(self, path: str, pixmap: QPixmap) -> None:
        self._remember(path, pixmap)
        try:
            pixmap.save(self._cache_path(path), "PNG")
        except Exception as exc:
            _log.debug("Cannot persist thumbnail for %s: %s", path, exc)

    def _remember(self, path: str, pixmap: QPixmap) -> None:
        self._memory[path] = pixmap
        self._memory.move_to_end(path)
        while len(self._memory) > self._limit:
            self._memory.popitem(last=False)


class _JobSignals(QObject):
    finished = Signal(str, object)  # path -> QPixmap | None


class ThumbnailJob(QRunnable):
    """Decodes one thumbnail off the UI thread."""

    def __init__(self, cache: ThumbnailCache, path: str, size: int, signals: "_JobSignals") -> None:
        super().__init__()
        self.cache = cache
        self.path = path
        self.size = size
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        pixmap = self.cache.load(self.path)
        self.signals.finished.emit(self.path, pixmap)


class ThumbnailLoader:
    """Schedules thumbnail jobs on the global thread pool."""

    def __init__(self, cache: Optional[ThumbnailCache] = None) -> None:
        self.cache = cache or ThumbnailCache()
        self._pool = QThreadPool.globalInstance()
        self._in_flight: Dict[str, ThumbnailJob] = {}
        # Jobs whose results are no longer awaited. They are kept referenced
        # until they finish: dropping the Python wrapper of a running QRunnable
        # deletes its signals object mid-emit ("Signal source has been deleted").
        self._stranded: List[ThumbnailJob] = []
        self._deferred: List[_JobSignals] = []

    def request(self, path: str, size: Optional[int] = None) -> _JobSignals:
        """Queue ``path`` for decoding and return the signals object to connect.

        Each job owns its signals object, so callers always get back the exact
        object the job will emit on. A cache hit defers the emit to the next
        event-loop tick because callers connect to ``finished`` only once this
        method returns.
        """
        pixmap = self.cache.get(path)
        if pixmap is not None:
            signals = _JobSignals()
            self._deferred.append(signals)
            QTimer.singleShot(0, lambda: self._emit_deferred(signals, path, pixmap))
            return signals

        job = self._in_flight.get(path)
        if job is None:
            signals = _JobSignals()
            job = ThumbnailJob(self.cache, path, size or self.cache.size, signals)
            job.signals.finished.connect(lambda _p, _pix, job=job: self._drop_job(job))
            self._in_flight[path] = job
            self._pool.start(job)
        return job.signals

    def _drop_job(self, job: "ThumbnailJob") -> None:
        self._in_flight.pop(job.path, None)
        self._stranded = [other for other in self._stranded if other is not job]

    def _emit_deferred(self, signals: "_JobSignals", path: str, pixmap) -> None:
        try:
            signals.finished.emit(path, pixmap)
        finally:
            try:
                self._deferred.remove(signals)
            except ValueError:
                pass

    def clear_pending(self) -> None:
        """Forget which results are awaited without destroying running jobs."""
        self._stranded.extend(self._in_flight.values())
        self._in_flight.clear()


def pixmap_size(pixmap: QPixmap) -> Tuple[int, int]:
    return (pixmap.width(), pixmap.height())
