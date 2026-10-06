"""Headless CLI smoke tests.

The CLI shares the GUI's pipeline, so these only verify the command surface:
argument parsing, JSON/text output shape and the history listing. Pipeline
correctness is covered by the service tests.
"""

from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stdout, redirect_stderr

from cli import build_parser, main

from .helpers import duplicate_set, isolate_app_data, remove_tree, temp_dir


class TestCliScan(unittest.TestCase):
    def setUp(self) -> None:
        # The CLI talks to the user's real database/config by design; point it
        # at a throwaway directory so these runs never touch real data.
        self.addCleanup(isolate_app_data())
        self.root = temp_dir()
        self.layout = duplicate_set(self.root)

    def tearDown(self) -> None:
        remove_tree(self.root)

    def test_requires_a_subcommand(self) -> None:
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            main(["--help"])

    def test_scan_reports_exact_duplicate_as_json(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            code = main(["scan", "--quiet", "--json", self.layout["folder"]])

        self.assertEqual(code, 0)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["images"], 4)
        self.assertTrue(report["groups"])
        exact = next(group for group in report["groups"] if group["type"] == "exact")
        self.assertEqual(len(exact["duplicates"]), 1)
        self.assertTrue(os.path.exists(exact["keeper"]))

    def test_scan_text_report_names_keeper_and_duplicate(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            code = main(["scan", "--quiet", self.layout["folder"]])

        self.assertEqual(code, 0)
        text = stdout.getvalue()
        self.assertIn("KEEP", text)
        self.assertIn("IMG_0001.jpg", text)
        self.assertIn("IMG_0001_copy.jpg", text)

    def test_scan_records_session_in_history(self) -> None:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            main(["scan", "--quiet", self.layout["folder"]])

        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            code = main(["history"])

        self.assertEqual(code, 0)
        self.assertIn("completed", stdout.getvalue())


class TestCliParser(unittest.TestCase):
    def setUp(self) -> None:
        # Pure argument parsing, but keep it off the user's data regardless.
        self.addCleanup(isolate_app_data())

    def test_scan_accepts_threshold_and_min_size(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["scan", "D:/Photos", "--threshold", "60", "--min-size-mb", "1", "--json"]
        )
        self.assertEqual(args.command, "scan")
        self.assertEqual(args.folders, ["D:/Photos"])
        self.assertEqual(args.threshold, 60.0)
        self.assertEqual(args.min_size_mb, 1.0)
        self.assertTrue(args.json)

    def test_history_defaults(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["history"])
        self.assertEqual(args.command, "history")
        self.assertEqual(args.limit, 20)


if __name__ == "__main__":
    unittest.main()
