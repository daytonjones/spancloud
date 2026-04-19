"""Theme system for the Spancloud GUI — multiple named themes with live switching."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget


# ---------------------------------------------------------------------------
# Theme definitions
# ---------------------------------------------------------------------------

THEMES: dict[str, dict[str, str]] = {
    "Tokyo Night": {
        "BG_BASE":        "#1a1b26",
        "BG_SURFACE":     "#1f2335",
        "BG_ELEVATED":    "#24283b",
        "BG_HIGHLIGHT":   "#292e42",
        "BORDER_SUBTLE":  "#3b4261",
        "BORDER_ACCENT":  "#7aa2f7",
        "TEXT_PRIMARY":   "#c0caf5",
        "TEXT_SECONDARY": "#a9b1d6",
        "TEXT_MUTED":     "#565f89",
        "TEXT_HEADING":   "#7aa2f7",
        "ACCENT_BLUE":    "#7aa2f7",
        "ACCENT_GREEN":   "#9ece6a",
        "ACCENT_YELLOW":  "#e0af68",
        "ACCENT_RED":     "#f7768e",
        "ACCENT_CYAN":    "#7dcfff",
        "ACCENT_PURPLE":  "#bb9af7",
    },
    "Dark": {
        "BG_BASE":        "#1e1e1e",
        "BG_SURFACE":     "#252526",
        "BG_ELEVATED":    "#2d2d2d",
        "BG_HIGHLIGHT":   "#37373d",
        "BORDER_SUBTLE":  "#3e3e42",
        "BORDER_ACCENT":  "#569cd6",
        "TEXT_PRIMARY":   "#d4d4d4",
        "TEXT_SECONDARY": "#b8b8b8",
        "TEXT_MUTED":     "#6a6a6a",
        "TEXT_HEADING":   "#569cd6",
        "ACCENT_BLUE":    "#569cd6",
        "ACCENT_GREEN":   "#4ec9b0",
        "ACCENT_YELLOW":  "#dcdcaa",
        "ACCENT_RED":     "#f44747",
        "ACCENT_CYAN":    "#9cdcfe",
        "ACCENT_PURPLE":  "#c586c0",
    },
    "Dracula": {
        "BG_BASE":        "#282a36",
        "BG_SURFACE":     "#21222c",
        "BG_ELEVATED":    "#343746",
        "BG_HIGHLIGHT":   "#44475a",
        "BORDER_SUBTLE":  "#44475a",
        "BORDER_ACCENT":  "#bd93f9",
        "TEXT_PRIMARY":   "#f8f8f2",
        "TEXT_SECONDARY": "#cfcfcf",
        "TEXT_MUTED":     "#6272a4",
        "TEXT_HEADING":   "#bd93f9",
        "ACCENT_BLUE":    "#6272a4",
        "ACCENT_GREEN":   "#50fa7b",
        "ACCENT_YELLOW":  "#f1fa8c",
        "ACCENT_RED":     "#ff5555",
        "ACCENT_CYAN":    "#8be9fd",
        "ACCENT_PURPLE":  "#bd93f9",
    },
    "Solarized Dark": {
        "BG_BASE":        "#002b36",
        "BG_SURFACE":     "#073642",
        "BG_ELEVATED":    "#083f4d",
        "BG_HIGHLIGHT":   "#0d4f5e",
        "BORDER_SUBTLE":  "#1a5566",
        "BORDER_ACCENT":  "#268bd2",
        "TEXT_PRIMARY":   "#839496",
        "TEXT_SECONDARY": "#93a1a1",
        "TEXT_MUTED":     "#586e75",
        "TEXT_HEADING":   "#268bd2",
        "ACCENT_BLUE":    "#268bd2",
        "ACCENT_GREEN":   "#859900",
        "ACCENT_YELLOW":  "#b58900",
        "ACCENT_RED":     "#dc322f",
        "ACCENT_CYAN":    "#2aa198",
        "ACCENT_PURPLE":  "#6c71c4",
    },
    "Light": {
        "BG_BASE":        "#ffffff",
        "BG_SURFACE":     "#f5f5f5",
        "BG_ELEVATED":    "#ebebeb",
        "BG_HIGHLIGHT":   "#dde3ed",
        "BORDER_SUBTLE":  "#c8c8c8",
        "BORDER_ACCENT":  "#0366d6",
        "TEXT_PRIMARY":   "#24292e",
        "TEXT_SECONDARY": "#444d56",
        "TEXT_MUTED":     "#959da5",
        "TEXT_HEADING":   "#0366d6",
        "ACCENT_BLUE":    "#0366d6",
        "ACCENT_GREEN":   "#28a745",
        "ACCENT_YELLOW":  "#b08800",
        "ACCENT_RED":     "#d73a49",
        "ACCENT_CYAN":    "#0598bc",
        "ACCENT_PURPLE":  "#6f42c1",
    },
}

THEME_NAMES = list(THEMES.keys())
DEFAULT_THEME = "Tokyo Night"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def get_active_theme_name() -> str:
    settings = QSettings("spancloud", "spancloud-gui")
    return str(settings.value("theme", DEFAULT_THEME))


def set_active_theme_name(name: str) -> None:
    settings = QSettings("spancloud", "spancloud-gui")
    settings.setValue("theme", name)


def get_tokens(name: str | None = None) -> dict[str, str]:
    if name is None:
        name = get_active_theme_name()
    return THEMES.get(name, THEMES[DEFAULT_THEME])


# ---------------------------------------------------------------------------
# Backwards-compat token accessors (read active theme at call time)
# ---------------------------------------------------------------------------

def _t(key: str) -> str:
    return get_tokens()[key]


# Module-level aliases used by widgets — resolved from active theme at import.
# After a theme switch, call apply_theme() to re-apply; widget inline styles
# that read these at construction time will need a restart (or dialog rebuild).
def _tokens() -> dict[str, str]:
    return get_tokens()


# Provide module-level names for the default theme so existing imports keep working.
_default = THEMES[DEFAULT_THEME]
BG_BASE        = _default["BG_BASE"]
BG_SURFACE     = _default["BG_SURFACE"]
BG_ELEVATED    = _default["BG_ELEVATED"]
BG_HIGHLIGHT   = _default["BG_HIGHLIGHT"]
BORDER_SUBTLE  = _default["BORDER_SUBTLE"]
BORDER_ACCENT  = _default["BORDER_ACCENT"]
TEXT_PRIMARY   = _default["TEXT_PRIMARY"]
TEXT_SECONDARY = _default["TEXT_SECONDARY"]
TEXT_MUTED     = _default["TEXT_MUTED"]
TEXT_HEADING   = _default["TEXT_HEADING"]
ACCENT_BLUE    = _default["ACCENT_BLUE"]
ACCENT_GREEN   = _default["ACCENT_GREEN"]
ACCENT_YELLOW  = _default["ACCENT_YELLOW"]
ACCENT_RED     = _default["ACCENT_RED"]
ACCENT_CYAN    = _default["ACCENT_CYAN"]
ACCENT_PURPLE  = _default["ACCENT_PURPLE"]

STATUS_OK      = _default["ACCENT_GREEN"]
STATUS_ERROR   = _default["ACCENT_RED"]
STATUS_WARN    = _default["ACCENT_YELLOW"]
STATUS_MUTED   = _default["TEXT_MUTED"]


# ---------------------------------------------------------------------------
# Stylesheet generator
# ---------------------------------------------------------------------------

def build_stylesheet(t: dict[str, str]) -> str:
    return f"""
/* ── Base ─────────────────────────────────────────────────────────────── */
QMainWindow, QDialog, QWidget {{
    background: {t["BG_BASE"]};
    color: {t["TEXT_PRIMARY"]};
    font-family: "Inter", "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 13px;
}}

/* ── Divider line ──────────────────────────────────────────────────────── */
QFrame#divider {{
    background: {t["BORDER_SUBTLE"]};
    max-width: 1px;
}}

/* ── Sidebar ───────────────────────────────────────────────────────────── */
#sidebar {{
    background: {t["BG_ELEVATED"]};
    min-width: 220px;
    max-width: 220px;
}}

#sidebar-logo {{
    color: {t["ACCENT_BLUE"]};
    font-size: 18px;
    font-weight: 700;
    padding: 16px 20px 8px 20px;
    letter-spacing: 1px;
}}

#sidebar-section {{
    color: {t["TEXT_MUTED"]};
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
    color: {t["TEXT_SECONDARY"]};
    font-size: 13px;
    padding: 8px 12px;
    text-align: left;
    margin: 1px 8px;
}}
QPushButton.sidebar-item:hover {{
    background: {t["BG_HIGHLIGHT"]};
    color: {t["TEXT_PRIMARY"]};
}}
QPushButton.sidebar-item[active="true"] {{
    background: {t["BG_HIGHLIGHT"]};
    color: {t["ACCENT_BLUE"]};
    font-weight: 600;
}}

/* status dot colours via object name */
QLabel#dot-authenticated   {{ color: {t["ACCENT_GREEN"]}; }}
QLabel#dot-error           {{ color: {t["ACCENT_RED"]}; }}
QLabel#dot-unauthenticated {{ color: {t["TEXT_MUTED"]}; }}

/* ── Content area ──────────────────────────────────────────────────────── */
#content-header {{
    background: {t["BG_ELEVATED"]};
    border-bottom: 1px solid {t["BORDER_SUBTLE"]};
    padding: 12px 24px;
    min-height: 52px;
    max-height: 52px;
}}

#content-title {{
    color: {t["TEXT_HEADING"]};
    font-size: 16px;
    font-weight: 700;
}}

#content-subtitle {{
    color: {t["TEXT_MUTED"]};
    font-size: 12px;
}}

/* ── Tabs ──────────────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: none;
    background: {t["BG_BASE"]};
}}

QTabBar::tab {{
    background: {t["BG_ELEVATED"]};
    color: {t["TEXT_SECONDARY"]};
    border: none;
    padding: 8px 20px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-size: 12px;
}}
QTabBar::tab:selected {{
    background: {t["BG_BASE"]};
    color: {t["TEXT_PRIMARY"]};
    border-top: 2px solid {t["ACCENT_BLUE"]};
}}
QTabBar::tab:hover:!selected {{
    background: {t["BG_HIGHLIGHT"]};
}}

/* ── Cards (overview) ──────────────────────────────────────────────────── */
QFrame.provider-card {{
    background: {t["BG_SURFACE"]};
    border: 1px solid {t["BORDER_SUBTLE"]};
    border-radius: 8px;
}}
QFrame.provider-card:hover {{
    border: 1px solid {t["ACCENT_BLUE"]};
}}
QFrame.provider-card[status="authenticated"] {{
    border-left: 3px solid {t["ACCENT_GREEN"]};
}}
QFrame.provider-card[status="error"] {{
    border-left: 3px solid {t["ACCENT_RED"]};
}}
QFrame.provider-card[status="unauthenticated"] {{
    border-left: 3px solid {t["TEXT_MUTED"]};
}}

#card-name {{
    color: {t["TEXT_PRIMARY"]};
    font-weight: 600;
    font-size: 14px;
}}
#card-count {{
    color: {t["ACCENT_CYAN"]};
    font-size: 22px;
    font-weight: 700;
}}
#card-count-label {{
    color: {t["TEXT_MUTED"]};
    font-size: 11px;
}}
#card-status {{
    font-size: 11px;
    font-weight: 600;
}}
#card-status[status="authenticated"]   {{ color: {t["ACCENT_GREEN"]}; }}
#card-status[status="error"]           {{ color: {t["ACCENT_RED"]}; }}
#card-status[status="unauthenticated"] {{ color: {t["TEXT_MUTED"]}; }}

/* ── Resource table ────────────────────────────────────────────────────── */
QTreeWidget {{
    background: {t["BG_SURFACE"]};
    border: none;
    alternate-background-color: {t["BG_ELEVATED"]};
    gridline-color: {t["BORDER_SUBTLE"]};
    outline: none;
}}
QTreeWidget::item {{
    padding: 6px 4px;
    border-bottom: 1px solid {t["BORDER_SUBTLE"]};
}}
QTreeWidget::item:selected {{
    background: {t["BG_HIGHLIGHT"]};
    color: {t["TEXT_PRIMARY"]};
}}
QTreeWidget::item:hover {{
    background: {t["BG_HIGHLIGHT"]};
}}
QHeaderView::section {{
    background: {t["BG_ELEVATED"]};
    color: {t["TEXT_MUTED"]};
    border: none;
    border-bottom: 1px solid {t["BORDER_SUBTLE"]};
    border-right: 1px solid {t["BORDER_SUBTLE"]};
    padding: 6px 8px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}

/* ── Detail panel ──────────────────────────────────────────────────────── */
#detail-panel {{
    background: {t["BG_ELEVATED"]};
    border-top: 1px solid {t["ACCENT_BLUE"]};
    padding: 12px 20px;
}}
#detail-title {{
    color: {t["TEXT_HEADING"]};
    font-size: 13px;
    font-weight: 600;
}}
#detail-key   {{ color: {t["TEXT_MUTED"]};   font-size: 12px; }}
#detail-value {{ color: {t["TEXT_PRIMARY"]}; font-size: 12px; }}

/* ── Analysis panel ────────────────────────────────────────────────────── */
#analysis-panel {{
    background: {t["BG_SURFACE"]};
    border: 1px solid {t["BORDER_SUBTLE"]};
    border-radius: 8px;
    padding: 16px;
}}
#analysis-title {{
    color: {t["TEXT_HEADING"]};
    font-size: 14px;
    font-weight: 600;
    padding-bottom: 8px;
}}

/* ── Sidebar analysis items ─────────────────────────────────────────────── */
QPushButton.analysis-item {{
    background: transparent;
    border: none;
    border-radius: 6px;
    color: {t["TEXT_SECONDARY"]};
    font-size: 12px;
    padding: 6px 12px;
    text-align: left;
    margin: 1px 8px;
}}
QPushButton.analysis-item:hover {{
    background: {t["BG_HIGHLIGHT"]};
    color: {t["TEXT_PRIMARY"]};
}}
QPushButton.analysis-item[active="true"] {{
    background: {t["BG_HIGHLIGHT"]};
    color: {t["ACCENT_BLUE"]};
}}

/* ── Search bar ─────────────────────────────────────────────────────────── */
QLineEdit {{
    background: {t["BG_ELEVATED"]};
    border: 1px solid {t["BORDER_SUBTLE"]};
    border-radius: 6px;
    color: {t["TEXT_PRIMARY"]};
    padding: 7px 12px;
    font-size: 13px;
    selection-background-color: {t["ACCENT_BLUE"]};
}}
QLineEdit:focus {{
    border: 1px solid {t["ACCENT_BLUE"]};
}}
QLineEdit::placeholder {{
    color: {t["TEXT_MUTED"]};
}}

/* ── Status bar ─────────────────────────────────────────────────────────── */
QStatusBar {{
    background: {t["BG_ELEVATED"]};
    border-top: 1px solid {t["BORDER_SUBTLE"]};
    color: {t["TEXT_MUTED"]};
    font-size: 12px;
    padding: 0 8px;
}}

/* ── Scrollbars ─────────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {t["BG_BASE"]};
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {t["BORDER_SUBTLE"]};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t["TEXT_MUTED"]};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {t["BG_BASE"]};
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: {t["BORDER_SUBTLE"]};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: {t["TEXT_MUTED"]}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── Splitter ───────────────────────────────────────────────────────────── */
QSplitter::handle {{
    background: {t["BORDER_SUBTLE"]};
}}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical   {{ height: 1px; }}
"""


# ---------------------------------------------------------------------------
# QPalette builder
# ---------------------------------------------------------------------------

def build_palette(t: dict[str, str]) -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(t["BG_BASE"]))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(t["TEXT_PRIMARY"]))
    p.setColor(QPalette.ColorRole.Base,            QColor(t["BG_SURFACE"]))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(t["BG_ELEVATED"]))
    p.setColor(QPalette.ColorRole.Text,            QColor(t["TEXT_PRIMARY"]))
    p.setColor(QPalette.ColorRole.BrightText,      QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(t["TEXT_PRIMARY"]))
    p.setColor(QPalette.ColorRole.Button,          QColor(t["BG_ELEVATED"]))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(t["ACCENT_BLUE"]))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.Link,            QColor(t["ACCENT_BLUE"]))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(t["TEXT_SECONDARY"]))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(t["BG_ELEVATED"]))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor(t["TEXT_PRIMARY"]))
    return p


# ---------------------------------------------------------------------------
# Apply helpers
# ---------------------------------------------------------------------------

def apply_stylesheet(widget: QWidget, theme_name: str | None = None) -> None:
    t = get_tokens(theme_name)
    widget.setStyleSheet(build_stylesheet(t))


def apply_theme(window: QWidget, theme_name: str) -> None:
    """Apply theme to the main window and update the application palette."""
    set_active_theme_name(theme_name)
    t = get_tokens(theme_name)
    window.setStyleSheet(build_stylesheet(t))
    app = QApplication.instance()
    if app is not None:
        app.setPalette(build_palette(t))


# Backwards-compat alias used in app.py startup
DARK_PALETTE = build_palette(THEMES[DEFAULT_THEME])
