"""Application style sheets.

Two themes are provided: a dark theme (default, matches the Persian-first
design) and a light theme. Everything is QSS so widgets stay themeable without
touching palette objects. Colour variables are inlined per block because QSS has
no notion of variables.

The palettes and radii follow the Windows 11 Fluent design language: Mica-like
neutral backgrounds, an ``#0078D4`` system accent, 8px rounded cards and
controls, 4px input fields, thin pill scrollbars and a navigation pane whose
selected item carries a small accent pill.
"""

from __future__ import annotations

from ..core.config import Theme

# ---------------------------------------------------------------------------
# Colour palettes
# ---------------------------------------------------------------------------

# Windows 11 dark (Mica): neutral charcoal base, layered surfaces, a brightened
# accent for text/indicators so they stay legible on the dark base.
_DARK = {
    "bg": "#1F1F1F",
    "bg_alt": "#1A1A1A",
    "surface": "#2A2A2A",
    "surface_hover": "#383838",
    "surface_pressed": "#424242",
    "border": "#383838",
    "input_border": "#4A4A4A",
    "input_border_hover": "#606060",
    "text": "#FFFFFF",
    "text_dim": "#C5C5C5",
    "placeholder": "#8A8A8A",
    "accent": "#0078D4",
    "accent_hover": "#1A86D9",
    "accent_pressed": "#0067C0",
    "accent_bright": "#4CC2FF",
    "accent_text": "#FFFFFF",
    "success": "#4ADE80",
    "warning": "#F5B142",
    "danger": "#C42B1C",
    "danger_hover": "#A92017",
    "scrollbar": "#3A3A3A",
    "scrollbar_hover": "#525252",
    "thumb_bg": "#232323",
}

# Windows 11 light (Mica): near-white canvas, white cards with hairline strokes,
# the saturated accent for filled controls and a deepened accent for text.
_LIGHT = {
    "bg": "#F3F3F3",
    "bg_alt": "#ECECEC",
    "surface": "#FFFFFF",
    "surface_hover": "#EDEDED",
    "surface_pressed": "#E0E0E0",
    "border": "#E5E5E5",
    "input_border": "#C9C9C9",
    "input_border_hover": "#A6A6A6",
    "text": "#202020",
    "text_dim": "#616161",
    "placeholder": "#8A8A8A",
    "accent": "#0078D4",
    "accent_hover": "#0067C0",
    "accent_pressed": "#005A9E",
    "accent_bright": "#0067C0",
    "accent_text": "#FFFFFF",
    "success": "#107C10",
    "warning": "#9A6500",
    "danger": "#C42B1C",
    "danger_hover": "#A92017",
    "scrollbar": "#C9C9C9",
    "scrollbar_hover": "#A6A6A6",
    "thumb_bg": "#F0F0F0",
}

QSS_TEMPLATE = """
* {{
    font-family: "Segoe UI Variable", "Segoe UI", "Vazirmatn", "Tahoma", sans-serif;
    font-size: 13px;
}}

QWidget {{
    background-color: {bg};
    color: {text};
}}

/* ------------------------------------------------------------------ */
/* Navigation pane (Windows 11 NavigationView)                        */
/* ------------------------------------------------------------------ */
QFrame#Sidebar {{
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {bg_alt}, stop:1 {bg});
    {sidebar_border}: 1px solid {border};
}}
QFrame#SidebarSeparator {{
    background-color: {border};
    max-height: 1px;
    border: none;
}}
QLabel#BrandIcon {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {accent_hover}, stop:1 {accent_pressed});
    border-radius: 8px;
    color: {accent_text};
    font-size: 17px;
    font-weight: 700;
}}

QPushButton#NavButton {{
    text-align: {nav_text_align};
    padding: 10px 14px;
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
QPushButton#NavButton:pressed {{
    background-color: {surface_pressed};
}}
QPushButton#NavButton:checked {{
    color: {text};
    background-color: {surface_hover};
    font-weight: 600;
    {nav_indicator}: 3px solid {accent_bright};
}}

/* ------------------------------------------------------------------ */
/* Headings                                                            */
/* ------------------------------------------------------------------ */
QLabel#PageTitle {{
    font-size: 22px;
    font-weight: 600;
    color: {text};
}}
QLabel#PageSubtitle {{
    color: {text_dim};
}}
QLabel#DimLabel {{
    color: {text_dim};
}}
QLabel#EmptyState {{
    color: {placeholder};
    font-size: 15px;
    font-weight: 600;
    padding: 32px;
}}

/* ------------------------------------------------------------------ */
/* Cards                                                               */
/* ------------------------------------------------------------------ */
QFrame#Card {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 8px;
}}
QFrame#Card:hover {{
    border-color: {input_border_hover};
}}
QFrame#StatCard {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 8px;
}}
QLabel#StatValue {{
    font-size: 26px;
    font-weight: 700;
}}
QLabel#StatTitle {{
    color: {text_dim};
    font-size: 12px;
}}

/* ------------------------------------------------------------------ */
/* Buttons                                                             */
/* ------------------------------------------------------------------ */
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
QPushButton:pressed {{
    background-color: {accent_pressed};
}}
QPushButton:disabled {{
    background-color: {surface_hover};
    color: {placeholder};
}}
QPushButton:focus {{
    border: 2px solid {accent_bright};
}}
QPushButton#SecondaryButton {{
    background-color: transparent;
    color: {text};
    border: 1px solid {input_border};
}}
QPushButton#SecondaryButton:hover {{
    background-color: {surface_hover};
    border-color: {input_border_hover};
}}
QPushButton#SecondaryButton:pressed {{
    background-color: {surface_pressed};
}}
QPushButton#SecondaryButton:disabled {{
    background-color: transparent;
    color: {placeholder};
}}
QPushButton#IconButton {{
    background-color: transparent;
    color: {text};
    border: 1px solid {input_border};
    border-radius: 6px;
    padding: 0px;
}}
QPushButton#IconButton:hover {{
    background-color: {surface_hover};
    border-color: {input_border_hover};
}}
QPushButton#IconButton:disabled {{
    color: {placeholder};
    background-color: transparent;
}}
QPushButton#DangerButton {{
    background-color: {danger};
    color: #ffffff;
}}
QPushButton#DangerButton:hover {{
    background-color: {danger_hover};
}}

/* ------------------------------------------------------------------ */
/* Inputs (4px radius, 2px accent focus ring)                          */
/* ------------------------------------------------------------------ */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {surface};
    color: {text};
    border: 1px solid {input_border};
    border-radius: 4px;
    padding: 6px 10px;
    min-height: 22px;
    selection-background-color: {accent};
    selection-color: {accent_text};
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    border: 1px solid {input_border_hover};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 2px solid {accent};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    background-color: {bg_alt};
    color: {placeholder};
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
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: transparent;
    border: none;
    width: 18px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {text_dim};
    width: 0px;
    height: 0px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {text_dim};
    width: 0px;
    height: 0px;
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
    border-radius: 6px;
    outline: none;
    padding: 4px;
}}

/* ------------------------------------------------------------------ */
/* Lists                                                               */
/* ------------------------------------------------------------------ */
QListWidget {{
    background-color: {bg_alt};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    outline: none;
}}
QListWidget::item {{
    padding: 8px;
    border-radius: 4px;
}}
QListWidget::item:hover {{
    background-color: {surface_hover};
}}
QListWidget::item:selected {{
    background-color: {accent};
    color: {accent_text};
}}

/* ------------------------------------------------------------------ */
/* Tables (gridlines hidden, Win11 data grid look)                     */
/* ------------------------------------------------------------------ */
QTableWidget, QTableView {{
    background-color: {surface};
    alternate-background-color: {bg_alt};
    color: {text};
    gridline-color: transparent;
    border: 1px solid {border};
    border-radius: 8px;
    outline: none;
}}
QTableWidget::item, QTableView::item {{
    padding: 6px 10px;
    border: none;
}}
QTableWidget::item:hover, QTableView::item:hover {{
    background-color: {surface_hover};
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {accent};
    color: {accent_text};
}}
QHeaderView::section {{
    background-color: transparent;
    color: {text_dim};
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid {border};
    font-weight: 600;
}}
QTableCornerButton::section {{
    background-color: transparent;
    border: none;
    border-bottom: 1px solid {border};
}}

/* ------------------------------------------------------------------ */
/* Progress (slim pill bar)                                            */
/* ------------------------------------------------------------------ */
QProgressBar {{
    background-color: {surface_pressed};
    border: none;
    border-radius: 4px;
    text-align: center;
    color: {text};
    min-height: 8px;
    max-height: 8px;
}}
QProgressBar::chunk {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {accent}, stop:1 {accent_bright});
    border-radius: 4px;
}}

/* ------------------------------------------------------------------ */
/* Scroll bars (thin overlaid pills)                                   */
/* ------------------------------------------------------------------ */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background-color: {scrollbar};
    border-radius: 4px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{
    background-color: {scrollbar_hover};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    background: none;
    border: none;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background-color: {scrollbar};
    border-radius: 4px;
    min-width: 32px;
}}
QScrollBar::handle:horizontal:hover {{
    background-color: {scrollbar_hover};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
    background: none;
    border: none;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}
QScrollBar#TileScroll:horizontal {{
    height: 6px;
}}

/* ------------------------------------------------------------------ */
/* Check boxes and radio buttons                                       */
/* ------------------------------------------------------------------ */
QCheckBox, QRadioButton {{
    color: {text};
    spacing: 8px;
    min-height: 20px;
}}
QCheckBox:disabled, QRadioButton:disabled {{
    color: {placeholder};
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

/* ------------------------------------------------------------------ */
/* Group boxes rendered as cards                                       */
/* ------------------------------------------------------------------ */
QGroupBox {{
    background-color: {surface};
    border: 1px solid {border};
    border-radius: 8px;
    margin-top: 16px;
    padding-top: 14px;
    color: {text_dim};
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top {title_side};
    {title_side}: 12px;
    padding: 0 6px;
    background-color: {surface};
}}

/* ------------------------------------------------------------------ */
/* Tabs                                                                */
/* ------------------------------------------------------------------ */
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
    color: {accent_bright};
    border-bottom: 2px solid {accent_bright};
}}

/* ------------------------------------------------------------------ */
/* Menus (rounded, Win11 flyout look)                                  */
/* ------------------------------------------------------------------ */
QMenuBar {{
    background-color: {bg_alt};
    color: {text_dim};
    border-bottom: 1px solid {border};
    padding: 2px 4px;
}}
QMenuBar::item {{
    padding: 6px 12px;
    border-radius: 6px;
    background: transparent;
}}
QMenuBar::item:selected {{
    background-color: {surface_hover};
    color: {text};
}}
QMenu {{
    background-color: {surface};
    color: {text};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 8px 24px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background-color: {accent};
    color: {accent_text};
}}
QMenu::separator {{
    height: 1px;
    background-color: {border};
    margin: 4px 8px;
}}

/* ------------------------------------------------------------------ */
/* Status bar and splitters                                            */
/* ------------------------------------------------------------------ */
QStatusBar {{
    background-color: {bg_alt};
    color: {text_dim};
    border-top: 1px solid {border};
}}
QStatusBar::item {{
    border: none;
}}
QSplitter::handle {{
    background-color: {border};
}}

/* ------------------------------------------------------------------ */
/* Tooltips and dialogs                                                */
/* ------------------------------------------------------------------ */
QToolTip {{
    background-color: {surface};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 6px 10px;
}}
QDialog {{
    background-color: {bg};
}}

QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget {{
    background: transparent;
}}

/* ------------------------------------------------------------------ */
/* Result tiles                                                        */
/* ------------------------------------------------------------------ */
QLabel#ThumbnailPlaceholder {{
    background-color: {thumb_bg};
    border-radius: 6px;
    color: {placeholder};
}}
QLabel#BadgeExact {{
    background-color: {success};
    color: #ffffff;
    padding: 2px 10px;
    border-radius: 9px;
    font-weight: 700;
}}
QLabel#BadgeSimilar {{
    background-color: {accent};
    color: #ffffff;
    padding: 2px 10px;
    border-radius: 9px;
    font-weight: 700;
}}
QLabel#KeepBadge {{
    color: {success};
    font-weight: 700;
    padding: 2px 6px;
}}
QLabel#ImagePlaceholder {{
    background-color: {thumb_bg};
    border-radius: 8px;
}}
"""


def style_sheet(theme: Theme, rtl: bool = True) -> str:
    """Render the QSS template with the palette of ``theme``.

    ``rtl`` flips the handful of rules that Qt's stylesheet engine does not
    mirror on its own (sidebar border side, nav button text alignment, the
    selected-nav accent pill and the group box title anchor).
    """
    palette = dict(_LIGHT if theme == Theme.LIGHT else _DARK)
    palette["sidebar_border"] = "border-left" if rtl else "border-right"
    palette["nav_text_align"] = "right" if rtl else "left"
    # The pill sits on the leading edge of the selected nav item.
    palette["nav_indicator"] = "border-right" if rtl else "border-left"
    palette["title_side"] = "right" if rtl else "left"
    return QSS_TEMPLATE.format(**palette)


def palette(theme: Theme) -> dict:
    """Expose the palette dict so custom-painted widgets can match the theme."""
    return dict(_LIGHT if theme == Theme.LIGHT else _DARK)
