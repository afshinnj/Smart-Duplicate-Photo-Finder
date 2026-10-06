"""Side-by-side comparison dialog for two images.

Shows both files at a matching zoom level together with the per-method scores
produced by :class:`~similarity.similarity_engine.SimilarityEngine`, so the user
can see *why* two files were flagged as duplicates.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.constants import rate_similarity
from ...i18n import tr
from ..widgets.group_card import rating_label


class ZoomableImage(QWidget):
    """A preview that scales with the current zoom factor."""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._zoom = 1.0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._title = QLabel(title, self)
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setObjectName("PageSubtitle")
        self._name = QLabel("", self)
        self._name.setAlignment(Qt.AlignCenter)
        self._name.setObjectName("DimLabel")
        self._name.setWordWrap(True)
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setMinimumSize(320, 240)
        self._label.setObjectName("ImagePlaceholder")
        layout.addWidget(self._title)
        layout.addWidget(self._label, stretch=1)
        layout.addWidget(self._name)

    def set_image(self, path: str) -> None:
        pixmap = QPixmap(path)
        self._pixmap = pixmap if not pixmap.isNull() else None
        self._name.setText(path)
        self._name.setToolTip(path)
        self._render()

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(0.1, min(4.0, zoom))
        self._render()

    def fit(self) -> None:
        self._zoom = 1.0
        self._render()

    def _render(self) -> None:
        if self._pixmap is None:
            self._label.setText(tr("results_empty"))
            return
        available = self._label.size()
        if available.width() < 32 or available.height() < 32:
            available = self._label.minimumSize()
        scaled = self._pixmap.scaled(
            int(max(32, available.width() * self._zoom)),
            int(max(32, available.height() * self._zoom)),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self._label.setPixmap(scaled)


class CompareDialog(QDialog):
    """Modal comparison of two image records."""

    def __init__(self, record_a, record_b, similarity_engine, parent=None) -> None:
        super().__init__(parent)
        self._record_a = record_a
        self._record_b = record_b
        self._engine = similarity_engine
        self._zoom = 1.0
        self.setWindowTitle(tr("compare_title"))
        self.resize(960, 640)
        self._build()
        self._load_images()
        self._load_scores()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        self._score_label = QLabel("", self)
        self._score_label.setObjectName("PageTitle")
        header.addWidget(self._score_label)
        header.addStretch()
        self._rating_label = QLabel("", self)
        self._rating_label.setObjectName("PageSubtitle")
        header.addWidget(self._rating_label)
        layout.addLayout(header)

        previews = QHBoxLayout()
        previews.setSpacing(12)
        self._preview_a = ZoomableImage(tr("compare_image_a"), self)
        self._preview_b = ZoomableImage(tr("compare_image_b"), self)
        previews.addWidget(self._preview_a, stretch=1)
        previews.addWidget(self._preview_b, stretch=1)
        layout.addLayout(previews, stretch=1)

        layout.addWidget(self._build_controls())
        layout.addWidget(self._build_scores())

        buttons = QHBoxLayout()
        buttons.addStretch()
        self._btn_close = QPushButton(tr("dialog_close"), self)
        self._btn_close.clicked.connect(self.accept)
        buttons.addWidget(self._btn_close)
        layout.addLayout(buttons)

    def _build_controls(self) -> QWidget:
        frame = QWidget(self)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()

        self._btn_zoom_out = QPushButton("−", frame)
        self._btn_zoom_out.setObjectName("SecondaryButton")
        self._btn_zoom_out.setFixedWidth(36)
        self._btn_zoom_out.setToolTip(tr("compare_zoom_out"))
        self._btn_zoom_in = QPushButton("+", frame)
        self._btn_zoom_in.setObjectName("SecondaryButton")
        self._btn_zoom_in.setFixedWidth(36)
        self._btn_zoom_in.setToolTip(tr("compare_zoom_in"))
        self._btn_fit = QPushButton(tr("compare_fit"), frame)
        self._btn_fit.setObjectName("SecondaryButton")

        self._btn_zoom_in.clicked.connect(lambda: self._set_zoom(self._zoom * 1.25))
        self._btn_zoom_out.clicked.connect(lambda: self._set_zoom(self._zoom / 1.25))
        self._btn_fit.clicked.connect(lambda: self._set_zoom(1.0))

        layout.addWidget(self._btn_zoom_out)
        layout.addWidget(self._btn_zoom_in)
        layout.addWidget(self._btn_fit)
        layout.addStretch()
        return frame

    def _build_scores(self) -> QGroupBox:
        box = QGroupBox(tr("results_similarity"), self)
        layout = QVBoxLayout(box)
        self._score_table = QTableWidget(0, 2, box)
        self._score_table.setHorizontalHeaderLabels([tr("results_similarity"), ""])
        self._score_table.verticalHeader().setVisible(False)
        self._score_table.horizontalHeader().setStretchLastSection(True)
        self._score_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._score_table.setMaximumHeight(180)
        layout.addWidget(self._score_table)
        return box

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _load_images(self) -> None:
        self._preview_a.set_image(self._record_a.path)
        self._preview_b.set_image(self._record_b.path)

    def _load_scores(self) -> None:
        try:
            result = self._engine.compare(self._record_a, self._record_b)
        except Exception:
            result = None

        if result is None:
            self._score_label.setText(tr("results_similarity"))
            return

        self._score_label.setText(f"{result.score:.1f}%")
        self._rating_label.setText(rating_label(rate_similarity(result.score)))

        scores = dict(result.method_scores)
        if result.matched_keypoints is not None:
            scores[tr("results_compare")] = f"{result.matched_keypoints}"
        self._score_table.setRowCount(len(scores))
        for row, (method, value) in enumerate(scores.items()):
            self._score_table.setItem(row, 0, QTableWidgetItem(str(method)))
            text = f"{value:.1f}" if isinstance(value, (int, float)) else str(value)
            self._score_table.setItem(row, 1, QTableWidgetItem(text))

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def _set_zoom(self, zoom: float) -> None:
        self._zoom = max(0.1, min(4.0, zoom))
        self._preview_a.set_zoom(self._zoom)
        self._preview_b.set_zoom(self._zoom)

    # ------------------------------------------------------------------
    # Retranslation
    # ------------------------------------------------------------------

    def retranslate(self) -> None:
        self.setWindowTitle(tr("compare_title"))
        self._preview_a._title.setText(tr("compare_image_a"))
        self._preview_b._title.setText(tr("compare_image_b"))
        self._btn_zoom_in.setToolTip(tr("compare_zoom_in"))
        self._btn_zoom_out.setToolTip(tr("compare_zoom_out"))
        self._btn_fit.setText(tr("compare_fit"))
        self._btn_close.setText(tr("dialog_close"))
