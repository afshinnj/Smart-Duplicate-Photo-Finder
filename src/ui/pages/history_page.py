"""History page: past scan sessions with undo and per-session cleanup."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.constants import ScanStatus
from ...models.scan_session import ScanSession
from ...services.progress import format_size
from ...i18n import tr

_STATUS_ICONS = {
    ScanStatus.COMPLETED: "✓",
    ScanStatus.CANCELLED: "⊘",
    ScanStatus.FAILED: "✕",
    ScanStatus.RUNNING: "⟳",
    ScanStatus.PAUSED: "⏸",
    ScanStatus.PENDING: "…",
}


class HistoryPage(QWidget):
    """Lists previous scans and lets the user inspect or forget them."""

    view_results_requested = Signal(int)  # session id

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._context = context
        self._sessions: List[ScanSession] = []
        self._build()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        header = QHBoxLayout()
        self._title = QLabel(tr("nav_history"), self)
        self._title.setObjectName("PageTitle")
        header.addWidget(self._title)
        header.addStretch()
        self._btn_refresh = QPushButton(tr("history_refresh"), self)
        self._btn_refresh.setObjectName("SecondaryButton")
        self._btn_refresh.clicked.connect(self.refresh)
        header.addWidget(self._btn_refresh)
        root.addLayout(header)

        self._table = QTableWidget(0, 7, self)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.verticalHeader().setVisible(False)
        root.addWidget(self._table, stretch=1)

        actions = QHBoxLayout()
        actions.addStretch()
        self._btn_view = QPushButton(tr("history_view_results"), self)
        self._btn_view.clicked.connect(self._view_selected)
        self._btn_delete = QPushButton(tr("history_delete"), self)
        self._btn_delete.setObjectName("DangerButton")
        self._btn_delete.clicked.connect(self._delete_selected)
        actions.addWidget(self._btn_view)
        actions.addWidget(self._btn_delete)
        root.addLayout(actions)

        self._empty_label = QLabel("", self)
        self._empty_label.setObjectName("EmptyState")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setTextFormat(Qt.RichText)
        root.addWidget(self._empty_label)
        self._update_empty_text()

        self._table.itemSelectionChanged.connect(self._update_actions)
        self._update_actions()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        try:
            self._sessions = self._context.history_service.list_sessions(limit=100)
        except Exception:
            self._sessions = []
        self._populate()
        self._update_actions()

    def _populate(self) -> None:
        self._table.clearContents()
        self._table.setRowCount(len(self._sessions))
        self._table.setHorizontalHeaderLabels(
            [
                tr("history_start"),
                tr("stats_scanned_folders"),
                tr("history_files"),
                tr("history_images"),
                tr("history_duplicates"),
                tr("history_space"),
                tr("history_status"),
            ]
        )
        for row, session in enumerate(self._sessions):
            self._table.setItem(row, 0, self._item(self._started_label(session)))
            self._table.setItem(row, 1, self._item(self._folders_label(session)))
            self._table.setItem(row, 2, self._item(f"{session.files_scanned:,}"))
            self._table.setItem(row, 3, self._item(f"{session.images_found:,}"))
            self._table.setItem(row, 4, self._item(f"{session.duplicates_found:,}"))
            self._table.setItem(
                row, 5, self._item(format_size(session.space_recoverable))
            )
            self._table.setItem(row, 6, self._item(self._status_label(session)))
            self._table.item(row, 0).setData(Qt.UserRole, session.id)
        self._empty_label.setVisible(not self._sessions)
        self._table.setVisible(bool(self._sessions))

    @staticmethod
    def _item(text: str) -> QTableWidgetItem:
        return QTableWidgetItem(text)

    @staticmethod
    def _started_label(session: ScanSession) -> str:
        return session.start_time.strftime("%Y-%m-%d %H:%M") if session.start_time else "--"

    @staticmethod
    def _folders_label(session: ScanSession) -> str:
        if not session.folders:
            return "-"
        if len(session.folders) == 1:
            return session.folders[0]
        return f"{session.folders[0]} (+{len(session.folders) - 1})"

    @staticmethod
    def _status_label(session: ScanSession) -> str:
        icon = _STATUS_ICONS.get(session.status, "")
        labels = {
            ScanStatus.COMPLETED: tr("status_done"),
            ScanStatus.RUNNING: tr("status_scanning"),
            ScanStatus.PENDING: tr("status_ready"),
            ScanStatus.CANCELLED: tr("scan_stage_cancelled"),
            ScanStatus.FAILED: tr("scan_stage_failed"),
            ScanStatus.PAUSED: tr("scan_pause"),
        }
        return f"{icon} {labels.get(session.status, session.status.value)}"

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _selected_session(self) -> Optional[ScanSession]:
        rows = {index.row() for index in self._table.selectedIndexes()}
        if not rows:
            return None
        row = next(iter(rows))
        if 0 <= row < len(self._sessions):
            return self._sessions[row]
        return None

    def _update_actions(self) -> None:
        session = self._selected_session()
        self._btn_view.setEnabled(session is not None)
        self._btn_delete.setEnabled(session is not None)

    def _view_selected(self) -> None:
        session = self._selected_session()
        if session is None or session.id is None:
            return
        self.view_results_requested.emit(session.id)

    def _delete_selected(self) -> None:
        session = self._selected_session()
        if session is None or session.id is None:
            return
        confirm = QMessageBox.question(
            self,
            tr("history_delete"),
            f"{tr('history_delete')}? ({self._started_label(session)})",
        )
        if confirm not in (QMessageBox.Yes, QMessageBox.Ok):
            return
        try:
            self._context.history_service.delete_session(session.id)
        except Exception as exc:
            QMessageBox.critical(self, tr("history_delete"), str(exc))
            return
        self.refresh()

    def show_results(self, session_id: int) -> None:
        for row, session in enumerate(self._sessions):
            if session.id == session_id:
                self._table.selectRow(row)
                break

    # ------------------------------------------------------------------
    # Retranslation
    # ------------------------------------------------------------------

    def retranslate(self) -> None:
        self._title.setText(tr("nav_history"))
        self._btn_refresh.setText(tr("history_refresh"))
        self._btn_view.setText(tr("history_view_results"))
        self._btn_delete.setText(tr("history_delete"))
        self._update_empty_text()
        self._populate()
        self._update_actions()

    def _update_empty_text(self) -> None:
        self._empty_label.setText(
            f"<div style='font-size:36px'>◷</div><br>{tr('history_empty')}"
        )
