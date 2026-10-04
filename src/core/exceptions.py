"""Application specific exception hierarchy."""

from __future__ import annotations


class AppError(Exception):
    """Base class for every error raised by the application."""


class ConfigError(AppError):
    """Raised when the configuration cannot be loaded or is invalid."""


class DatabaseError(AppError):
    """Raised on database connection or migration failures."""


class ScanError(AppError):
    """Raised when a scan cannot be started or continued."""


class ScanCancelled(ScanError):
    """Raised internally to unwind a cancelled scan."""

    def __init__(self, message: str = "Scan cancelled by user") -> None:
        super().__init__(message)


class ScanPaused(ScanError):
    """Raised internally when the caller asked for the scan to pause."""


class HashError(AppError):
    """Raised when a file cannot be read for hashing."""


class ImageProcessingError(AppError):
    """Raised when an image cannot be decoded or analysed."""


class UnsupportedFormatError(ImageProcessingError):
    """Raised when a file format is not supported."""


class CleanupError(AppError):
    """Raised when a file cannot be removed or restored."""


class AIEngineError(AppError):
    """Raised by the optional AI similarity engines."""
