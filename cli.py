"""Headless command-line interface.

Runs the same scan pipeline as the GUI without any Qt dependency, which is
useful for servers, scheduled clean-ups and shell scripting::

    python cli.py scan D:/Photos D:/Camera
    python cli.py scan D:/Photos --json > report.json

The scan is read-only: nothing is ever deleted from here. Open the GUI to act
on the results, or use ``--list-history`` to revisit a previous session.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

from src.core import constants
from src.core.config import AppConfig
from src.core.logger import get_logger, setup_logging
from src.database.database import Database
from src.services.progress import ProgressUpdate
from src.services.scan_service import ScanController, ScanResult, ScanService

_log = get_logger("cli")


def _human_size(value: float) -> str:
    """Render a byte count the way the GUI's dashboard does."""
    value = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024.0 or unit == "TB":
            return f"{value:,.1f} {unit}" if unit != "B" else f"{int(value):,} B"
        value /= 1024.0
    return f"{value:,.1f} TB"


def _progress_printer(update: ProgressUpdate) -> None:
    """Print a compact, self-updating single-line progress report."""
    bar_width = 24
    filled = int(bar_width * max(0.0, min(100.0, update.overall_progress)) / 100.0)
    bar = "#" * filled + "-" * (bar_width - filled)
    line = (
        f"\r[{bar}] {update.overall_progress:5.1f}%  "
        f"{update.stage.value:<12} "
        f"{update.files_scanned:,} files / {update.images_found:,} images"
    )
    if update.eta_label.strip() and update.eta_label != "--":
        line += f"  eta {update.eta_label}"
    sys.stderr.write(line)
    sys.stderr.flush()


def _group_to_dict(group, session_id: Optional[int]) -> dict:
    return {
        "session_id": session_id,
        "type": "exact" if group.is_exact else "similar",
        "similarity": round(float(group.similarity_score), 1),
        "keeper": group.keeper.path,
        "duplicates": [item.path for item in group.duplicates],
        "wasted_bytes": group.wasted_bytes,
    }


def _print_report(result: ScanResult, as_json: bool) -> None:
    groups = sorted(result.groups, key=lambda group: group.wasted_bytes, reverse=True)
    if as_json:
        payload = {
            "session_id": result.session.id,
            "status": result.session.status.value,
            "images": result.image_count,
            "duplicates": result.duplicate_count,
            "recoverable_bytes": result.recoverable_bytes,
            "skipped_files": result.skipped_files,
            "errors": result.errors,
            "groups": [_group_to_dict(group, result.session.id) for group in groups],
        }
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return

    print()
    print("=" * 72)
    print(f"  Images scanned : {result.image_count:,}")
    print(f"  Duplicates     : {result.duplicate_count:,}")
    print(f"  Recoverable    : {_human_size(result.recoverable_bytes)}")
    if result.skipped_files:
        print(f"  Skipped files  : {result.skipped_files:,}")
    print("=" * 72)
    for index, group in enumerate(groups, start=1):
        tag = "EXACT " if group.is_exact else "SIMILAR"
        print(f"\n#{index} [{tag}] score {group.similarity_score:.0f}  "
              f"({_human_size(group.wasted_bytes)} recoverable)")
        print(f"  KEEP   {group.keeper.path}")
        for item in group.duplicates:
            print(f"  DEL?   {item.path}")
    if not groups:
        print("\nNo duplicates found.")


def cmd_scan(args: argparse.Namespace) -> int:
    config = AppConfig.load()
    if args.threshold is not None:
        config.similarity.similar_threshold = args.threshold
    if args.min_size_mb is not None:
        config.scan.min_file_size_mb = args.min_size_mb

    database = Database()
    try:
        service = ScanService(database, config)
        controller = ScanController()
        progress = None if args.quiet else _progress_printer
        try:
            result = service.scan_folders(args.folders, progress=progress, controller=controller)
        except KeyboardInterrupt:
            controller.cancel()
            print("\nScan cancelled by user.")
            return 130
        finally:
            if not args.quiet:
                sys.stderr.write("\n")
                sys.stderr.flush()
        _print_report(result, args.json)
        if result.errors:
            print(f"\n{len(result.errors)} error(s) were logged during the scan.",
                  file=sys.stderr)
        return 0
    finally:
        database.close()


def cmd_history(args: argparse.Namespace) -> int:
    from src.services.history_service import HistoryService

    database = Database()
    try:
        history = HistoryService(database)
        sessions = history.list_sessions(limit=args.limit)
        if not sessions:
            print("No previous scans recorded.")
            return 0
        print(f"{'ID':>5}  {'Status':<10} {'Images':>7} {'Dupes':>6}  Started")
        print("-" * 60)
        for session in sessions:
            started = session.start_time.strftime("%Y-%m-%d %H:%M") if session.start_time else "-"
            print(f"{session.id:>5}  {session.status.value:<10} "
                  f"{session.images_found:>7} "
                  f"{session.duplicates_found:>6}  {started}")
        return 0
    finally:
        database.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description=f"{constants.APP_NAME} - headless duplicate photo scan.",
    )
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {constants.APP_VERSION}")

    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan folders and report duplicates (read-only).")
    scan.add_argument("folders", nargs="+", help="One or more folders to scan.")
    scan.add_argument("--json", action="store_true",
                      help="Emit a machine-readable JSON report on stdout.")
    scan.add_argument("--threshold", type=float, default=None,
                      help="Similarity threshold (0-100); lower finds more near-matches.")
    scan.add_argument("--min-size-mb", type=float, default=None,
                      help="Ignore images smaller than this many megabytes.")
    scan.add_argument("--quiet", action="store_true", help="Suppress progress output.")
    scan.set_defaults(func=cmd_scan)

    history = sub.add_parser("history", help="List previously recorded scan sessions.")
    history.add_argument("--limit", type=int, default=20, help="Maximum sessions to show.")
    history.set_defaults(func=cmd_history)

    return parser


def main(argv: Optional[list] = None) -> int:
    setup_logging()
    # Adopt the previous product name's data before the database is opened.
    constants.migrate_legacy_data_dir()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        _log.exception("CLI failed")
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
