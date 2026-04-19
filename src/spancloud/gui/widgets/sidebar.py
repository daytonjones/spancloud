"""Left-hand provider navigation sidebar."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from spancloud.gui.theme import (
    ACCENT_GREEN,
    ACCENT_RED,
    STATUS_MUTED,
    TEXT_MUTED,
)

_STATUS_DOT: dict[str, str] = {
    "authenticated":   "●",
    "error":           "●",
    "unauthenticated": "○",
}

_PROVIDER_ICONS: dict[str, str] = {
    "aws":          "☁",
    "gcp":          "☁",
    "azure":        "☁",
    "digitalocean": "⋄",
    "vultr":        "⋄",
    "oci":          "☁",
    "alibaba":      "☁",
}


class ProviderSidebar(QWidget):
    provider_selected = Signal(str)

    def __init__(self, providers: list[dict], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self._buttons: dict[str, QPushButton] = {}
        self._dots: dict[str, QLabel] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Logo / app name
        logo = QLabel("⬡ spancloud")
        logo.setObjectName("sidebar-logo")
        outer.addWidget(logo)

        # Scroll area for provider list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(scroll.horizontalScrollBarPolicy().ScrollBarAlwaysOff)

        inner_widget = QWidget()
        inner = QVBoxLayout(inner_widget)
        inner.setContentsMargins(0, 8, 0, 8)
        inner.setSpacing(0)

        # Overview button
        btn = self._make_button("overview", "⊞  Overview", None)
        self._buttons["overview"] = btn
        inner.addWidget(btn)

        # Providers section
        sect = QLabel("PROVIDERS")
        sect.setObjectName("sidebar-section")
        inner.addWidget(sect)

        for p in providers:
            btn = self._make_button(p["name"], p["display"], p["status"])
            self._buttons[p["name"]] = btn
            inner.addWidget(btn)

        inner.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        scroll.setWidget(inner_widget)
        outer.addWidget(scroll, stretch=1)

        # Select overview by default
        self.select("overview")

    def _make_button(self, name: str, label: str, status: str | None) -> QPushButton:
        btn = QPushButton()
        btn.setProperty("class", "sidebar-item")
        btn.setProperty("active", "false")
        btn.setCheckable(False)
        btn.setFlat(True)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout()
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(8)

        if status is not None:
            dot = QLabel(_STATUS_DOT.get(status, "○"))
            dot.setObjectName(f"dot-{status}")
            dot.setFixedWidth(14)
            row.addWidget(dot)
            self._dots[name] = dot

        lbl = QLabel(label)
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addWidget(lbl)

        container = QWidget()
        container.setLayout(row)
        container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        outer = QVBoxLayout(btn)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        btn.clicked.connect(lambda checked=False, n=name: self.provider_selected.emit(n))
        return btn

    def select(self, name: str) -> None:
        for n, btn in self._buttons.items():
            btn.setProperty("active", "true" if n == name else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def update_status(self, name: str, status: str) -> None:
        """Update the status dot for a provider button after auth check."""
        dot = self._dots.get(name)
        if dot is None:
            return
        dot.setText(_STATUS_DOT.get(status, "○"))
        dot.setObjectName(f"dot-{status}")
        dot.style().unpolish(dot)
        dot.style().polish(dot)
