"""A small card that shows one statistic (title on top, big value below)."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class StatCard(QFrame):
    """Frame with a title, a large value and an optional caption line."""

    def __init__(self, title: str = "", value: str = "", caption: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setFrameShape(QFrame.NoFrame)

        self._title_label = QLabel(title, self)
        self._title_label.setObjectName("StatTitle")
        self._title_label.setWordWrap(True)
        self._value_label = QLabel(value, self)
        self._value_label.setObjectName("StatValue")
        self._caption_label = QLabel(caption, self)
        self._caption_label.setObjectName("DimLabel")
        self._caption_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        layout.addWidget(self._title_label)
        layout.addWidget(self._value_label)
        layout.addWidget(self._caption_label)

        self.setMinimumHeight(96)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def set_title(self, title: str) -> None:
        self._title_label.setText(title)

    def set_value(self, value: str) -> None:
        self._value_label.setText(value)

    def set_caption(self, caption: str) -> None:
        self._caption_label.setText(caption)

    def value_label(self) -> QLabel:
        return self._value_label

    def set_alignment(self, alignment: Qt.AlignmentFlag) -> None:
        self._title_label.setAlignment(alignment)
        self._value_label.setAlignment(alignment)
        self._caption_label.setAlignment(alignment)

    def retranslate(self, title: Optional[str] = None, caption: Optional[str] = None) -> None:
        if title is not None:
            self.set_title(title)
        if caption is not None:
            self.set_caption(caption)
