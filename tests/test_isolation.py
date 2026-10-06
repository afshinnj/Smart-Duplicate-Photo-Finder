"""Tests for user-data isolation and image format capability discovery."""

from __future__ import annotations

import os
import unittest

from src.core import constants
from src.core.image_formats import (
    decodable_extensions,
    heif_available,
    unsupported_extensions,
)
from src.scanner.image_detector import ImageDetector

from .helpers import isolate_app_data, isolated_app_data, remove_tree, temp_dir


class TestLegacyDataMigration(unittest.TestCase):
    """The rename to DupliPix must adopt the user's existing data, not orphan it."""

    def _layout(self, base: str) -> str:
        """Create a fake pre-rename data folder under ``base`` and return it."""
        legacy = os.path.join(base, constants._LEGACY_DIR_NAME)
        os.makedirs(os.path.join(legacy, "quarantine"), exist_ok=True)
        with open(os.path.join(legacy, "config.json"), "w", encoding="utf-8") as handle:
            handle.write('{"general": {"language": "fa"}}')
        with open(os.path.join(legacy, "database.sqlite"), "w", encoding="utf-8") as handle:
            handle.write("sqlite")
        with open(os.path.join(legacy, "quarantine", "photo.jpg"), "w", encoding="utf-8") as handle:
            handle.write("image")
        return legacy

    def _run_migration(self, base: str) -> str:
        """Point APPDATA at ``base``, run the migration, return the data dir."""
        os.environ["APPDATA"] = base
        import importlib

        importlib.reload(constants)
        constants.migrate_legacy_data_dir()
        return os.path.join(base, constants.APP_DIR_NAME)

    def setUp(self) -> None:
        # A scratch folder that doubles as a fake %APPDATA%; the migration
        # looks at APPDATA, so point it there and restore it afterwards.
        self._appdata = temp_dir()
        os.environ["APPDATA"] = self._appdata
        self.addCleanup(self._restore_appdata)
        self.addCleanup(remove_tree, self._appdata)

    def _restore_appdata(self) -> None:
        if "APPDATA" in os.environ:
            del os.environ["APPDATA"]
        import importlib

        importlib.reload(constants)

    def test_moves_legacy_data_into_the_renamed_folder(self) -> None:
        base = self._appdata
        self._layout(base)
        target = os.path.join(base, constants.APP_DIR_NAME)
        if os.path.isdir(target):
            os.rmdir(target)  # start from a genuinely fresh folder

        new_dir = self._run_migration(base)

        self.assertEqual(new_dir, target)
        self.assertTrue(os.path.exists(os.path.join(new_dir, "config.json")))
        self.assertTrue(os.path.exists(os.path.join(new_dir, "database.sqlite")))
        self.assertTrue(os.path.exists(os.path.join(new_dir, "quarantine", "photo.jpg")))
        self.assertFalse(os.path.isdir(os.path.join(base, constants._LEGACY_DIR_NAME)))

    def test_never_overwrites_existing_user_data(self) -> None:
        base = self._appdata
        os.makedirs(os.path.join(base, constants.APP_DIR_NAME), exist_ok=True)
        self._layout(base)
        target = os.path.join(base, constants.APP_DIR_NAME)
        with open(os.path.join(target, "config.json"), "w", encoding="utf-8") as handle:
            handle.write('{"general": {"language": "en"}}')

        self._run_migration(base)

        with open(os.path.join(target, "config.json"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), '{"general": {"language": "en"}}')
        # The legacy folder is left exactly as it was.
        self.assertTrue(os.path.isdir(os.path.join(base, constants._LEGACY_DIR_NAME)))

    def test_skipped_when_data_dir_is_overridden(self) -> None:
        """Test/offscreen runs must never touch real user data."""
        with isolated_app_data():
            self._layout(self._appdata)
            constants.migrate_legacy_data_dir()
            # The legacy folder is untouched because SDPF_DATA_DIR is set.
            self.assertTrue(os.path.isdir(os.path.join(self._appdata, constants._LEGACY_DIR_NAME)))
            self.assertFalse(os.path.isdir(os.path.join(self._appdata, constants.APP_DIR_NAME)))


class TestAppDataIsolation(unittest.TestCase):
    """The SDPF_DATA_DIR override redirects every user-data path."""

    def setUp(self) -> None:
        self.addCleanup(isolate_app_data())

    def test_override_redirects_all_paths(self) -> None:
        base = constants.app_data_dir()
        for path in (
            constants.config_path(),
            constants.database_path(),
            constants.quarantine_dir(),
            constants.thumbnails_dir(),
            constants.logs_dir(),
        ):
            # Some paths live in subdirectories of the app-data folder.
            self.assertTrue(os.path.commonpath([base, path]) == base)
            self.assertNotIn("AppData", path)

    def test_override_creates_the_directory(self) -> None:
        self.assertTrue(os.path.isdir(constants.app_data_dir()))


class TestImageFormats(unittest.TestCase):
    def test_common_formats_are_decodable(self) -> None:
        accepted = decodable_extensions({".jpg", ".png", ".webp", ".bmp"})
        self.assertEqual(accepted, {".jpg", ".png", ".webp", ".bmp"})

    def test_heif_round_trips_the_capability_flag(self) -> None:
        requested = {".heic", ".heif"}
        if heif_available():
            self.assertTrue(decodable_extensions(requested))
            self.assertFalse(unsupported_extensions(requested))
        else:
            self.assertFalse(decodable_extensions(requested))
            self.assertEqual(unsupported_extensions(requested), requested)

    def test_detector_drops_undecodable_extensions(self) -> None:
        detector = ImageDetector(extensions=[".jpg", ".heic", ".png"])
        # .jpg/.png always decode; .heic only when pillow-heif is installed.
        self.assertIn(".jpg", detector.extensions)
        self.assertIn(".png", detector.extensions)
        self.assertEqual(".heic" in detector.extensions, heif_available())


if __name__ == "__main__":
    unittest.main()
