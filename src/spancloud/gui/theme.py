"""Dark theme palette and stylesheet for the Spancloud GUI."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QWidget


# ---------------------------------------------------------------------------
# Colour tokens
# ---------------------------------------------------------------------------
BG_BASE        = "#1a1b26"   # main window background
BG_SURFACE     = "#1f2335"   # cards, panels
BG_ELEVATED    = "#24283b"   # sidebar, header
BG_HIGHLIGHT   = "#292e42"   # hover, selection
BORDER_SUBTLE  = "#3b4261"   # subtle separators
BORDER_ACCENT  = "#7aa2f7"   # focused / active border

TEXT_PRIMARY   = "#c0caf5"
TEXT_SECONDARY = "#a9b1d6"
TEXT_MUTED     = "#565f89"
TEXT_HEADING   = "#7aa2f7"   # blue headings

ACCENT_BLUE    = "#7aa2f7"
ACCENT_GREEN   = "#9ece6a"
ACCENT_YELLOW  = "#e0af68"
ACCENT_RED     = "#f7768e"
ACCENT_CYAN    = "#7dcfff"
ACCENT_PURPLE  = "#bb9af7"

STATUS_OK      = ACCENT_GREEN
STATUS_ERROR   = ACCENT_RED
STATUS_WARN    = ACCENT_YELLOW
STATUS_MUTED   = TEXT_MUTED


# ---------------------------------------------------------------------------
# QPalette
# ---------------------------------------------------------------------------
def _palette() -> QPalette:
    p = QPalette()
    bg    = QColor(BG_BASE)
    surf  = QColor(BG_SURFACE)
    elev  = QColor(BG_ELEVATED)
    hi    = QColor(BG_HIGHLIGHT)
    txt   = QColor(TEXT_PRIMARY)
    dim   = QColor(TEXT_SECONDARY)
    acc   = QColor(ACCENT_BLUE)

    p.setColor(QPalette.ColorRole.Window,          bg)
    p.setColor(QPalette.ColorRole.WindowText,      txt)
    p.setColor(QPalette.ColorRole.Base,            surf)
    p.setColor(QPalette.ColorRole.AlternateBase,   elev)
    p.setColor(QPalette.ColorRole.Text,            txt)
    p.setColor(QPalette.ColorRole.BrightText,      QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.ButtonText,      txt)
    p.setColor(QPalette.ColorRole.Button,          elev)
    p.setColor(QPalette.ColorRole.Highlight,       acc)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.Link,            acc)
    p.setColor(QPalette.ColorRole.PlaceholderText, dim)
    p.setColor(QPalette.ColorRole.ToolTipBase,     elev)
    p.setColor(QPalette.ColorRole.ToolTipText,     txt)
    return p

DARK_PALETTE = _palette()


# ---------------------------------------------------------------------------
# QSS stylesheet
# ---------------------------------------------------------------------------
STYLESHEET = f"""
/* ── Base ─────────────────────────────────────────────────────────────── */
QMainWindow, QDialog, QWidget {{
    background: {BG_BASE};
    color: {TEXT_PRIMARY};
    font-family: "Inter", "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 13px;
}}

/* ── Divider line ──────────────────────────────────────────────────────── */
QFrame#divider {{
    background: {BORDER_SUBTLE};
    max-width: 1px;
}}

/* ── Sidebar ───────────────────────────────────────────────────────────── */
#sidebar {{
    background: {BG_ELEVATED};
    min-width: 220px;
    max-width: 220px;
}}

#sidebar-logo {{
    color: {ACCENT_BLUE};
    font-size: 18px;
    font-weight: 700;
    padding: 16px 20px 8px 20px;
    letter-spacing: 1px;
}}

#sidebar-section {{
    color: {TEXT_MUTED};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 12px 20px 4px 20px;
}}

QPushButton.sidebar-item {{
    background: transparent;
    border: none;
    border-radius: 6px;
    color: {TEXT_SECONDARY};
    font-size: 13px;
    padding: 8px 12px;
    text-align: left;
    margin: 1px 8px;
}}
QPushButton.sidebar-item:hover {{
    background: {BG_HIGHLIGHT};
    color: {TEXT_PRIMARY};
}}
QPushButton.sidebar-item[active="true"] {{
    background: {BG_HIGHLIGHT};
    color: {ACCENT_BLUE};
    font-weight: 600;
}}

/* status dot colours via object name */
QLabel#dot-authenticated {{ color: {STATUS_OK}; }}
QLabel#dot-error         {{ color: {STATUS_ERROR}; }}
QLabel#dot-unauthenticated {{ color: {STATUS_MUTED}; }}

/* ── Content area ──────────────────────────────────────────────────────── */
#content-header {{
    background: {BG_ELEVATED};
    border-bottom: 1px solid {BORDER_SUBTLE};
    padding: 12px 24px;
    min-height: 52px;
    max-height: 52px;
}}

#content-title {{
    color: {TEXT_HEADING};
    font-size: 16px;
    font-weight: 700;
}}

#content-subtitle {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}

/* ── Tabs ──────────────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: none;
    background: {BG_BASE};
}}

QTabBar::tab {{
    background: {BG_ELEVATED};
    color: {TEXT_SECONDARY};
    border: none;
    padding: 8px 20px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-size: 12px;
}}
QTabBar::tab:selected {{
    background: {BG_BASE};
    color: {TEXT_PRIMARY};
    border-top: 2px solid {ACCENT_BLUE};
}}
QTabBar::tab:hover:!selected {{
    background: {BG_HIGHLIGHT};
}}

/* ── Cards (overview) ──────────────────────────────────────────────────── */
QFrame.provider-card {{
    background: {BG_SURFACE};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 8px;
}}
QFrame.provider-card:hover {{
    border: 1px solid {ACCENT_BLUE};
}}
QFrame.provider-card[status="authenticated"] {{
    border-left: 3px solid {STATUS_OK};
}}
QFrame.provider-card[status="error"] {{
    border-left: 3px solid {STATUS_ERROR};
}}
QFrame.provider-card[status="unauthenticated"] {{
    border-left: 3px solid {STATUS_MUTED};
}}

#card-name {{
    color: {TEXT_PRIMARY};
    font-weight: 600;
    font-size: 14px;
}}
#card-count {{
    color: {ACCENT_CYAN};
    font-size: 22px;
    font-weight: 700;
}}
#card-count-label {{
    color: {TEXT_MUTED};
    font-size: 11px;
}}
#card-status {{
    font-size: 11px;
    font-weight: 600;
}}
#card-status[status="authenticated"]   {{ color: {STATUS_OK}; }}
#card-status[status="error"]           {{ color: {STATUS_ERROR}; }}
#card-status[status="unauthenticated"] {{ color: {STATUS_MUTED}; }}

/* ── Resource table ────────────────────────────────────────────────────── */
QTreeWidget {{
    background: {BG_SURFACE};
    border: none;
    alternate-background-color: {BG_ELEVATED};
    gridline-color: {BORDER_SUBTLE};
    outline: none;
}}
QTreeWidget::item {{
    padding: 6px 4px;
    border-bottom: 1px solid {BORDER_SUBTLE};
}}
QTreeWidget::item:selected {{
    background: {BG_HIGHLIGHT};
    color: {TEXT_PRIMARY};
}}
QTreeWidget::item:hover {{
    background: {BG_HIGHLIGHT};
}}
QHeaderView::section {{
    background: {BG_ELEVATED};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER_SUBTLE};
    border-right: 1px solid {BORDER_SUBTLE};
    padding: 6px 8px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}

/* ── Detail panel ──────────────────────────────────────────────────────── */
#detail-panel {{
    background: {BG_ELEVATED};
    border-top: 1px solid {ACCENT_BLUE};
    padding: 12px 20px;
}}
#detail-title {{
    color: {TEXT_HEADING};
    font-size: 13px;
    font-weight: 600;
}}
#detail-key   {{ color: {TEXT_MUTED};    font-size: 12px; }}
#detail-value {{ color: {TEXT_PRIMARY};  font-size: 12px; }}

/* ── Analysis panel ────────────────────────────────────────────────────── */
#analysis-panel {{
    background: {BG_SURFACE};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 8px;
    padding: 16px;
}}
#analysis-title {{
    color: {TEXT_HEADING};
    font-size: 14px;
    font-weight: 600;
    padding-bottom: 8px;
}}

/* ── Sidebar analysis items ─────────────────────────────────────────────── */
QPushButton.analysis-item {{
    background: transparent;
    border: none;
    border-radius: 6px;
    color: {TEXT_SECONDARY};
    font-size: 12px;
    padding: 6px 12px;
    text-align: left;
    margin: 1px 8px;
}}
QPushButton.analysis-item:hover {{
    background: {BG_HIGHLIGHT};
    color: {TEXT_PRIMARY};
}}
QPushButton.analysis-item[active="true"] {{
    background: rgba(122,162,247,0.15);
    color: {ACCENT_BLUE};
}}

/* ── Search bar ─────────────────────────────────────────────────────────── */
QLineEdit {{
    background: {BG_ELEVATED};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 6px;
    color: {TEXT_PRIMARY};
    padding: 7px 12px;
    font-size: 13px;
    selection-background-color: {ACCENT_BLUE};
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT_BLUE};
}}
QLineEdit::placeholder {{
    color: {TEXT_MUTED};
}}

/* ── Status bar ─────────────────────────────────────────────────────────── */
QStatusBar {{
    background: {BG_ELEVATED};
    border-top: 1px solid {BORDER_SUBTLE};
    color: {TEXT_MUTED};
    font-size: 12px;
    padding: 0 8px;
}}

/* ── Scrollbars ─────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {BG_BASE};
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_SUBTLE};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TEXT_MUTED};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {BG_BASE};
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_SUBTLE};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: {TEXT_MUTED}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Splitter ───────────────────────────────────────────────────────────── */
QSplitter::handle {{
    background: {BORDER_SUBTLE};
}}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical   {{ height: 1px; }}
"""


def apply_stylesheet(widget: QWidget) -> None:
    widget.setStyleSheet(STYLESHEET)
