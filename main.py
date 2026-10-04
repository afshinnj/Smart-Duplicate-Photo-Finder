"""Smart Duplicate Photo Finder - application entry point.

Boots logging, loads the persisted configuration, opens the SQLite database and
shows the main window. Everything runs locally; no network access is needed.
"""

from __future__ import annotations

import os
import sys
import traceback
from typing import Optional

os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

from PySide6.QtCore import Qt  # noqa: E402  (env must be set before Qt import)
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from src.core import constants  # noqa: E402
from src.core.config import AppConfig  # noqa: E402
from src.core.logger import get_logger, setup_logging  # noqa: E402
from src.database.database import Database  # noqa: E402
from src.i18n import translator  # noqa: E402
from src.ui.app_context import AppContext  # noqa: E402
from src.ui.main_window import MainWindow  # noqa: E402

_log = get_logger("main")


def _bootstrap() -> Optional[AppContext]:
    """Build the backend context, reporting failures instead of crashing."""
    setup_logging()
    try:
        config = AppConfig.load()
        translator().set_language(config.general.language.value)
        database = Database()
        return AppContext(database=database, config=config)
    except Exception:
        _log.critical("Cannot start the application:\n%s", traceback.format_exc())
        QMessageBox.critical(
            None,
            constants.APP_NAME,
            "The application cannot start.\n"
            f"Details are logged to {constants.logs_dir()}.",
        )
        return None


def main(argv: Optional[list] = None) -> int:
    """Run the application until the user closes the window."""
    argv = list(sys.argv if argv is None else argv)
    application = QApplication(argv)
    application.setApplicationName(constants.APP_NAME)
    application.setApplicationDisplayName(constants.APP_NAME)
    application.setOrganizationName(constants.ORG_NAME)
    application.setOrganizationDomain(constants.ORG_DOMAIN)

    context = _bootstrap()
    if context is None:
        return 1

    application.setLayoutDirection(translator().layout_direction)
    window = MainWindow(context)
    window.show()
    window.show_page("dashboard")

    _log.info("%s %s started", constants.APP_NAME, constants.APP_VERSION)
    exit_code = application.exec()
    _log.info("%s exited with code %d", constants.APP_NAME, exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
