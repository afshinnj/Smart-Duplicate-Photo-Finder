"""Landing page: headline statistics and shortcuts to the other pages."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.constants import ScanStatus
from ...models.scan_session import ScanSession
from ...services.progress import format_size
from ...i18n import tr
from ..widgets import StatCard


class DashboardPage(QWidget):
    """Shows aggregate statistics and the primary navigation shortcuts."""

    navigate_requested = Signal(str)  # page key: scan / results / history

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._context = context
        self._build()
        self.refresh()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        self._title = QLabel(tr("nav_dashboard"), self)
        self._title.setObjectName("PageTitle")
        self._subtitle = QLabel(tr("app_tagline"), self)
        self._subtitle.setObjectName("PageSubtitle")
        root.addWidget(self._title)
        root.addWidget(self._subtitle)

        # --- statistic cards -------------------------------------------
        self._stats_row = QGridLayout(self)
        self._stats_row.setSpacing(14)
        self._cards: List[StatCard] = []

        self._card_images = StatCard(tr("stats_total_images"), parent=self)
        self._card_groups = StatCard(tr("stats_duplicate_groups"), parent=self)
        self._card_space = StatCard(tr("stats_wasted_space"), parent=self)
        self._card_last = StatCard(tr("stats_last_scan"), parent=self)
        for index, card in enumerate(
            (self._card_images, self._card_groups, self._card_space, self._card_last)
        ):
            self._stats_row.addWidget(card, 0, index)
            # Equal stretches keep the four cards the same width at any window size.
            self._stats_row.setColumnStretch(index, 1)
            self._cards.append(card)
        root.addLayout(self._stats_row)

        # --- shortcuts ---------------------------------------------------
        buttons = QHBoxLayout(self)
        buttons.setSpacing(10)
        self._btn_scan = QPushButton(tr("scan_start"), self)
        self._btn_scan.setMinimumHeight(44)
        self._btn_results = QPushButton(tr("nav_results"), self)
        self._btn_results.setObjectName("SecondaryButton")
        self._btn_results.setMinimumHeight(44)
        self._btn_history = QPushButton(tr("nav_history"), self)
        self._btn_history.setObjectName("SecondaryButton")
        self._btn_history.setMinimumHeight(44)
        buttons.addWidget(self._btn_scan)
        buttons.addWidget(self._btn_results)
        buttons.addWidget(self._btn_history)
        buttons.addStretch()
        root.addLayout(buttons)

        self._btn_scan.clicked.connect(lambda: self.navigate_requested.emit("scan"))
        self._btn_results.clicked.connect(lambda: self.navigate_requested.emit("results"))
        self._btn_history.clicked.connect(lambda: self.navigate_requested.emit("history"))

        # --- recent sessions ---------------------------------------------
        self._recent_box = QFrame(self)
        self._recent_box.setObjectName("Card")
        recent_layout = QVBoxLayout(self._recent_box)
        recent_layout.setContentsMargins(16, 14, 16, 14)
        recent_layout.setSpacing(8)
        self._recent_title = QLabel(tr("stats_last_scan"), self._recent_box)
        self._recent_title.setObjectName("PageSubtitle")
        self._recent_detail = QLabel("", self._recent_box)
        self._recent_detail.setObjectName("DimLabel")
        self._recent_detail.setWordWrap(True)
        recent_layout.addWidget(self._recent_title)
        recent_layout.addWidget(self._recent_detail)
        root.addWidget(self._recent_box)

        root.addStretch()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload the aggregates from the database."""
        history = self._context.history_service
        total_images = history.total_images()
        total_groups = history.total_groups()
        wasted = self._wasted_total()

        self._card_images.set_value(f"{total_images:,}")
        self._card_groups.set_value(f"{total_groups:,}")
        self._card_space.set_value(format_size(wasted))

        session = history.latest_session()
        if session is not None:
            self._card_last.set_value(self._status_label(session))
            self._recent_detail.setText(self._session_detail(session))
        else:
            self._card_last.set_value(tr("stats_never"))
            self._recent_detail.setText(tr("history_empty"))

    def _wasted_total(self) -> int:
        """Recoverable space reported by the most recent scan.

        Sessions overlap (the same library is re-scanned), so summing the column
        across sessions would multiply-count the same duplicates.
        """
        session = self._context.history_service.latest_session()
        return session.space_recoverable if session is not None else 0

    @staticmethod
    def _status_label(session: ScanSession) -> str:
        labels = {
            ScanStatus.COMPLETED: tr("status_done"),
            ScanStatus.RUNNING: tr("status_scanning"),
            ScanStatus.PENDING: tr("status_ready"),
            ScanStatus.CANCELLED: tr("scan_stage_cancelled"),
            ScanStatus.FAILED: tr("scan_stage_failed"),
            ScanStatus.PAUSED: tr("scan_pause"),
        }
        return labels.get(session.status, session.status.value)

    @staticmethod
    def _session_detail(session: ScanSession) -> str:
        folders = ", ".join(session.folders) if session.folders else "-"
        when = session.start_time.strftime("%Y-%m-%d %H:%M") if session.start_time else "--"
        return (
            f"{when} · {session.files_scanned:,} {tr('scan_files_scanned').lower()} · "
            f"{session.images_found:,} {tr('scan_images_found').lower()} · "
            f"{session.duplicates_found:,} {tr('stats_duplicates').lower()} · "
            f"{tr('stats_scanned_folders')}: {folders}"
        )

    # ------------------------------------------------------------------
    # Retranslation
    # ------------------------------------------------------------------

    def retranslate(self) -> None:
        self._title.setText(tr("nav_dashboard"))
        self._subtitle.setText(tr("app_tagline"))
        self._card_images.set_title(tr("stats_total_images"))
        self._card_groups.set_title(tr("stats_duplicate_groups"))
        self._card_space.set_title(tr("stats_wasted_space"))
        self._card_last.set_title(tr("stats_last_scan"))
        self._btn_scan.setText(tr("scan_start"))
        self._btn_results.setText(tr("nav_results"))
        self._btn_history.setText(tr("nav_history"))
        self._recent_title.setText(tr("stats_last_scan"))
        self.refresh()
