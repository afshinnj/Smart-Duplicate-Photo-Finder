"""Tests for quarantine-based cleanup and undo."""

from __future__ import annotations

import os
import unittest

from src.core.config import AppConfig, CleanupSettings
from src.core.constants import CleanupMethod
from src.core.exceptions import CleanupError
from src.database.database import Database
from src.services.cleanup_service import CleanupService, is_protected_path

from .helpers import duplicate_set, remove_tree, temp_dir


class TestProtectedPaths(unittest.TestCase):
    def test_system_locations_are_refused(self) -> None:
        self.assertTrue(is_protected_path(r"C:\Windows\System32\foo.png"))
        self.assertTrue(is_protected_path(r"C:\Program Files\app\bar.png"))
        self.assertTrue(is_protected_path("C:\\Windows\\explorer.exe"))

    def test_user_files_are_allowed(self) -> None:
        self.assertFalse(is_protected_path(r"C:\Users\me\Pictures\IMG_001.jpg"))


class TestCleanupService(unittest.TestCase):
    def setUp(self) -> None:
        self.root = temp_dir()
        self.layout = duplicate_set(self.root)
        self.database = Database(path=self.root + "/cleanup.sqlite")
        self.settings = CleanupSettings(method=CleanupMethod.QUARANTINE)
        self.service = CleanupService(self.database, self.settings)

    def tearDown(self) -> None:
        self.database.close()
        remove_tree(self.root)

    def _record(self, path: str, image_id: int = 1, size: int | None = None) -> ImageRecord:
        from src.models.image_model import ImageRecord

        if size is None:
            size = os.path.getsize(path) if os.path.exists(path) else 0
        return ImageRecord(id=image_id, path=path, filename=os.path.basename(path), size=size)

    def test_quarantine_moves_file_and_keeps_it_recoverable(self) -> None:
        record = self._record(self.layout["copy"])
        result = self.service.remove([record])
        self.assertEqual(result.removed_count, 1)
        self.assertFalse(os.path.exists(record.path))
        self.assertEqual(self.service.pending_undo_count(), 1)
        self.assertGreater(self.service.pending_undo_size(), 0)

    def test_undo_restores_file(self) -> None:
        record = self._record(self.layout["copy"])
        self.service.remove([record])
        restored = self.service.undo()
        self.assertEqual(restored, 1)
        self.assertTrue(os.path.exists(record.path))
        self.assertEqual(self.service.pending_undo_count(), 0)

    def test_confirm_callback_blocks_removal(self) -> None:
        record = self._record(self.layout["copy"])
        with self.assertRaises(CleanupError):
            self.service.remove([record], confirm=lambda records, size, method: False)
        self.assertTrue(os.path.exists(record.path))

    def test_missing_file_is_reported_as_failed(self) -> None:
        record = self._record(os.path.join(self.root, "gone.jpg"), size=100)
        result = self.service.remove([record])
        self.assertEqual(result.removed_count, 0)
        self.assertEqual(result.failed_count, 1)

    def test_permanent_delete_removes_file(self) -> None:
        record = self._record(self.layout["copy"])
        self.service.remove([record], method=CleanupMethod.PERMANENT)
        self.assertFalse(os.path.exists(record.path))
        # Undo bookkeeping still exists but there is nothing to restore.
        self.assertEqual(self.service.undo(), 0)


if __name__ == "__main__":
    unittest.main()
