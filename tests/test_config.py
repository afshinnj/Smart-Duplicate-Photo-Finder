"""Tests for configuration (de)serialisation and defaults."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from src.core.config import AIEngineType, AppConfig, Language, Theme


class TestConfig(unittest.TestCase):
    def test_defaults(self) -> None:
        config = AppConfig()
        self.assertEqual(config.general.language, Language.PERSIAN)
        self.assertEqual(config.general.theme, Theme.DARK)
        self.assertEqual(config.similarity.duplicate_threshold, 98.0)
        self.assertEqual(config.cleanup.method.value, "quarantine")
        self.assertEqual(config.ai.engine, AIEngineType.DISABLED)

    def test_roundtrip(self) -> None:
        config = AppConfig()
        config.general.language = Language.ENGLISH
        config.general.theme = Theme.LIGHT
        config.similarity.similar_threshold = 77.5
        config.scan.include_hidden_files = True
        config.last_scan_folders = ["C:/a", "C:/b"]

        path = os.path.join(tempfile.mkdtemp(), "config.json")
        config.save(path)

        loaded = AppConfig.load(path)
        self.assertEqual(loaded.general.language, Language.ENGLISH)
        self.assertEqual(loaded.general.theme, Theme.LIGHT)
        self.assertEqual(loaded.similarity.similar_threshold, 77.5)
        self.assertTrue(loaded.scan.include_hidden_files)
        self.assertEqual(loaded.last_scan_folders, ["C:/a", "C:/b"])

    def test_missing_file_uses_defaults(self) -> None:
        config = AppConfig.load(os.path.join(tempfile.mkdtemp(), "nope.json"))
        self.assertEqual(config, AppConfig())

    def test_invalid_enum_value_is_ignored(self) -> None:
        config = AppConfig.from_dict({"general": {"language": "klingon"}})
        self.assertEqual(config.general.language, Language.PERSIAN)

    def test_enums_serialise_to_plain_json(self) -> None:
        config = AppConfig()
        data = json.loads(json.dumps(config.to_dict()))
        self.assertEqual(data["general"]["language"], "fa")
        self.assertEqual(data["general"]["theme"], "dark")


if __name__ == "__main__":
    unittest.main()
