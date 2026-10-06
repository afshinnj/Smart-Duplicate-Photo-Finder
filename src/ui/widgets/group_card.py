"""Group card used by the results page.

A :class:`GroupCard` renders one :class:`~models.duplicate_group.DuplicateGroup`:
a header with the type badge, similarity score and recoverable space, followed
by a horizontally scrolling row of :class:`ImageTile` widgets - one per member.
"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...core.constants import DuplicateType, SimilarityRating
from ...models.duplicate_group import DuplicateGroup
from ...models.image_model import ImageRecord
from ...services.progress import format_size
from ...i18n import tr

class ImageTile(QFrame):
    """One image inside a group: thumbnail, name, size and a keep badge."""

    selection_changed = Signal(object, bool)  # ImageRecord, checked
    open_folder_requested = Signal(object)
    compare_requested = Signal(object, object)  # record, other_record
    thumbnail_requested = Signal(object, object)  # path, tile

    TILE_SIZE = 150

    def __init__(self, record: ImageRecord, keeper: bool, parent=None) -> None:
        super().__init__(parent)
        self.record = record
        self.keeper = keeper
        self.setObjectName("Card")
        self.setFixedSize(self.TILE_SIZE + 16, self.TILE_SIZE + 74)
        self._build()
        self.retranslate()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.thumbnail = QLabel(self)
        self.thumbnail.setFixedSize(self.TILE_SIZE, self.TILE_SIZE)
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setObjectName("ThumbnailPlaceholder")
        self.thumbnail.setText("…")
        layout.addWidget(self.thumbnail)

        self.name_label = QLabel(self.record.filename, self)
        self.name_label.setWordWrap(False)
        self.name_label.setMaximumWidth(self.TILE_SIZE)
        self._tooltip = self.record.path
        self.name_label.setToolTip(self._tooltip)
        layout.addWidget(self.name_label)

        self.meta_label = QLabel("", self)
        self.meta_label.setObjectName("DimLabel")
        layout.addWidget(self.meta_label)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        self._keep_badge = QLabel("", self)
        self._keep_badge.setObjectName("KeepBadge")
        row.addWidget(self._keep_badge)

        self.check = QCheckBox(self)
        self.check.setChecked(not self.keeper)
        self.check.stateChanged.connect(self._on_check_changed)
        row.addWidget(self.check)
        row.addStretch()
        layout.addLayout(row)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(2)
        self._btn_folder = QPushButton("📁", self)
        self._btn_folder.setObjectName("SecondaryButton")
        self._btn_folder.setFixedSize(28, 24)
        self._btn_folder.setToolTip(tr("results_open_folder"))
        self._btn_folder.clicked.connect(
            lambda: self.open_folder_requested.emit(self.record)
        )
        self._btn_compare = QPushButton("⇄", self)
        self._btn_compare.setObjectName("SecondaryButton")
        self._btn_compare.setFixedSize(28, 24)
        self._btn_compare.setToolTip(tr("results_compare"))
        self._btn_compare.clicked.connect(self._emit_compare)
        actions.addWidget(self._btn_folder)
        actions.addWidget(self._btn_compare)
        actions.addStretch()
        layout.addLayout(actions)

        self._compare_target: Optional[ImageRecord] = None
        self._update_meta()

    def _emit_compare(self) -> None:
        if self._compare_target is not None:
            self.compare_requested.emit(self.record, self._compare_target)

    def _update_meta(self) -> None:
        self.meta_label.setText(
            f"{format_size(self.record.size)} · {self.record.resolution}"
        )

    def _on_check_changed(self, state: int) -> None:
        self.selection_changed.emit(self.record, state == Qt.Checked.value)

    def set_thumbnail(self, pixmap) -> None:
        if pixmap is not None and not pixmap.isNull():
            self.thumbnail.setPixmap(
                pixmap.scaled(
                    self.TILE_SIZE,
                    self.TILE_SIZE,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )

    def set_compare_target(self, other: ImageRecord) -> None:
        self._compare_target = other

    def retranslate(self) -> None:
        self._keep_badge.setText(tr("results_keep_this") if self.keeper else "")
        self._btn_folder.setToolTip(tr("results_open_folder"))
        self._btn_compare.setToolTip(tr("results_compare"))
        self._update_meta()


class GroupCard(QFrame):
    """Renders one duplicate group with its member tiles."""

    delete_requested = Signal(object, list)  # group, records
    compare_requested = Signal(object, object)
    open_folder_requested = Signal(object)
    thumbnail_requested = Signal(object, object)  # path, tile

    def __init__(self, group: DuplicateGroup, index: int, parent=None) -> None:
        super().__init__(parent)
        self.group = group
        self.index = index
        self.setObjectName("Card")
        self._tiles: List[ImageTile] = []
        self._build()
        self.retranslate()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)

        self.badge = QLabel("", self)
        # The exact/similar variant is known up-front; choosing the object name
        # here lets the stylesheet pick the right colours without a re-polish.
        self.badge.setObjectName("BadgeExact" if self.group.is_exact else "BadgeSimilar")
        header.addWidget(self.badge)

        self.title = QLabel("", self)
        self.title.setObjectName("PageSubtitle")
        header.addWidget(self.title)

        header.addStretch()

        self.space_label = QLabel("", self)
        self.space_label.setObjectName("DimLabel")
        header.addWidget(self.space_label)

        self._btn_delete = QPushButton("", self)
        self._btn_delete.setObjectName("DangerButton")
        self._btn_delete.clicked.connect(self._emit_delete)
        header.addWidget(self._btn_delete)

        layout.addLayout(header)

        tiles_scroll = QScrollArea(self)
        tiles_scroll.setObjectName("TileScroll")
        tiles_scroll.setWidgetResizable(True)
        tiles_scroll.setFixedHeight(ImageTile.TILE_SIZE + 92)
        tiles_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        tiles_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tiles_scroll.setFrameShape(QFrame.NoFrame)

        tiles_widget = QWidget()
        tiles_layout = QHBoxLayout(tiles_widget)
        tiles_layout.setContentsMargins(0, 0, 0, 0)
        tiles_layout.setSpacing(10)
        tiles_layout.setDirection(QBoxLayout.LeftToRight)
        tiles_layout.addStretch()

        keeper = self.group.keeper
        for record in self.group.items:
            tile = ImageTile(record, keeper=record.id == keeper.id, parent=tiles_widget)
            tile.selection_changed.connect(self._on_selection_changed)
            tile.open_folder_requested.connect(self.open_folder_requested)
            tile.compare_requested.connect(self.compare_requested)
            if record.id != keeper.id:
                tile.set_compare_target(keeper)
            tiles_layout.addWidget(tile)
            self._tiles.append(tile)
        tiles_scroll.setWidget(tiles_widget)
        layout.addWidget(tiles_scroll)

        self._update_header()

    def request_thumbnails(self) -> None:
        """Ask the owner to decode the tiles' thumbnails.

        Emitted here rather than in the constructor so that callers can
        connect to :attr:`thumbnail_requested` first — a signal fired while
        building the widget would be lost.
        """
        for tile in self._tiles:
            self.thumbnail_requested.emit(tile.record.path, tile)

    def _update_header(self) -> None:
        group = self.group
        self.title.setText(
            f"{tr('results_group')} {self.index + 1} · {len(group.items)} "
            f"{tr('results_duplicate')}"
        )
        self.space_label.setText(
            f"{tr('stats_space_recoverable')}: {format_size(group.wasted_bytes)}"
        )
        exact = group.is_exact
        self.badge.setText(tr("results_filter_exact") if exact else tr("results_filter_similar"))

    def _emit_delete(self) -> None:
        self.delete_requested.emit(self.group, self.selected_records())

    def _on_selection_changed(self, record: ImageRecord, checked: bool) -> None:
        tile = self.tile_for(record)
        if tile is not None:
            tile.blockSignals(True)
            tile.check.setChecked(checked)
            tile.blockSignals(False)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def tile_for(self, record: ImageRecord) -> Optional[ImageTile]:
        for tile in self._tiles:
            if tile.record.id == record.id:
                return tile
        return None

    def selected_records(self) -> List[ImageRecord]:
        keeper_id = self.group.keeper.id
        return [
            tile.record
            for tile in self._tiles
            if tile.check.isChecked() and tile.record.id != keeper_id
        ]

    def set_thumbnail(self, path: str, pixmap) -> None:
        for tile in self._tiles:
            if tile.record.path == path:
                tile.set_thumbnail(pixmap)

    def retranslate(self) -> None:
        self._btn_delete.setText(tr("results_delete"))
        self._btn_delete.setToolTip(tr("results_delete_selected"))
        for tile in self._tiles:
            tile.retranslate()
        self._update_header()


def rating_label(rating: SimilarityRating) -> str:
    """Map a rating band to its translated label."""
    return {
        SimilarityRating.EXACT: tr("rating_identical"),
        SimilarityRating.ALMOST_SAME: tr("rating_almost_identical"),
        SimilarityRating.VERY_SIMILAR: tr("rating_very_similar"),
        SimilarityRating.SIMILAR: tr("rating_similar"),
        SimilarityRating.POSSIBLY_RELATED: tr("rating_possibly_related"),
        SimilarityRating.DIFFERENT: tr("rating_different"),
    }.get(rating, tr("rating_similar"))


def type_label(group_type: DuplicateType) -> str:
    return (
        tr("results_filter_exact")
        if group_type == DuplicateType.EXACT
        else tr("results_filter_similar")
    )
