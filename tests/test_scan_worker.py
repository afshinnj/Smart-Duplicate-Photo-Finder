"""Wiring test: a real scan through the Qt worker, rendered in the results page.

Unlike the service tests this exercises the whole stack the user hits: the
ScanWorker thread, its Qt signals, the results page rendering and the
asynchronous thumbnail loader.
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from src.core.config import AppConfig  # noqa: E402
from src.database.database import Database  # noqa: E402
from src.ui.app_context import AppContext  # noqa: E402
from src.ui.main_window import MainWindow  # noqa: E402
from src.ui.pages.results_page import ResultsPage  # noqa: E402
from src.workers.scan_worker import ScanWorker  # noqa: E402

from .helpers import duplicate_set, remove_tree, temp_dir  # noqa: E402

_APPLICATION = None


def application() -> QApplication:
    global _APPLICATION
    if _APPLICATION is None:
        _APPLICATION = QApplication.instance() or QApplication([])
    return _APPLICATION


def _process_events(timeout_ms: int = 5000) -> None:
    import time

    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        application().processEvents()


class TestScanWorkerWiring(unittest.TestCase):
    def setUp(self) -> None:
        application()
        self.root = temp_dir()
        self.layout = duplicate_set(self.root)

    def tearDown(self) -> None:
        remove_tree(self.root)

    def _run(self, worker: ScanWorker) -> None:
        ticks = []
        worker.progress.connect(lambda update: ticks.append(update))
        worker.start()
        import time

        start = time.time()
        while worker.isRunning() and time.time() - start < 30.0:
            application().processEvents()
        # The worker thread has exited, but its queued signals are delivered on
        # the UI thread - pump once more so finished_scan handlers actually run.
        for _ in range(10):
            application().processEvents()
        self.assertFalse(worker.isRunning(), "scan worker did not finish in time")
        self.assertTrue(ticks, "no progress signals were emitted")

    def test_worker_drives_full_pipeline(self) -> None:
        database = Database(path=os.path.join(self.root, "worker.sqlite"))
        try:
            config = AppConfig()
            config.similarity.similar_threshold = 70.0
            worker = ScanWorker(
                database=database,
                config=config,
                folders=[self.layout["folder"]],
            )
            results = []
            worker.finished_scan.connect(results.append)
            self._run(worker)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].image_count, 4)
            self.assertTrue(any(group.is_exact for group in results[0].groups))

            sessions = database.query("SELECT * FROM scan_sessions")
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0]["status"], "completed")
        finally:
            database.close()

    def test_results_page_renders_scan_output(self) -> None:
        database = Database(path=os.path.join(self.root, "worker.sqlite"))
        try:
            config = AppConfig()
            config.similarity.similar_threshold = 70.0
            worker = ScanWorker(
                database=database,
                config=config,
                folders=[self.layout["folder"]],
            )
            results = []
            worker.finished_scan.connect(results.append)
            self._run(worker)
            self.assertTrue(results, "finished_scan was never emitted")

            page = ResultsPage(AppContext(database=database, config=config))
            page.set_groups(results[0].groups, results[0].session.id)
            self.assertTrue(page._cards)

            exact = next(card.group for card in page._cards if card.group.is_exact)
            self.assertEqual(len(exact.items), 2)
            self.assertEqual(exact.keeper.filename, "IMG_0001.jpg")

            # Give the thumbnail thread pool a chance to deliver the pixmaps.
            _process_events(3000)
            tile = page._cards[0]._tiles[0]
            self.assertFalse(tile.thumbnail.pixmap() is None)
        finally:
            database.close()


class TestMainWindowScanFlow(unittest.TestCase):
    """The window wires scan completion straight into the results page."""

    def setUp(self) -> None:
        application()
        self.root = temp_dir()
        self.layout = duplicate_set(self.root)
        # An isolated database: the shared user database accumulates images
        # across runs and would make the similarity stage far outlast the
        # timeout below.
        self.database = Database(path=os.path.join(self.root, "window.sqlite"))

    def tearDown(self) -> None:
        self.database.close()
        remove_tree(self.root)

    def test_scan_finished_switches_to_results(self) -> None:
        context = AppContext(database=self.database)
        context.config.similarity.similar_threshold = 70.0
        window = MainWindow(context)
        window.show()
        scan_page = window._pages["scan"]
        scan_page._folder_list.addItem(self.layout["folder"])
        scan_page._combo_targets.setCurrentIndex(2)  # folders
        scan_page.start_scan()

        import time

        start = time.time()
        while scan_page.is_scanning() and time.time() - start < 30.0:
            application().processEvents()
        for _ in range(10):
            application().processEvents()

        self.assertFalse(scan_page.is_scanning())
        self.assertEqual(window._stack.currentWidget(), window._pages["results"])
        self.assertTrue(window._pages["results"]._cards)
        window.close()


if __name__ == "__main__":
    unittest.main()
