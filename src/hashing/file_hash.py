"""Cryptographic file hashing (SHA-256)."""

from __future__ import annotations

import hashlib
import os
from typing import Optional

from ..core import constants
from ..core.exceptions import HashError
from ..core.logger import get_logger

_log = get_logger("hashing.file_hash")


class FileHashEngine:
    """Streams files through SHA-256 in fixed-size chunks.

    Chunked reads keep memory usage flat regardless of file size, which matters
    when terabytes of photos are being processed.
    """

    def __init__(self, chunk_size: int = constants.SHA256_CHUNK_SIZE) -> None:
        self.chunk_size = max(64 * 1024, chunk_size)

    def hash_file(self, path: str) -> Optional[str]:
        """Return the hex SHA-256 digest of ``path`` or ``None`` on failure."""
        try:
            digest = hashlib.sha256()
            with open(path, "rb") as handle:
                while True:
                    chunk = handle.read(self.chunk_size)
                    if not chunk:
                        break
                    digest.update(chunk)
            return digest.hexdigest()
        except PermissionError:
            _log.debug("Permission denied while hashing %s", path)
            return None
        except OSError as exc:
            _log.debug("Cannot hash %s: %s", path, exc)
            return None
        except Exception as exc:  # defensive: hashing must never crash a scan
            _log.debug("Unexpected hashing error for %s: %s", path, exc)
            return None

    def hash_files(self, paths: list[str]) -> dict[str, str]:
        """Hash many files, mapping each path to its digest."""
        results: dict[str, str] = {}
        for path in paths:
            digest = self.hash_file(path)
            if digest is not None:
                results[path] = digest
        return results

    def verify(self, path: str, expected_digest: str) -> bool:
        actual = self.hash_file(path)
        return actual is not None and actual.lower() == expected_digest.lower()

    @staticmethod
    def partial_digest(buffer: bytes) -> str:
        """Hash an in-memory buffer (used for tests and previews)."""
        return hashlib.sha256(buffer).hexdigest()
