"""SQLite connection management and schema migration."""

from __future__ import annotations

import os
import sqlite3
import threading
from typing import Optional

from ..core import constants
from ..core.exceptions import DatabaseError
from ..core.logger import get_logger

_log = get_logger("database")

_SCHEMA_VERSION = 1
_MIGRATIONS = ("001_initial.sql",)


class Database:
    """Thread-safe wrapper around a single SQLite connection.

    SQLite connections are not shareable across threads by default, so a lock
    guards every statement and ``check_same_thread`` is disabled to let the
    worker threads report progress.
    """

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or constants.database_path()
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._lock = threading.RLock()
        try:
            self._connection = sqlite3.connect(
                self.path, check_same_thread=False, timeout=30.0
            )
        except sqlite3.Error as exc:
            raise DatabaseError(f"Cannot open database at {self.path}") from exc

        self._connection.row_factory = sqlite3.Row
        self._apply_pragmas()
        self.migrate()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _apply_pragmas(self) -> None:
        with self._lock:
            try:
                self._connection.execute("PRAGMA journal_mode = WAL")
                self._connection.execute("PRAGMA synchronous = NORMAL")
                self._connection.execute("PRAGMA foreign_keys = ON")
                self._connection.execute("PRAGMA temp_store = MEMORY")
                self._connection.execute("PRAGMA cache_size = -65536")  # ~64 MiB
            except sqlite3.Error as exc:
                _log.warning("Could not apply all PRAGMAs: %s", exc)

    def migrate(self) -> None:
        """Run every pending migration script."""
        with self._lock:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_meta "
                "(key TEXT PRIMARY KEY, value INTEGER NOT NULL)"
            )
            try:
                current = self._connection.execute(
                    "SELECT value FROM schema_meta WHERE key = 'version'"
                ).fetchone()
                current_version = current[0] if current else 0
            except sqlite3.Error:
                current_version = 0

            if current_version >= _SCHEMA_VERSION:
                return

            base_dir = os.path.join(os.path.dirname(__file__), "migrations")
            try:
                for index, filename in enumerate(_MIGRATIONS, start=1):
                    if index <= current_version:
                        continue
                    with open(os.path.join(base_dir, filename), "r", encoding="utf-8") as handle:
                        script = handle.read()
                    self._connection.executescript(script)
                    _log.info("Applied database migration %s", filename)

                self._connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES('version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (_SCHEMA_VERSION,),
                )
                self._connection.commit()
            except (sqlite3.Error, OSError) as exc:
                raise DatabaseError("Database migration failed") from exc

    # ------------------------------------------------------------------
    # Execution helpers
    # ------------------------------------------------------------------

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            try:
                return self._connection.execute(sql, params)
            except sqlite3.Error as exc:
                _log.error("SQL error: %s | query: %s", exc, sql)
                raise DatabaseError(str(exc)) from exc

    def executemany(self, sql: str, params) -> None:
        with self._lock:
            try:
                self._connection.executemany(sql, params)
            except sqlite3.Error as exc:
                _log.error("SQL error: %s | query: %s", exc, sql)
                raise DatabaseError(str(exc)) from exc

    def commit(self) -> None:
        with self._lock:
            try:
                self._connection.commit()
            except sqlite3.Error as exc:
                raise DatabaseError(str(exc)) from exc

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            try:
                return self._connection.execute(sql, params).fetchall()
            except sqlite3.Error as exc:
                _log.error("SQL error: %s | query: %s", exc, sql)
                raise DatabaseError(str(exc)) from exc

    def query_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        with self._lock:
            try:
                return self._connection.execute(sql, params).fetchone()
            except sqlite3.Error as exc:
                _log.error("SQL error: %s | query: %s", exc, sql)
                raise DatabaseError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def vacuum(self) -> None:
        with self._lock:
            try:
                self._connection.execute("VACUUM")
            except sqlite3.Error as exc:
                _log.warning("VACUUM failed: %s", exc)

    def close(self) -> None:
        with self._lock:
            try:
                self._connection.close()
            except sqlite3.Error:
                pass
