"""Full-width application toolbar."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from spancloud.gui.theme import (
    ACCENT_BLUE,
    ACCENT_GREEN,
    BG_ELEVATED,
    BORDER_SUBTLE,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

import importlib.resources as pkg_resources


def _icon_path() -> str:
    try:
        ref = pkg_resources.files("spancloud.gui.assets").joinpath("icon.svg")
        return str(ref)
    except Exception:
        return ""


class AppToolbar(QWidget):
    """Full-width toolbar: logo | breadcrumb | actions."""

    refresh_clicked = Signal()
    settings_clicked = Signal()
    about_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("app-toolbar")
        self.setFixedHeight(52)
        self.setStyleSheet(f"""
            #app-toolbar {{
                background: {BG_ELEVATED};
                border-bottom: 1px solid {BORDER_SUBTLE};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(0)

        # ── Logo block ──────────────────────────────────────────────────
        logo_row = QHBoxLayout()
        logo_row.setSpacing(10)
        logo_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        icon_path = _icon_path()
        if icon_path:
            svg = QSvgWidget(icon_path)
            svg.setFixedSize(28, 28)
            logo_row.addWidget(svg)

        app_name = QLabel("spancloud")
        app_name.setStyleSheet(f"""
            color: {ACCENT_BLUE};
            font-size: 16px;
            font-weight: 700;
            letter-spacing: 0.5px;
        """)
        logo_row.addWidget(app_name)

        layout.addLayout(logo_row)

        # Subtle divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setStyleSheet(f"color: {BORDER_SUBTLE}; margin: 12px 20px;")
        layout.addWidget(div)

        # ── Breadcrumb / title ──────────────────────────────────────────
        self._breadcrumb = QLabel("Overview")
        self._breadcrumb.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: 13px;
            font-weight: 500;
        """)
        layout.addWidget(self._breadcrumb)

        self._subtitle = QLabel()
        self._subtitle.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; padding-left: 12px;")
        layout.addWidget(self._subtitle)

        layout.addStretch()

        # ── Action buttons ──────────────────────────────────────────────
        self._refresh_btn = self._icon_button("⟳", "Refresh")
        self._refresh_btn.clicked.connect(self.refresh_clicked)
        layout.addWidget(self._refresh_btn)

        self._settings_btn = self._icon_button("⚙", "Settings")
        self._settings_btn.clicked.connect(self.settings_clicked)
        layout.addWidget(self._settings_btn)

        self._about_btn = self._icon_button("ℹ", "About")
        self._about_btn.clicked.connect(self.about_clicked)
        layout.addWidget(self._about_btn)

    def _icon_button(self, icon: str, tooltip: str) -> QPushButton:
        btn = QPushButton(icon)
        btn.setToolTip(tooltip)
        btn.setFixedSize(36, 36)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 6px;
                color: {TEXT_SECONDARY};
                font-size: 16px;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,0.07);
                color: {TEXT_PRIMARY};
            }}
        """)
        return btn

    def set_context(self, title: str, subtitle: str = "") -> None:
        self._breadcrumb.setText(title)
        self._subtitle.setText(subtitle)
        self._subtitle.setVisible(bool(subtitle))
