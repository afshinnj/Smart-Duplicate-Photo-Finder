"""Offscreen smoke tests for the Qt layer.

These run with ``QT_QPA_PLATFORM=offscreen`` so they need no display. They only
verify that the widgets construct and connect - pipeline behaviour is covered by
the service tests.
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QElapsedTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.core.constants import DuplicateType  # noqa: E402
from src.models.duplicate_group import DuplicateGroup  # noqa: E402
from src.models.image_model import ImageRecord  # noqa: E402
from src.ui.app_context import AppContext  # noqa: E402
from src.ui.main_window import MainWindow  # noqa: E402
from src.ui.pages.results_page import ResultsPage  # noqa: E402
from src.ui.widgets.group_card import GroupCard  # noqa: E402

from .helpers import duplicate_set, remove_tree, temp_dir  # noqa: E402

_APPLICATION = None


def application() -> QApplication:
    global _APPLICATION
    if _APPLICATION is None:
        _APPLICATION = QApplication.instance() or QApplication([])
    return _APPLICATION


def _group() -> DuplicateGroup:
    records = [
        ImageRecord(id=1, path="photos/IMG_0001.jpg", filename="IMG_0001.jpg", size=5000, width=200, height=200),
        ImageRecord(id=2, path="photos/IMG_0001_copy.jpg", filename="IMG_0001_copy.jpg", size=5000, width=200, height=200),
    ]
    return DuplicateGroup(id=1, scan_id=1, group_type=DuplicateType.EXACT, similarity_score=100.0, items=records, keep_id=1)


def _group_from_files(paths) -> DuplicateGroup:
    """Build an EXACT group of real files on disk (needed for thumbnail I/O)."""
    import os

    records = []
    for index, path in enumerate(paths, start=1):
        stat = os.stat(path)
        records.append(
            ImageRecord(
                id=index,
                path=path,
                filename=os.path.basename(path),
                size=stat.st_size,
                width=200,
                height=200,
            )
        )
    return DuplicateGroup(
        id=1,
        scan_id=1,
        group_type=DuplicateType.EXACT,
        similarity_score=100.0,
        items=records,
        keep_id=records[0].id,
    )


class TestWidgets(unittest.TestCase):
    def setUp(self) -> None:
        application()

    def test_group_card_builds(self) -> None:
        card = GroupCard(_group(), 0)
        self.assertEqual(len(card._tiles), 2)
        self.assertEqual(card.selected_records(), [card._tiles[1].record])
        card.retranslate()

    def test_results_page_empty(self) -> None:
        page = ResultsPage(AppContext())
        page.set_groups([])
        self.assertFalse(page._cards)
        page.retranslate()

    def test_group_card_requests_thumbnails_after_wiring(self) -> None:
        """The card must only emit thumbnail_requested once connected (regression).

        It used to fire from the constructor, so the results page connected
        after the signal had already been emitted and no tile ever received a
        pixmap.
        """
        root = temp_dir()
        try:
            fixtures = duplicate_set(root)
            group = _group_from_files([fixtures["original"], fixtures["copy"]])
            requested = []
            card = GroupCard(group, 0)
            card.thumbnail_requested.connect(lambda path, tile: requested.append(path))
            card.request_thumbnails()
            self.assertEqual(len(requested), 2)
        finally:
            remove_tree(root)

    def test_results_page_loads_thumbnails(self) -> None:
        """Tiles of real duplicate images end up with a pixmap (regression)."""
        app = application()
        root = temp_dir()
        try:
            fixtures = duplicate_set(root)
            context = AppContext()
            page = ResultsPage(context)
            page.set_groups([_group_from_files([fixtures["original"], fixtures["copy"]])])

            tiles = [tile for card in page._cards for tile in card._tiles]
            self.assertEqual(len(tiles), 2)
            deadline = QElapsedTimer()
            deadline.start()
            while deadline.elapsed() < 5000 and any(
                tile.thumbnail.pixmap() is None or tile.thumbnail.pixmap().isNull() for tile in tiles
            ):
                app.processEvents()
            self.assertTrue(
                all(
                    tile.thumbnail.pixmap() is not None and not tile.thumbnail.pixmap().isNull()
                    for tile in tiles
                ),
                "thumbnails were never delivered to the result tiles",
            )
            context.close()
        finally:
            remove_tree(root)


class TestMainWindow(unittest.TestCase):
    def setUp(self) -> None:
        application()

    def test_window_navigates_every_page(self) -> None:
        window = MainWindow(AppContext())
        window.show()
        for key in ("dashboard", "scan", "results", "history", "settings"):
            window.show_page(key)
            self.assertEqual(window._stack.currentWidget(), window._pages[key])
        window.close()


if __name__ == "__main__":
    unittest.main()
