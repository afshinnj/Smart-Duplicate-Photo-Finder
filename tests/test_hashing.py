"""Tests for hashing engines and the duplicate grouping service."""

from __future__ import annotations

import os
import unittest

from src.core.config import AppConfig
from src.core.constants import DuplicateType
from src.hashing.file_hash import FileHashEngine
from src.hashing.perceptual_hash import PerceptualHashEngine, similarity_percentage
from src.services.duplicate_service import DuplicateService, SmartKeeper

from .helpers import duplicate_set, make_image, remove_tree, temp_dir


class TestFileHash(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = FileHashEngine()
        self.root = temp_dir()

    def tearDown(self) -> None:
        remove_tree(self.root)

    def test_identical_files_share_digest(self) -> None:
        layout = duplicate_set(self.root)
        self.assertEqual(self.engine.hash_file(layout["original"]), self.engine.hash_file(layout["copy"]))

    def test_different_files_differ(self) -> None:
        layout = duplicate_set(self.root)
        self.assertNotEqual(self.engine.hash_file(layout["original"]), self.engine.hash_file(layout["other"]))

    def test_hex_length(self) -> None:
        path = make_image(self.root, "a.png", (10, 20, 30))
        self.assertEqual(len(self.engine.hash_file(path)), 64)


class TestPerceptualHash(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = PerceptualHashEngine()
        self.root = temp_dir()

    def tearDown(self) -> None:
        remove_tree(self.root)

    def test_resized_copy_scores_high(self) -> None:
        layout = duplicate_set(self.root)
        hashes = self.engine.compute_all(layout["original"])
        self.assertIn("phash", hashes)
        for other_path, expected in ((layout["copy"], 95.0), (layout["resized"], 80.0)):
            other = self.engine.compute_all(other_path)
            score = similarity_percentage(hashes["phash"], other["phash"])
            self.assertIsNotNone(score)
            self.assertGreaterEqual(score, expected)

    def test_unrelated_image_scores_low(self) -> None:
        layout = duplicate_set(self.root)
        first = self.engine.compute_all(layout["original"])
        second = self.engine.compute_all(layout["other"])
        score = similarity_percentage(first["phash"], second["phash"])
        self.assertIsNotNone(score)
        self.assertLess(score, 60.0)


class TestSmartKeeper(unittest.TestCase):
    def setUp(self) -> None:
        self.keeper = SmartKeeper(AppConfig())
        self.root = temp_dir()

    def tearDown(self) -> None:
        remove_tree(self.root)

    def test_prefers_higher_resolution(self) -> None:
        from src.models.image_model import ImageRecord

        layout = duplicate_set(self.root)
        small = ImageRecord(path=layout["resized"], filename="small.jpg", size=1024, width=100, height=100)
        big = ImageRecord(path=layout["original"], filename="IMG_0001.jpg", size=9000, width=200, height=200)
        self.assertEqual(self.keeper.recommend([small, big]), big)

    def test_penalises_copy_names(self) -> None:
        from src.models.image_model import ImageRecord

        layout = duplicate_set(self.root)
        copy_record = ImageRecord(path=layout["copy"], filename="IMG_0001_copy.jpg", size=9000, width=200, height=200)
        original = ImageRecord(path=layout["original"], filename="IMG_0001.jpg", size=9000, width=200, height=200)
        self.assertEqual(self.keeper.recommend([copy_record, original]), original)


class TestDuplicateService(unittest.TestCase):
    def setUp(self) -> None:
        self.service = DuplicateService(AppConfig())
        self.root = temp_dir()

    def tearDown(self) -> None:
        remove_tree(self.root)

    def _records(self):
        from src.models.image_model import ImageRecord

        layout = duplicate_set(self.root)
        from src.hashing.file_hash import FileHashEngine

        hash_engine = FileHashEngine()
        original = ImageRecord(id=1, path=layout["original"], filename="IMG_0001.jpg", size=9000, width=200, height=200, sha256=hash_engine.hash_file(layout["original"]))
        copy = ImageRecord(id=2, path=layout["copy"], filename="IMG_0001_copy.jpg", size=9000, width=200, height=200, sha256=hash_engine.hash_file(layout["copy"]))
        other = ImageRecord(id=3, path=layout["other"], filename="DCP_9999.jpg", size=8000, width=200, height=200, sha256=hash_engine.hash_file(layout["other"]))
        return original, copy, other

    def test_group_exact(self) -> None:
        original, copy, other = self._records()
        groups = self.service.group_exact([original, copy, other], scan_id=1)
        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertEqual(group.group_type, DuplicateType.EXACT)
        self.assertEqual(len(group.items), 2)
        self.assertEqual(group.keeper, original)
        self.assertEqual(group.wasted_bytes, copy.size)

    def test_group_similar_below_threshold(self) -> None:
        from src.models.image_model import ImageRecord
        from src.models.similarity_result import SimilarityResult

        original, copy, other = self._records()
        low = SimilarityResult(image_a_id=1, image_b_id=3, score=10.0)
        groups = self.service.group_similar([original, copy, other], [low], scan_id=1, threshold=80.0)
        self.assertEqual(groups, [])

    def test_group_similar_clusters(self) -> None:
        from src.models.similarity_result import SimilarityResult

        original, copy, other = self._records()
        results = [
            SimilarityResult(image_a_id=1, image_b_id=2, score=99.0),
            SimilarityResult(image_a_id=2, image_b_id=3, score=90.0),
        ]
        groups = self.service.group_similar([original, copy, other], results, scan_id=1, threshold=80.0)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].items), 3)


if __name__ == "__main__":
    unittest.main()
