"""Sidebar settings dialog — configure which resource types appear per provider."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
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
    TEXT_SECONDARY,
)


class SidebarSettingsDialog(QDialog):
    """Modal dialog for toggling which services appear in the provider sidebar."""

    def __init__(
        self, provider_name: str, provider_display: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._provider_name = provider_name
        self._checkboxes: list[tuple[QCheckBox, dict]] = []

        self.setWindowTitle(f"Sidebar Settings — {provider_display}")
        self.setMinimumWidth(400)
        self.setMinimumHeight(480)
        self.setModal(True)
        self.setStyleSheet(f"""
            QDialog {{
                background: {BG_SURFACE};
            }}
            QLabel#dialog-title {{
                color: {ACCENT_BLUE};
                font-size: 14px;
                font-weight: 700;
            }}
            QLabel#dialog-hint {{
                color: {TEXT_MUTED};
                font-size: 11px;
            }}
            QCheckBox {{
                color: {TEXT_PRIMARY};
                font-size: 12px;
                spacing: 8px;
                padding: 5px 4px;
            }}
            QCheckBox::indicator {{
                width: 15px;
                height: 15px;
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 3px;
                background: {BG_ELEVATED};
            }}
            QCheckBox::indicator:checked {{
                background: {ACCENT_BLUE};
                border-color: {ACCENT_BLUE};
            }}
            QCheckBox:hover {{
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
            QPushButton:hover {{
                border-color: {ACCENT_BLUE};
                color: {ACCENT_BLUE};
            }}
            QPushButton#btn-save {{
                background: {ACCENT_BLUE};
                border-color: {ACCENT_BLUE};
                color: #1a1b26;
                font-weight: 600;
            }}
            QPushButton#btn-save:hover {{
                background: #89b4fa;
                border-color: #89b4fa;
                color: #1a1b26;
            }}
            QPushButton#btn-reset {{
                color: {TEXT_MUTED};
            }}
        """)
        self._build()
        self._populate()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(12)

        title = QLabel(f"Configure Sidebar")
        title.setObjectName("dialog-title")
        root.addWidget(title)

        hint = QLabel("Check the services to show in the sidebar (max ~10 recommended).")
        hint.setObjectName("dialog-hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER_SUBTLE}; margin: 2px 0;")
        root.addWidget(sep)

        # Scrollable checkbox area
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

        # Buttons
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color: {BORDER_SUBTLE}; margin: 2px 0;")
        root.addWidget(sep2)

        btn_row = QVBoxLayout()
        btn_row.setSpacing(8)

        from PySide6.QtWidgets import QHBoxLayout
        h = QHBoxLayout()
        h.setSpacing(8)

        self._btn_save = QPushButton("Save")
        self._btn_save.setObjectName("btn-save")
        self._btn_save.clicked.connect(self._save)

        btn_reset = QPushButton("Reset Defaults")
        btn_reset.setObjectName("btn-reset")
        btn_reset.clicked.connect(self._reset)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        h.addWidget(self._btn_save)
        h.addWidget(btn_reset)
        h.addStretch()
        h.addWidget(btn_cancel)
        root.addLayout(h)

    def _populate(self) -> None:
        from spancloud.config.sidebar import get_available_services, get_sidebar_items

        current = {s["name"] for s in get_sidebar_items(self._provider_name)}
        available = get_available_services(self._provider_name)

        # Clear existing checkboxes (keep trailing stretch)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._checkboxes.clear()

        for svc in available:
            cb = QCheckBox(f"{svc['label']}  ({svc['type']})")
            cb.setChecked(svc["name"] in current)
            self._list_layout.insertWidget(self._list_layout.count() - 1, cb)
            self._checkboxes.append((cb, svc))

    def _save(self) -> None:
        from spancloud.config.sidebar import set_sidebar_items

        selected = [svc for cb, svc in self._checkboxes if cb.isChecked()]
        if not selected:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Nothing Selected", "Select at least one service.")
            return
        set_sidebar_items(self._provider_name, selected)
        self.accept()

    def _reset(self) -> None:
        from spancloud.config.sidebar import reset_sidebar
        reset_sidebar(self._provider_name)
        self._populate()
