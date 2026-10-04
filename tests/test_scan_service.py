"""End-to-end scan pipeline test against a folder with known duplicates."""

from __future__ import annotations

import unittest

from src.core.config import AppConfig
from src.core.constants import ScanStatus
from src.database.database import Database
from src.services.progress import ProgressUpdate, ScanStage, format_duration, format_size
from src.services.scan_service import ScanController, ScanService

from .helpers import duplicate_set, remove_tree, temp_dir


class TestProgressHelpers(unittest.TestCase):
    def test_format_size(self) -> None:
        self.assertEqual(format_size(0), "0 B")
        self.assertEqual(format_size(1023), "1023 B")
        self.assertEqual(format_size(1536), "1.5 KB")
        self.assertEqual(format_size(1024 * 1024 * 5), "5.0 MB")

    def test_format_duration(self) -> None:
        self.assertEqual(format_duration(0), "--")
        self.assertEqual(format_duration(45), "45s")
        self.assertEqual(format_duration(125), "2m 05s")
        self.assertEqual(format_duration(3725), "1h 02m")

    def test_progress_update_defaults(self) -> None:
        update = ProgressUpdate(stage=ScanStage.IDLE)
        self.assertEqual(update.files_scanned, 0)
        self.assertEqual(update.eta_label, "--")


class TestScanPipeline(unittest.TestCase):
    """Runs the full pipeline on a small synthetic photo collection."""

    def setUp(self) -> None:
        self.root = temp_dir()
        self.layout = duplicate_set(self.root)
        self.database = Database(path=self.root + "/test.sqlite")
        config = AppConfig()
        config.similarity.similar_threshold = 70.0
        self.service = ScanService(self.database, config)

    def tearDown(self) -> None:
        self.database.close()
        remove_tree(self.root)

    def test_scan_finds_exact_duplicate(self) -> None:
        updates = []
        result = self.service.scan_folders(
            [self.layout["folder"]],
            progress=updates.append,
            controller=ScanController(),
        )
        self.assertEqual(result.status, ScanStatus.COMPLETED)
        self.assertEqual(result.image_count, 4)
        self.assertTrue(any(update.stage.value == "done" for update in updates))

        exact = [group for group in result.groups if group.is_exact]
        self.assertEqual(len(exact), 1)
        self.assertEqual(len(exact[0].items), 2)
        self.assertGreater(exact[0].wasted_bytes, 0)

    def test_scan_persists_session(self) -> None:
        result = self.service.scan_folders([self.layout["folder"]])
        self.assertIsNotNone(result.session.id)
        sessions = self.database.query("SELECT * FROM scan_sessions")
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["status"], "completed")

    def test_scan_recommends_original_over_copy(self) -> None:
        result = self.service.scan_folders([self.layout["folder"]])
        exact = next(group for group in result.groups if group.is_exact)
        keeper = exact.keeper
        self.assertEqual(keeper.filename, "IMG_0001.jpg")
        self.assertNotIn("copy", keeper.filename.lower())

    def test_groups_reloaded_from_database(self) -> None:
        from src.database.repositories.image_repository import ImageRepository
        from src.database.repositories.scan_repository import GroupRepository

        result = self.service.scan_folders([self.layout["folder"]])
        image_repo = ImageRepository(self.database)
        reloaded = GroupRepository(self.database).load_groups(result.session.id, image_repo)
        self.assertEqual(len(reloaded), len(result.groups))
        for original, stored in zip(result.groups, reloaded):
            self.assertEqual({item.id for item in original.items}, {item.id for item in stored.items})


if __name__ == "__main__":
    unittest.main()
