"""Main application window.

Owns the sidebar, the stacked page container and the shared backend context.
Navigation between pages is driven through the sidebar buttons; cross-page
actions (view results of a given session, compare two images) are wired here.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from ..core import constants
from ..core.config import Theme
from ..core.logger import get_logger
from ..i18n import is_rtl, translator, tr
from ..similarity.similarity_engine import SimilarityEngine
from .app_context import AppContext
from .app_style import style_sheet
from .pages import (
    CompareDialog,
    DashboardPage,
    HistoryPage,
    ResultsPage,
    ScanPage,
    SettingsPage,
)

_log = get_logger("ui.main_window")

_PAGES = (
    ("dashboard", "nav_dashboard", "◧"),
    ("scan", "nav_scan", "⌕"),
    ("results", "nav_results", "◫"),
    ("history", "nav_history", "◷"),
    ("settings", "nav_settings", "✦"),
)


class MainWindow(QMainWindow):
    """Application shell that hosts every page."""

    def __init__(self, context: Optional[AppContext] = None, parent=None) -> None:
        super().__init__(parent)
        self._context = context or AppContext()
        self._pages: Dict[str, QWidget] = {}
        self._exiting = False
        self._build()
        self._apply_theme()
        self._apply_direction()
        self._retranslate()
        self._setup_tray()
        self._purge_quarantine_later()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        self.setWindowTitle(constants.APP_NAME)
        self.resize(1180, 760)
        self.setMinimumSize(940, 620)

        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_content(), stretch=1)
        self.setCentralWidget(central)

        self._build_menu()
        self._build_statusbar()

        self._context.scan_service  # ensure the service is ready
        self._wire_signals()

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame(self)
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(216)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 18, 12, 18)
        layout.setSpacing(6)

        self._brand = QLabel(constants.APP_NAME, sidebar)
        self._brand.setObjectName("PageTitle")
        self._brand.setWordWrap(True)
        layout.addWidget(self._brand)
        layout.addSpacing(12)

        self._nav_group = QButtonGroup(sidebar)
        self._nav_group.setExclusive(True)
        self._nav_buttons: Dict[str, QPushButton] = {}
        for key, label, icon in _PAGES:
            button = QPushButton(f"  {icon}  {tr(label)}", sidebar)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setMinimumHeight(42)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, k=key: self.show_page(k))
            self._nav_group.addButton(button)
            self._nav_buttons[key] = button
            layout.addWidget(button)
            page = self._make_page(key)
            self._pages[key] = page

        layout.addStretch()
        version = QLabel(f"{constants.APP_VERSION}", sidebar)
        version.setObjectName("DimLabel")
        version.setAlignment(Qt.AlignCenter)
        layout.addWidget(version)
        return sidebar

    def _build_content(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        self._stack = QStackedWidget(container)
        for key, _, _icon in _PAGES:
            self._stack.addWidget(self._pages[key])
        layout.addWidget(self._stack)
        return container

    def _make_page(self, key: str) -> QWidget:
        context = self._context
        if key == "dashboard":
            return DashboardPage(context, self)
        if key == "scan":
            return ScanPage(context, self)
        if key == "results":
            return ResultsPage(context, self)
        if key == "history":
            return HistoryPage(context, self)
        return SettingsPage(context, self)

    def _build_menu(self) -> None:
        from PySide6.QtGui import QKeySequence

        file_menu = self.menuBar().addMenu(tr("nav_scan"))
        self._action_scan = QAction(tr("scan_start"), self)
        self._action_scan.setShortcut(QKeySequence("Ctrl+S"))
        self._action_scan.triggered.connect(lambda: self.show_page("scan"))
        file_menu.addAction(self._action_scan)

        self._action_quit = QAction(tr("dialog_close"), self)
        self._action_quit.setShortcut(QKeySequence("Ctrl+Q"))
        self._action_quit.triggered.connect(self.close)
        file_menu.addAction(self._action_quit)

        help_menu = self.menuBar().addMenu("?")
        self._action_about = QAction(constants.APP_NAME, self)
        self._action_about.triggered.connect(self._show_about)
        help_menu.addAction(self._action_about)

    def _build_statusbar(self) -> None:
        bar = self.statusBar()
        self._status_label = QLabel(tr("status_ready"))
        bar.addWidget(self._status_label)
        bar.showMessage(tr("status_ready"))

    def _setup_tray(self) -> None:
        self._tray: Optional[QSystemTrayIcon] = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self)
        self._tray.setToolTip(constants.APP_NAME)
        self._tray.activated.connect(self._on_tray_activated)
        # A real icon lives in assets/icons; fall back to a generated pixmap.
        self._tray.setIcon(self.windowIcon())
        self._tray.show()

    def _purge_quarantine_later(self) -> None:
        """Expire old quarantine entries shortly after startup, off the UI path."""
        QTimer.singleShot(2500, self._purge_quarantine)

    def _purge_quarantine(self) -> None:
        try:
            purged = self._context.make_cleanup_service().purge_expired_quarantine()
            if purged:
                _log.info("Purged %d expired quarantine entries", purged)
        except Exception:
            _log.debug("Quarantine purge skipped")

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def _wire_signals(self) -> None:
        dashboard = self._pages["dashboard"]
        dashboard.navigate_requested.connect(self.show_page)

        scan_page = self._pages["scan"]
        scan_page.scan_started.connect(self._on_scan_started)
        scan_page.scan_finished.connect(self._on_scan_finished)

        results_page = self._pages["results"]
        results_page.compare_requested.connect(self._compare_records)
        results_page.status_message.connect(self._status_label.setText)

        history_page = self._pages["history"]
        history_page.view_results_requested.connect(self._show_session_results)

        settings_page = self._pages["settings"]
        settings_page.language_changed.connect(self._on_language_changed)
        settings_page.theme_changed.connect(self._on_theme_changed)

        translator().language_changed.connect(self._retranslate)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def show_page(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None:
            return
        self._stack.setCurrentWidget(page)
        self._nav_buttons[key].setChecked(True)
        if key == "dashboard":
            dashboard = self._pages["dashboard"]
            dashboard.refresh()
        elif key == "results":
            results = self._pages["results"]
            if not results._groups:  # noqa: SLF001 - lazy load on first visit
                results.load_latest()
        elif key == "history":
            history = self._pages["history"]
            history.refresh()
        self._status_label.setText(tr("status_ready"))

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _on_scan_started(self) -> None:
        self._status_label.setText(tr("status_scanning"))

    def _on_scan_finished(self, result) -> None:
        groups = getattr(result, "groups", []) or []
        duplicates = getattr(result, "duplicate_count", 0)
        self._status_label.setText(
            f"{tr('status_done')} · {duplicates:,} {tr('stats_duplicates')}"
        )
        results_page = self._pages["results"]
        results_page.set_groups(groups, getattr(getattr(result, "session", None), "id", None))
        if groups:
            self.show_page("results")

    def _show_session_results(self, session_id: int) -> None:
        try:
            groups = self._context.history_service.load_groups(session_id)
        except Exception as exc:
            _log.exception("Cannot load groups for session %s", session_id)
            QMessageBox.critical(self, tr("nav_results"), str(exc))
            return
        results_page = self._pages["results"]
        results_page.set_groups(groups, session_id)
        self.show_page("results")

    def _compare_records(self, record_a, record_b) -> None:
        engine = SimilarityEngine(self._context.config.similarity)
        dialog = CompareDialog(record_a, record_b, engine, self)
        dialog.exec()

    # ------------------------------------------------------------------
    # Language and theme
    # ------------------------------------------------------------------

    def _on_language_changed(self, code: str) -> None:
        translator().set_language(code)
        self._apply_direction()
        self._status_label.setText(tr("settings_saved"))

    def _on_theme_changed(self, theme: Theme) -> None:
        self._context.config.general.theme = theme
        self._context.save_config()
        self._apply_theme()

    def _apply_theme(self) -> None:
        self.setStyleSheet(style_sheet(self._context.config.general.theme, translator().is_rtl))

    def _apply_direction(self) -> None:
        direction = translator().layout_direction
        self.setLayoutDirection(direction)
        for page in self._pages.values():
            page.setLayoutDirection(direction)
        self._status_label.setAlignment(
            Qt.AlignRight if direction == Qt.RightToLeft else Qt.AlignLeft
        )
        # The stylesheet holds a few direction-dependent rules (sidebar border,
        # nav button alignment, group box title anchor) that Qt will not mirror.
        self._apply_theme()

    def _retranslate(self) -> None:
        self.setWindowTitle(tr("app_name"))
        self._brand.setText(tr("app_name"))
        for key, label, icon in _PAGES:
            self._nav_buttons[key].setText(f"  {icon}  {tr(label)}")
        for page in self._pages.values():
            retranslate = getattr(page, "retranslate", None)
            if callable(retranslate):
                retranslate()
        self._action_scan.setText(tr("scan_start"))
        self._action_quit.setText(tr("dialog_close"))
        self._action_about.setText(constants.APP_NAME)
        self._status_label.setText(tr("status_ready"))

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        scan_page = self._pages.get("scan")
        if scan_page is not None and scan_page.is_scanning():
            answer = QMessageBox.question(
                self,
                tr("nav_scan"),
                tr("scan_cancel") + "?",
            )
            if answer not in (QMessageBox.Yes, QMessageBox.Ok):
                event.ignore()
                return
            scan_page.cancel_scan()

        if self._tray is not None and self._context.config.general.minimize_to_tray and not self._exiting:
            event.ignore()
            self.hide()
            self._tray.showMessage(constants.APP_NAME, tr("settings_minimize_to_tray"))
            return

        self._exiting = True
        try:
            self._context.close()
        except Exception:
            pass
        super().closeEvent(event)

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger or reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.raise_()
            self.activateWindow()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            constants.APP_NAME,
            f"<h3>{tr('app_name')}</h3>"
            f"<p>{tr('app_tagline')}</p>"
            f"<p style='color: gray'>{constants.APP_NAME} {constants.APP_VERSION} "
            f"· {constants.ORG_NAME}</p>",
        )
