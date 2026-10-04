"""Logging setup.

Three rotating log files are produced inside the application data folder:

```
logs/app.log     # INFO level, general application flow
logs/error.log   # WARNING+ level, problems worth investigating
logs/scan.log    # DEBUG level, detailed scan/hash/similarity traces
```
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

from . import constants

_MAX_LOG_BYTES = 5 * 1024 * 1024  # 5 MiB per file
_BACKUP_COUNT = 3
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _file_handler(filename: str, level: int) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        os.path.join(constants.logs_dir(), filename),
        maxBytes=_MAX_LOG_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))
    return handler


def setup_logging(level: int = logging.INFO) -> None:
    """Attach the rotating file handlers. Safe to call once."""
    global _configured
    if _configured:
        return

    root = logging.getLogger()

    root.addHandler(_file_handler("app.log", logging.INFO))
    root.addHandler(_file_handler("error.log", logging.WARNING))

    scan_logger = logging.getLogger("scan")
    scan_logger.setLevel(logging.DEBUG)
    scan_logger.addHandler(_file_handler("scan.log", logging.DEBUG))
    scan_logger.propagate = False

    root.setLevel(level)

    # Never let a logging call raise and crash the application.
    logging.raiseExceptions = False
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger.

    Names starting with ``scan`` are routed to the detailed ``scan.log`` file
    instead of the root handlers.
    """
    if name.startswith("scan"):
        return logging.getLogger("scan").getChild(name.removeprefix("scan").lstrip("."))
    return logging.getLogger(name)


def log_exception(logger: logging.Logger, message: str, exc: Optional[BaseException] = None) -> None:
    """Log an exception without re-raising it."""
    if exc is None:
        logger.exception(message)
    else:
        logger.exception("%s: %s", message, exc)
