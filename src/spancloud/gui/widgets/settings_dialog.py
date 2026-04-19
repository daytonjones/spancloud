"""Settings dialog — provider toggles and theme selection."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from spancloud.gui.theme import (
    ACCENT_BLUE,
    BG_ELEVATED,
    BG_SURFACE,
    BORDER_SUBTLE,
    TEXT_MUTED,
    TEXT_PRIMARY,
    THEME_NAMES,
    get_active_theme_name,
)

_STYLE = f"""
    QDialog {{ background: {BG_SURFACE}; }}
    QLabel#dlg-title {{
        color: {ACCENT_BLUE};
        font-size: 14px;
        font-weight: 700;
    }}
    QLabel#section-header {{
        color: {TEXT_MUTED};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 1px;
    }}
    QCheckBox, QRadioButton {{
        color: {TEXT_PRIMARY};
        font-size: 12px;
        spacing: 8px;
        padding: 5px 4px;
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 15px; height: 15px;
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 3px;
        background: {BG_ELEVATED};
    }}
    QRadioButton::indicator {{ border-radius: 8px; }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background: {ACCENT_BLUE};
        border-color: {ACCENT_BLUE};
    }}
    QCheckBox:hover, QRadioButton:hover {{
        background: rgba(122,162,247,0.07);
        border-radius: 4px;
    }}
    QScrollArea {{
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 6px;
        background: {BG_ELEVATED};
    }}
    QPushButton {{
        background: {BG_ELEVATED};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 5px;
        color: {TEXT_PRIMARY};
        font-size: 12px;
        padding: 6px 16px;
        min-width: 80px;
    }}
    QPushButton:hover {{ border-color: {ACCENT_BLUE}; color: {ACCENT_BLUE}; }}
    QPushButton#btn-save {{
        background: {ACCENT_BLUE};
        border-color: {ACCENT_BLUE};
        color: #1a1b26;
        font-weight: 600;
    }}
    QPushButton#btn-save:hover {{ background: #89b4fa; border-color: #89b4fa; color: #1a1b26; }}
"""

# Swatch colours for theme radio buttons
_THEME_SWATCHES: dict[str, str] = {
    "Tokyo Night":    "#7aa2f7",
    "Dark":           "#569cd6",
    "Dracula":        "#bd93f9",
    "Solarized Dark": "#268bd2",
    "Light":          "#0366d6",
}


class SettingsDialog(QDialog):
    """App-level settings: theme selection and provider enable/disable."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(440)
        self.setMinimumHeight(480)
        self.setModal(True)
        self.setStyleSheet(_STYLE)
        self._checkboxes: list[tuple[QCheckBox, str]] = []
        self._theme_group = QButtonGroup(self)
        self._build()
        self._populate()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(12)

        title = QLabel("Settings")
        title.setObjectName("dlg-title")
        root.addWidget(title)

        # ── Theme section ──────────────────────────────────────────────────
        theme_sec = QLabel("APPEARANCE")
        theme_sec.setObjectName("section-header")
        root.addWidget(theme_sec)

        theme_frame = QFrame()
        theme_frame.setStyleSheet(
            f"QFrame {{ background: {BG_ELEVATED}; border: 1px solid {BORDER_SUBTLE};"
            f" border-radius: 6px; padding: 4px; }}"
        )
        theme_layout = QVBoxLayout(theme_frame)
        theme_layout.setContentsMargins(10, 6, 10, 6)
        theme_layout.setSpacing(2)

        current = get_active_theme_name()
        for i, name in enumerate(THEME_NAMES):
            row = QHBoxLayout()
            row.setSpacing(8)
            rb = QRadioButton(name)
            rb.setChecked(name == current)
            self._theme_group.addButton(rb, i)
            row.addWidget(rb)

            swatch_color = _THEME_SWATCHES.get(name, ACCENT_BLUE)
            swatch = QLabel("  ")
            swatch.setFixedSize(18, 18)
            swatch.setStyleSheet(
                f"background: {swatch_color}; border-radius: 3px; border: none;"
            )
            row.addWidget(swatch)
            row.addStretch()
            theme_layout.addLayout(row)

        root.addWidget(theme_frame)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet(f"color: {BORDER_SUBTLE};")
        root.addWidget(sep1)

        # ── Providers section ──────────────────────────────────────────────
        prov_sec = QLabel("ACTIVE PROVIDERS")
        prov_sec.setObjectName("section-header")
        root.addWidget(prov_sec)

        hint = QLabel(
            "Uncheck a provider to hide it from the sidebar and overview."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        root.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(10, 8, 10, 8)
        self._list_layout.setSpacing(2)
        self._list_layout.addStretch()

        scroll.setWidget(self._list_widget)
        root.addWidget(scroll, stretch=1)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {BORDER_SUBTLE};")
        root.addWidget(sep2)

        btn_row = QHBoxLayout()
        self._btn_save = QPushButton("Save")
        self._btn_save.setObjectName("btn-save")
        self._btn_save.clicked.connect(self._save)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(self._btn_save)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        root.addLayout(btn_row)

    def _populate(self) -> None:
        from spancloud.config.sidebar import get_enabled_providers

        import spancloud.providers  # noqa: F401
        from spancloud.core.registry import registry

        enabled = get_enabled_providers()

        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._checkboxes.clear()

        for p in registry.list_providers():
            cb = QCheckBox(p.display_name)
            cb.setChecked(p.name in enabled)
            if not p.supported_resource_types:
                cb.setEnabled(False)
                cb.setToolTip("Not yet implemented")
            self._list_layout.insertWidget(self._list_layout.count() - 1, cb)
            self._checkboxes.append((cb, p.name))

    def selected_theme(self) -> str:
        btn = self._theme_group.checkedButton()
        return btn.text() if btn else get_active_theme_name()

    def _save(self) -> None:
        from spancloud.config.sidebar import set_enabled_providers

        enabled = {name for cb, name in self._checkboxes if cb.isChecked()}
        if not enabled:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Nothing Selected", "Enable at least one provider.")
            return
        set_enabled_providers(enabled)
        self.accept()
