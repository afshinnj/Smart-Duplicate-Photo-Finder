"""Tests for the translator and the similarity engine."""

from __future__ import annotations

import unittest

from src.core.constants import SimilarityRating, rate_similarity
from src.i18n import Translator, is_rtl, tr
from src.similarity.similarity_engine import SimilarityEngine
from src.models.image_model import ImageRecord


class TestTranslator(unittest.TestCase):
    def setUp(self) -> None:
        self.translator = Translator("fa")

    def test_known_key(self) -> None:
        self.assertEqual(self.translator.tr("nav_scan"), "اسکن")

    def test_missing_key_returns_key(self) -> None:
        self.assertEqual(self.translator.tr("no_such_key_xyz"), "no_such_key_xyz")

    def test_placeholder_interpolation(self) -> None:
        self.assertEqual(self.translator.tr("results_groups_count", count=5), "5 گروه")

    def test_switching_language_changes_text(self) -> None:
        self.assertTrue(self.translator.set_language("en"))
        self.assertEqual(self.translator.tr("nav_scan"), "Scan")
        self.assertTrue(self.translator.set_language("fa"))

    def test_rtl_detection(self) -> None:
        self.assertTrue(self.translator.is_rtl)
        self.translator.set_language("en")
        self.assertFalse(self.translator.is_rtl)
        self.translator.set_language("fa")

    def test_singleton_helpers(self) -> None:
        self.assertIsInstance(tr("nav_scan"), str)
        self.assertIsInstance(is_rtl(), bool)


class TestRatingBands(unittest.TestCase):
    def test_bands(self) -> None:
        self.assertEqual(rate_similarity(100.0), SimilarityRating.EXACT)
        self.assertEqual(rate_similarity(96.0), SimilarityRating.ALMOST_SAME)
        self.assertEqual(rate_similarity(88.0), SimilarityRating.VERY_SIMILAR)
        self.assertEqual(rate_similarity(75.0), SimilarityRating.SIMILAR)
        self.assertEqual(rate_similarity(55.0), SimilarityRating.POSSIBLY_RELATED)
        self.assertEqual(rate_similarity(10.0), SimilarityRating.DIFFERENT)


class TestSimilarityEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = SimilarityEngine()

    def _record(self, record_id: int, path: str) -> ImageRecord:
        return ImageRecord(id=record_id, path=path, filename=path.rsplit("/", 1)[-1], size=1000, width=64, height=64)

    def test_identical_files_score_high(self) -> None:
        from .helpers import duplicate_set, remove_tree, temp_dir

        root = temp_dir()
        try:
            layout = duplicate_set(root)
            a = self._record(1, layout["original"])
            b = self._record(2, layout["copy"])
            result = self.engine.compare(a, b)
            self.assertGreater(result.score, 90.0)
        finally:
            remove_tree(root)

    def test_exact_duplicate_detection(self) -> None:
        from .helpers import duplicate_set, remove_tree, temp_dir

        root = temp_dir()
        try:
            layout = duplicate_set(root)
            a = self._record(1, layout["original"])
            b = self._record(2, layout["copy"])
            a.sha256 = "abc"
            b.sha256 = "abc"
            self.assertTrue(SimilarityEngine.exact_duplicate(a, b))
        finally:
            remove_tree(root)


if __name__ == "__main__":
    unittest.main()
