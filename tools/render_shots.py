"""Render the main window offscreen to verify the new styling and save shots.

Run with:  QT_QPA_PLATFORM=offscreen py -m tools.render_shots
"""

from __future__ import annotations

import os
import sys
import tempfile

# Isolate all user data (config/db/quarantine) before importing the app.
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".render_tmp")
os.makedirs(_DATA_DIR, exist_ok=True)
os.environ["SDPF_DATA_DIR"] = _DATA_DIR
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.core.config import AppConfig, Theme  # noqa: E402
from src.database.database import Database  # noqa: E402
from src.i18n import translator  # noqa: E402
from src.ui.app_context import AppContext  # noqa: E402
from src.ui.main_window import MainWindow  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def grab(window: MainWindow, name: str) -> None:
    window.grab().save(os.path.join(OUT, name))
    print("saved", name)


def sample(window: MainWindow, x: int, y: int, label: str) -> None:
    image: QImage = window.grab().toImage()
    print(f"  {label:28s} #{image.pixelColor(x, y).name()}  at ({x},{y})")


def main() -> int:
    app = QApplication(sys.argv)
    config = AppConfig.load()
    config.general.theme = Theme.DARK
    translator().set_language("fa")
    context = AppContext(database=Database(), config=config)
    window = MainWindow(context)
    window.resize(1180, 760)
    window.show()

    print("dark theme, RTL:")
    for key in ("dashboard", "scan", "results", "history", "settings"):
        window.show_page(key)
        app.processEvents()
        grab(window, f"shot_{key}.png")
    sample(window, 30, 40, "sidebar bg")
    sample(window, 100, 200, "nav button area")
    sample(window, 400, 300, "content bg")

    # Light theme sanity check.
    window._context.config.general.theme = Theme.LIGHT
    window._apply_theme()
    window.show_page("dashboard")
    app.processEvents()
    grab(window, "shot_dashboard_light.png")
    print("light theme:")
    sample(window, 30, 40, "sidebar bg")
    sample(window, 400, 300, "content bg")

    window.close()
    context.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
