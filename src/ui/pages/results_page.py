"""Results page.

Renders the duplicate groups of the latest (or selected) scan as a stack of
:class:`~ui.widgets.group_card.GroupCard` widgets, with filtering, sorting,
search, batch deletion through the cleanup service and undo support.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import List, Optional

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core.constants import CleanupMethod, SimilarityRating
from ...core.logger import get_logger
from ...models.duplicate_group import DuplicateGroup
from ...models.image_model import ImageRecord
from ...services.progress import format_size
from ...i18n import tr
from ..widgets.group_card import GroupCard

_log = get_logger("ui.results_page")


class ResultsPage(QWidget):
    """Browse the groups produced by a scan and clean up the duplicates."""

    compare_requested = Signal(object, object)  # record_a, record_b
    status_message = Signal(str)

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._context = context
        self._groups: List[DuplicateGroup] = []
        self._cards: List[GroupCard] = []
        self._session_id: Optional[int] = None
        self._selected_paths: set[str] = set()
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self._apply_filters)
        self._scroll_restore_timer = QTimer(self)
        self._scroll_restore_timer.setSingleShot(True)
        self._scroll_restore_timer.timeout.connect(self._restore_scroll_position)
        self._pending_scroll_position = 0
        self._build()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)
        self._title = QLabel(tr("nav_results"), self)
        self._title.setObjectName("PageTitle")
        header.addWidget(self._title)
        header.addStretch()
        self._summary = QLabel("", self)
        self._summary.setObjectName("PageSubtitle")
        header.addWidget(self._summary)
        root.addLayout(header)

        # Toolbar ----------------------------------------------------------
        # Split into a filters row and an actions row: a single row overflows the
        # page once the translated labels are measured with a real Persian font.
        toolbar = QVBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)

        filters = QHBoxLayout()
        filters.setSpacing(8)

        self._search = QLineEdit(self)
        self._search.setPlaceholderText(tr("results_search"))
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._schedule_search)
        filters.addWidget(self._search, stretch=3)

        self._filter = QComboBox(self)
        self._filter.addItem(tr("results_filter_all"), "all")
        self._filter.addItem(tr("results_filter_exact"), "exact")
        self._filter.addItem(tr("results_filter_very_similar"), "very_similar")
        self._filter.addItem(tr("results_filter_similar"), "similar")
        self._filter.addItem(tr("results_filter_large"), "large")
        self._filter.addItem(tr("results_filter_small"), "small")
        self._filter.addItem(tr("results_filter_high_res"), "high_res")
        self._filter.addItem(tr("results_filter_low_res"), "low_res")
        self._filter.currentIndexChanged.connect(self._apply_filters)
        filters.addWidget(self._filter, stretch=1)

        self._sort = QComboBox(self)
        self._sort.addItem(tr("results_sort_similarity"), "similarity")
        self._sort.addItem(tr("results_sort_size"), "size")
        self._sort.addItem(tr("results_sort_resolution"), "resolution")
        self._sort.addItem(tr("results_sort_date"), "date")
        self._sort.addItem(tr("results_sort_filename"), "filename")
        self._sort.addItem(tr("results_sort_path"), "path")
        self._sort.currentIndexChanged.connect(self._apply_filters)
        filters.addWidget(self._sort, stretch=1)
        toolbar.addLayout(filters)

        actions = QHBoxLayout()
        actions.setSpacing(8)

        self._btn_select_all = QPushButton(tr("results_select_all"), self)
        self._btn_select_all.setObjectName("SecondaryButton")
        self._btn_select_all.clicked.connect(self._select_all_duplicates)
        actions.addWidget(self._btn_select_all)

        self._selection_label = QLabel("", self)
        self._selection_label.setObjectName("DimLabel")
        actions.addWidget(self._selection_label)

        actions.addStretch()

        self._btn_undo = QPushButton(tr("cleanup_undo"), self)
        self._btn_undo.setObjectName("SecondaryButton")
        self._btn_undo.clicked.connect(self._undo_cleanup)
        actions.addWidget(self._btn_undo)

        self._btn_delete = QPushButton(tr("results_delete_selected"), self)
        self._btn_delete.setObjectName("DangerButton")
        self._btn_delete.clicked.connect(self._delete_selected)
        actions.addWidget(self._btn_delete)
        toolbar.addLayout(actions)
        root.addLayout(toolbar)

        self._undo_label = QLabel("", self)
        self._undo_label.setObjectName("DimLabel")
        root.addWidget(self._undo_label)

        # Cards ------------------------------------------------------------
        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(12)
        self._container_layout.addStretch()
        self._scroll.setWidget(self._container)
        root.addWidget(self._scroll, stretch=1)

        self._empty_label = QLabel("", self)
        self._empty_label.setObjectName("EmptyState")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setTextFormat(Qt.RichText)
        root.addWidget(self._empty_label)

        self._update_undo_state()
        self._refresh_empty_state()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_groups(self, groups: List[DuplicateGroup], session_id: Optional[int] = None) -> None:
        self._search_timer.stop()
        self._groups = list(groups)
        self._session_id = session_id
        self._selected_paths.clear()
        self._scroll.verticalScrollBar().setValue(0)
        self._apply_filters()

    def load_latest(self) -> bool:
        """Show the groups of the most recent finished scan."""
        session = self._context.history_service.latest_session()
        if session is None or session.id is None:
            self.set_groups([])
            return False
        groups = self._context.history_service.load_groups(session.id)
        self.set_groups(groups, session.id)
        return True

    def refresh(self) -> None:
        self.load_latest()
        self._update_undo_state()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _clear_cards(self) -> None:
        for card in self._cards:
            self._container_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

    def _rebuild_cards(self) -> None:
        scroll_bar = self._scroll.verticalScrollBar()
        scroll_position = scroll_bar.value()
        self._clear_cards()
        self._context.thumbnail_loader.clear_pending()
        for index, group in enumerate(self._filtered_and_sorted()):
            card = GroupCard(group, index, parent=self._container)
            card.delete_requested.connect(self._delete_group_records)
            card.keeper_changed.connect(self._persist_keeper_choice)
            card.selection_changed.connect(self._on_selection_changed)
            card.compare_requested.connect(self.compare_requested.emit)
            card.open_folder_requested.connect(self._open_folder)
            card.thumbnail_requested.connect(self._load_thumbnail)
            self._container_layout.insertWidget(self._container_layout.count() - 1, card)
            self._cards.append(card)
            for tile in card._tiles:  # noqa: SLF001 - restore selection after rebuilding
                tile.check.setChecked(self._path_key(tile.record) in self._selected_paths)
            # Connected above; the card must only emit now, after the wiring is
            # in place, otherwise the requests are lost.
            card.request_thumbnails()
        self._update_summary()
        self._update_selection_label()
        self._refresh_empty_state()
        self._pending_scroll_position = scroll_position
        self._scroll_restore_timer.start(0)

    def _restore_scroll_position(self) -> None:
        scroll_bar = self._scroll.verticalScrollBar()
        scroll_bar.setValue(min(self._pending_scroll_position, scroll_bar.maximum()))

    @staticmethod
    def _path_key(record: ImageRecord) -> str:
        return os.path.normcase(os.path.abspath(record.path))

    def _on_selection_changed(self, record: ImageRecord, selected: bool) -> None:
        key = self._path_key(record)
        if selected:
            self._selected_paths.add(key)
        else:
            self._selected_paths.discard(key)
        self._update_selection_label()

    def _update_selection_label(self) -> None:
        count = len(self._selected_paths)
        self._selection_label.setText(
            tr("cleanup_files", count=count) if count else ""
        )
        self._selection_label.setVisible(count > 0)

    def _load_thumbnail(self, path: str, tile) -> None:
        self._context.thumbnail_loader.request(path).finished.connect(
            lambda loaded_path, pixmap: self._on_thumbnail(loaded_path, pixmap)
        )

    def _persist_keeper_choice(self, group: DuplicateGroup, record: ImageRecord) -> None:
        if group.id is None or record.id is None:
            return
        try:
            saved = self._context.history_service.update_group_keeper(group.id, record.id)
            if not saved:
                raise RuntimeError("The selected image is not a member of this saved group")
        except Exception as exc:
            _log.exception("Could not save keeper choice for group %s", group.id)
            QMessageBox.warning(
                self,
                tr("results_keep_this"),
                f"{tr('results_keeper_save_failed')}\n\n{exc}",
            )

    def _on_thumbnail(self, path: str, pixmap) -> None:
        for card in self._cards:
            card.set_thumbnail(path, pixmap)

    def _update_summary(self) -> None:
        groups = self._groups
        duplicates = sum(len(group.duplicates) for group in groups)
        wasted = sum(group.wasted_bytes for group in groups)
        self._summary.setText(
            f"{tr('results_groups_count', count=len(groups))} · "
            f"{duplicates:,} {tr('stats_duplicates')} · "
            f"{tr('stats_space_recoverable')}: {format_size(wasted)}"
        )

    def _refresh_empty_state(self) -> None:
        empty = not self._cards
        self._empty_label.setVisible(empty)
        self._scroll.setVisible(not empty)
        message = (
            tr("results_unavailable")
            if not self._groups
            else tr("results_empty")
        )
        self._empty_label.setText(message)

    # ------------------------------------------------------------------
    # Filtering and sorting
    # ------------------------------------------------------------------

    def _filtered_and_sorted(self) -> List[DuplicateGroup]:
        query = self._search.text().strip().lower()
        filter_key = self._filter.currentData()
        sort_key = self._sort.currentData()

        groups = self._groups
        if query:
            groups = [
                group
                for group in groups
                if any(query in item.filename.lower() or query in item.path.lower() for item in group.items)
            ]

        if filter_key in ("exact", "very_similar", "similar"):
            groups = [group for group in groups if self._matches_rating(group, filter_key)]
        elif filter_key in ("large", "small"):
            threshold_mb = 5.0
            groups = [
                group
                for group in groups
                if self._matches_size(group, filter_key, threshold_mb)
            ]
        elif filter_key in ("high_res", "low_res"):
            threshold_mp = 2.0
            groups = [
                group
                for group in groups
                if self._matches_resolution(group, filter_key, threshold_mp)
            ]

        return sorted(groups, key=lambda group: self._sort_key(group, sort_key))

    @staticmethod
    def _matches_rating(group: DuplicateGroup, key: str) -> bool:
        rating = group.rating
        if key == "exact":
            return group.is_exact or rating == SimilarityRating.ALMOST_SAME
        if key == "very_similar":
            return rating in (SimilarityRating.VERY_SIMILAR, SimilarityRating.ALMOST_SAME, SimilarityRating.EXACT)
        return rating in (SimilarityRating.SIMILAR, SimilarityRating.VERY_SIMILAR)

    @staticmethod
    def _matches_size(group: DuplicateGroup, key: str, threshold_mb: float) -> bool:
        threshold = threshold_mb * 1024 * 1024
        largest = max((item.size for item in group.items), default=0)
        return largest >= threshold if key == "large" else largest < threshold

    @staticmethod
    def _matches_resolution(group: DuplicateGroup, key: str, threshold_mp: float) -> bool:
        largest = max((item.megapixels for item in group.items), default=0.0)
        return largest >= threshold_mp if key == "high_res" else largest < threshold_mp

    @staticmethod
    def _sort_key(group: DuplicateGroup, key: str):
        keeper = group.keeper
        if key == "size":
            return (-keeper.size, -group.similarity_score)
        if key == "resolution":
            return (-keeper.megapixels, -group.similarity_score)
        if key == "date":
            return (-(keeper.created_at or 0), -group.similarity_score)
        if key == "filename":
            return (keeper.filename.lower(), -group.similarity_score)
        if key == "path":
            return (keeper.path.lower(), -group.similarity_score)
        return (-group.similarity_score, -group.wasted_bytes)

    def _schedule_search(self) -> None:
        self._search_timer.start()

    def _apply_filters(self) -> None:
        self._search_timer.stop()
        self._rebuild_cards()

    def _select_all_duplicates(self) -> None:
        any_selected = any(card.selected_records() for card in self._cards)
        for card in self._cards:
            keeper_id = card.group.keeper.id
            for tile in card._tiles:  # noqa: SLF001 - tiles are card internals
                if tile.record.id != keeper_id:
                    tile.check.setChecked(not any_selected)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _selected_records(self) -> List[ImageRecord]:
        records: List[ImageRecord] = []
        for card in self._cards:
            records.extend(card.selected_records())
        # A record may belong to several groups; remove each file only once.
        seen = set()
        unique: List[ImageRecord] = []
        for record in records:
            if record.id in seen:
                continue
            seen.add(record.id)
            unique.append(record)
        return unique

    def _delete_group_records(self, group: DuplicateGroup, records: List[ImageRecord]) -> None:
        self._run_cleanup(records, focus_group=group)

    def _delete_selected(self) -> None:
        records = self._selected_records()
        if not records:
            QMessageBox.information(self, tr("results_delete"), tr("results_empty"))
            return
        self._run_cleanup(records)

    def _run_cleanup(self, records: List[ImageRecord], focus_group: Optional[DuplicateGroup] = None) -> None:
        settings = self._context.config.cleanup
        method = settings.method

        if method == CleanupMethod.PERMANENT and settings.warn_before_permanent_delete:
            if not self._confirm_permanent(records):
                return
        elif not self._confirm_delete(records, method):
            return

        service = self._context.make_cleanup_service()
        try:
            result = service.remove(records)
        except Exception as exc:
            _log.exception("Cleanup failed")
            QMessageBox.critical(self, tr("results_delete"), str(exc))
            return

        if result.removed_count:
            self._after_cleanup(result.removed_count, result.total_size, focus_group)
        if result.failed_count:
            detail = "\n".join(f"{record.filename}: {reason}" for record, reason in result.failed_count[:10])
            QMessageBox.warning(
                self,
                tr("results_delete"),
                f"{result.failed_count} file(s) could not be removed:\n{detail}",
            )

    def _confirm_delete(self, records: List[ImageRecord], method: CleanupMethod) -> bool:
        size = sum(record.size for record in records)
        method_text = {
            CleanupMethod.QUARANTINE: tr("cleanup_quarantine"),
            CleanupMethod.RECYCLE_BIN: tr("cleanup_move_recycle"),
            CleanupMethod.PERMANENT: tr("cleanup_permanent"),
        }.get(method, method.value)
        message = (
            f"{tr('cleanup_confirm_message')}\n\n"
            f"{tr('cleanup_files', count=len(records))}\n"
            f"{tr('cleanup_total_size')} {format_size(size)}\n\n"
            f"{method_text}"
        )
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Question)
        dialog.setWindowTitle(tr("cleanup_confirm_title"))
        dialog.setText(message)
        dialog.setDetailedText(self._cleanup_details(records))
        dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        dialog.setDefaultButton(QMessageBox.No)
        return dialog.exec() == QMessageBox.Yes

    def _confirm_permanent(self, records: List[ImageRecord]) -> bool:
        size = sum(record.size for record in records)
        message = (
            f"{tr('cleanup_permanent_warning')}\n\n"
            f"{tr('cleanup_files', count=len(records))} · {format_size(size)}"
        )
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle(tr("cleanup_confirm_title"))
        dialog.setText(message)
        dialog.setDetailedText(self._cleanup_details(records))
        dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        dialog.setDefaultButton(QMessageBox.No)
        return dialog.exec() == QMessageBox.Yes

    @staticmethod
    def _cleanup_details(records: List[ImageRecord]) -> str:
        header = f"{tr('cleanup_preview_file')}\t{tr('cleanup_preview_size')}\t{tr('cleanup_preview_path')}"
        rows = [
            f"{record.filename}\t{format_size(record.size)}\t{record.path}"
            for record in records
        ]
        return "\n".join([header, *rows])

    def _after_cleanup(self, removed: int, size: int, focus_group: Optional[DuplicateGroup]) -> None:
        _log.info("Removed %d files (%s)", removed, format_size(size))
        self.status_message.emit(tr("cleanup_files", count=removed))
        # Drop the removed items from the in-memory groups and re-render.
        for group in self._groups:
            group.items = [item for item in group.items if os.path.exists(item.path)]
        self._groups = [group for group in self._groups if len(group.items) > 1]
        self._selected_paths = {
            key for key in self._selected_paths if os.path.exists(key)
        }
        self._rebuild_cards()
        self._update_undo_state()

    def _undo_cleanup(self) -> None:
        service = self._context.make_cleanup_service()
        try:
            restored = service.undo()
        except Exception as exc:
            _log.exception("Undo failed")
            QMessageBox.critical(self, tr("cleanup_undo"), str(exc))
            return
        QMessageBox.information(
            self, tr("cleanup_undo"), tr("cleanup_undo_done", count=restored)
        )
        self._update_undo_state()

    def _update_undo_state(self) -> None:
        try:
            service = self._context.make_cleanup_service()
            count = service.pending_undo_count()
            size = service.pending_undo_size()
        except Exception:
            count, size = 0, 0
        self._undo_label.setText(
            f"{tr('cleanup_undo')}: {count:,} · {format_size(size)}"
            if count
            else ""
        )
        self._btn_undo.setEnabled(count > 0)

    # ------------------------------------------------------------------
    # Shell integration
    # ------------------------------------------------------------------

    def _open_folder(self, record: ImageRecord) -> None:
        path = record.path
        if not os.path.exists(path):
            QMessageBox.information(self, tr("results_open_folder"), tr("results_empty"))
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", path])
            else:
                subprocess.Popen(["xdg-open", os.path.dirname(path)])
        except Exception as exc:
            _log.warning("Cannot open folder for %s: %s", path, exc)

    # ------------------------------------------------------------------
    # Retranslation
    # ------------------------------------------------------------------

    def retranslate(self) -> None:
        self._title.setText(tr("nav_results"))
        self._search.setPlaceholderText(tr("results_search"))
        self._btn_select_all.setText(tr("results_select_all"))
        self._btn_undo.setText(tr("cleanup_undo"))
        self._btn_delete.setText(tr("results_delete_selected"))
        for card in self._cards:
            card.retranslate()
        self._update_summary()
        self._update_selection_label()
        self._refresh_empty_state()
        self._update_undo_state()
