"""Application style sheets.

Two themes are provided: a dark theme (default, matches the Persian-first
design) and a light theme. Everything is QSS so widgets stay themeable without
touching palette objects. Colour variables are inlined per block because QSS has
no notion of variables.
"""

from __future__ import annotations

from ..core.config import Theme

# ---------------------------------------------------------------------------
# Colour palettes
# ---------------------------------------------------------------------------

_DARK = {
    "bg": "#101418",
    "bg_alt": "#171c22",
    "surface": "#1d232b",
    "surface_hover": "#242c36",
    "border": "#2c3540",
    "input_border": "#41505f",
    "text": "#e8ecf1",
    "text_dim": "#9aa6b2",
    "placeholder": "#7d8894",
    "accent": "#3b82f6",
    "accent_hover": "#2f6fd0",
    "accent_text": "#ffffff",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "danger": "#ef4444",
    "danger_hover": "#c8352f",
    "scrollbar": "#333d49",
}

_LIGHT = {
    "bg": "#f4f6f9",
    "bg_alt": "#eaeef3",
    "surface": "#ffffff",
    "surface_hover": "#f1f5fa",
    "border": "#d5dde6",
    "input_border": "#aebccb",
    "text": "#1b2430",
    "text_dim": "#5b6a7a",
    "placeholder": "#8a97a6",
    "accent": "#2563eb",
    "accent_hover": "#1d4fc4",
    "accent_text": "#ffffff",
    "success": "#15803d",
    "warning": "#b45309",
    "danger": "#dc2626",
    "danger_hover": "#b41c1c",
    "scrollbar": "#c3cdd9",
}

QSS_TEMPLATE = """
* {{
    font-family: "Segoe UI", "Vazirmatn", "Tahoma", sans-serif;
    font-size: 13px;
}}

QWidget {{
    background-color: {bg};
    color: {text};
}}

QFrame#Sidebar {{
    background-color: {bg_alt};
    {sidebar_border}: 1px solid {border};
}}

QPushButton#NavButton {{
    text-align: {nav_text_align};
    padding: 10px 16px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: {text_dim};
    font-size: 14px;
}}
QPushButton#NavButton:hover {{
    color: {text};
    background-color: {surface_hover};
}}
QPushButton#NavButton:checked {{
    color: {accent};
    background-color: {surface};
    font-weight: 600;
}}

QLabel#PageTitle {{
    font-size: 20px;
    font-weight: 700;
    color: {text};
}}
QLabel#PageSubtitle {{
    color: {text_dim};
}}
QLabel#DimLabel {{
    color: {text_dim};
}}

QFrame#Card {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 12px;
}}
QFrame#StatCard {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 12px;
}}
QLabel#StatValue {{
    font-size: 24px;
    font-weight: 700;
}}
QLabel#StatTitle {{
    color: {text_dim};
    font-size: 12px;
}}

QPushButton {{
    background-color: {accent};
    color: {accent_text};
    border: none;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {accent_hover};
}}
QPushButton:disabled {{
    background-color: {border};
    color: {text_dim};
}}
QPushButton#SecondaryButton {{
    background-color: {surface};
    color: {text};
    border: 1px solid {border};
}}
QPushButton#SecondaryButton:hover {{
    background-color: {surface_hover};
}}
QPushButton#DangerButton {{
    background-color: {danger};
    color: #ffffff;
}}
QPushButton#DangerButton:hover {{
    background-color: {danger_hover};
}}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {surface};
    color: {text};
    border: 1px solid {input_border};
    border-radius: 8px;
    padding: 6px 10px;
    min-height: 22px;
    selection-background-color: {accent};
    selection-color: {accent_text};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {accent};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    background-color: {bg_alt};
    color: {text_dim};
    border: 1px solid {border};
}}
/* The embedded line edit of a spin box must not double the padding/height. */
QLineEdit#qt_spinbox_lineedit {{
    min-height: 0px;
    padding: 0px;
    border: none;
    background: transparent;
    selection-background-color: {accent};
    selection-color: {accent_text};
}}
QComboBox::drop-down {{
    border: none;
    border-left: 1px solid {border};
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {text_dim};
    width: 0px;
    height: 0px;
}}
QComboBox:hover::down-arrow {{
    border-top-color: {text};
}}
QComboBox QAbstractItemView {{
    background-color: {surface};
    color: {text};
    selection-background-color: {accent};
    selection-color: {accent_text};
    border: 1px solid {input_border};
    outline: none;
    padding: 4px;
}}

QListWidget {{
    background-color: {bg_alt};
    border: 1px solid {border};
    border-radius: 8px;
    outline: none;
}}
QListWidget::item {{
    padding: 8px;
    border-radius: 6px;
}}
QListWidget::item:hover {{
    background-color: {surface_hover};
}}
QListWidget::item:selected {{
    background-color: {accent};
    color: {accent_text};
}}

QTableWidget, QTableView {{
    background-color: {surface};
    alternate-background-color: {bg_alt};
    color: {text};
    gridline-color: {border};
    border: 1px solid {border};
    border-radius: 8px;
}}
QHeaderView::section {{
    background-color: {bg_alt};
    color: {text_dim};
    padding: 8px;
    border: none;
    border-bottom: 1px solid {border};
}}
QTableWidget::item {{
    padding: 6px 8px;
}}

QProgressBar {{
    background-color: {bg_alt};
    border: 1px solid {border};
    border-radius: 8px;
    text-align: center;
    color: {text};
    min-height: 22px;
}}
QProgressBar::chunk {{
    background-color: {accent};
    border-radius: 7px;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background-color: {scrollbar};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background-color: {scrollbar};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QCheckBox, QRadioButton {{
    color: {text};
    spacing: 8px;
    min-height: 20px;
}}
QCheckBox:disabled, QRadioButton:disabled {{
    color: {text_dim};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {input_border};
    border-radius: 4px;
    background-color: {surface};
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {accent};
}}
QRadioButton::indicator {{
    border-radius: 9px;
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {accent};
    border-color: {accent};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background-color: {bg_alt};
    border-color: {border};
}}

QGroupBox {{
    background-color: {bg_alt};
    border: 1px solid {border};
    border-radius: 10px;
    margin-top: 14px;
    padding-top: 12px;
    color: {text_dim};
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top {title_side};
    {title_side}: 12px;
    padding: 0 6px;
    background-color: {bg_alt};
}}

QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 8px;
    background-color: {surface};
}}
QTabBar::tab {{
    padding: 8px 16px;
    color: {text_dim};
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{
    color: {accent};
    border-bottom: 2px solid {accent};
}}

QStatusBar {{
    background-color: {bg_alt};
    color: {text_dim};
    border-top: 1px solid {border};
}}

QSplitter::handle {{
    background-color: {border};
}}

QToolTip {{
    background-color: {surface};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 4px 8px;
}}

QScrollBar#TileScroll:horizontal {{
    height: 8px;
}}

QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget {{
    background: transparent;
}}
"""


def style_sheet(theme: Theme, rtl: bool = True) -> str:
    """Render the QSS template with the palette of ``theme``.

    ``rtl`` flips the handful of rules that Qt's stylesheet engine does not
    mirror on its own (sidebar border side, nav button text alignment and the
    group box title anchor).
    """
    palette = dict(_LIGHT if theme == Theme.LIGHT else _DARK)
    palette["sidebar_border"] = "border-left" if rtl else "border-right"
    palette["nav_text_align"] = "right" if rtl else "left"
    palette["title_side"] = "right" if rtl else "left"
    return QSS_TEMPLATE.format(**palette)


def palette(theme: Theme) -> dict:
    """Expose the palette dict so custom-painted widgets can match the theme."""
    return dict(_LIGHT if theme == Theme.LIGHT else _DARK)
