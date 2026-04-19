"""Overview widget — provider status cards in a grid."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from spancloud.gui.theme import (
    ACCENT_BLUE,
    ACCENT_CYAN,
    STATUS_ERROR,
    STATUS_MUTED,
    STATUS_OK,
    STATUS_WARN,
    TEXT_MUTED,
    TEXT_PRIMARY,
)



class ProviderCard(QFrame):
    clicked        = Signal(str)
    connect_clicked = Signal(str)   # emitted when card is clicked while unauthed

    def __init__(self, provider: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name = provider["name"]
        self._status = provider.get("status", "checking")
        status = self._status

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setProperty("class", "provider-card")
        self.setProperty("status", status)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(140)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 14, 16, 14)
        self._layout.setSpacing(4)

        # Header row: name + status badge
        header = QHBoxLayout()
        name_lbl = QLabel(provider["display"])
        name_lbl.setObjectName("card-name")
        header.addWidget(name_lbl)
        header.addStretch()

        self._status_lbl = QLabel(self._status_text(status))
        self._status_lbl.setObjectName("card-status")
        self._status_lbl.setProperty("status", status)
        header.addWidget(self._status_lbl)
        self._layout.addLayout(header)

        count = provider.get("resources", 0)
        self._count_lbl = QLabel(str(count) if count else "—")
        self._count_lbl.setObjectName("card-count")
        self._layout.addWidget(self._count_lbl)
        self._layout.addWidget(self._small_label("resources", "card-count-label"))

    def set_status(self, status: str, resource_count: int = 0) -> None:
        """Update displayed status and resource count."""
        self._status = status
        self._status_lbl.setText(self._status_text(status))
        self._status_lbl.setProperty("status", status)
        self._status_lbl.style().unpolish(self._status_lbl)
        self._status_lbl.style().polish(self._status_lbl)
        self.setProperty("status", status)
        self.style().unpolish(self)
        self.style().polish(self)
        self._count_lbl.setText(str(resource_count) if resource_count else "—")

    @staticmethod
    def _status_text(status: str) -> str:
        return {
            "authenticated":   "● Connected",
            "error":           "● Auth Error",
            "unauthenticated": "○ Not Connected",
            "checking":        "○ Checking…",
        }.get(status, status)

    def _small_label(self, text: str, obj_name: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName(obj_name)
        return lbl

    def mousePressEvent(self, event: object) -> None:
        if self._status in ("unauthenticated", "error"):
            self.connect_clicked.emit(self._name)
        else:
            self.clicked.emit(self._name)


class OverviewWidget(QWidget):
    provider_clicked  = Signal(str)
    connect_requested = Signal(str)   # unauthenticated card clicked

    def __init__(self, providers: list[dict], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._providers = providers
        self._cards: dict[str, ProviderCard] = {}
        self._summary_frame: QWidget | None = None
        self._summary_container: QVBoxLayout | None = None
        self._build(providers)

    def update_provider_status(self, name: str, status: str, resource_count: int = 0) -> None:
        """Update a provider card's status after an async auth check."""
        card = self._cards.get(name)
        if card is None:
            return
        card.set_status(status, resource_count)
        # Refresh summary bar counts
        if self._summary_frame and self._summary_container:
            idx = self._summary_container.indexOf(self._summary_frame)
            self._summary_container.removeWidget(self._summary_frame)
            self._summary_frame.deleteLater()
            self._summary_frame = self._make_summary(self._providers)
            self._summary_container.insertWidget(idx, self._summary_frame)

    def _build(self, providers: list[dict]) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Scrollable grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(24, 20, 24, 24)
        v.setSpacing(20)

        self._summary_container = v
        self._summary_frame = self._make_summary(providers)
        v.addWidget(self._summary_frame)

        # Provider cards grid
        grid = QGridLayout()
        grid.setSpacing(16)
        cols = 3
        for i, p in enumerate(providers):
            card = ProviderCard(p)
            card.clicked.connect(self.provider_clicked)
            card.connect_clicked.connect(self.connect_requested)
            self._cards[p["name"]] = card
            grid.addWidget(card, i // cols, i % cols)
        v.addLayout(grid)
        v.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll)

    def _make_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("content-header")
        header.setFixedHeight(60)
        h = QHBoxLayout(header)
        h.setContentsMargins(24, 8, 24, 8)
        h.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        left = QVBoxLayout()
        left.setSpacing(2)
        left.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title = QLabel("Overview")
        title.setObjectName("content-title")
        left.addWidget(title)
        sub = QLabel("All cloud providers at a glance")
        sub.setObjectName("content-subtitle")
        left.addWidget(sub)
        h.addLayout(left)
        h.addStretch()
        return header

    def _make_summary(self, providers: list[dict]) -> QWidget:
        authed = [p for p in providers if p["status"] == "authenticated"]
        errors = [p for p in providers if p["status"] == "error"]
        total  = sum(p["resources"] for p in providers)

        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: #1f2335;
                border: 1px solid #3b4261;
                border-radius: 8px;
                padding: 4px;
            }}
        """)
        row = QHBoxLayout(frame)
        row.setContentsMargins(20, 12, 20, 12)
        row.setSpacing(0)

        def stat(value: str, label: str, color: str) -> QWidget:
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(2)
            val_lbl = QLabel(value)
            val_lbl.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: 700;")
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            v.addWidget(val_lbl)
            v.addWidget(lbl)
            return w

        def divider() -> QFrame:
            f = QFrame()
            f.setFrameShape(QFrame.Shape.VLine)
            f.setStyleSheet(f"color: #3b4261; max-width: 1px; margin: 0 24px;")
            return f

        row.addWidget(stat(str(len(providers)), "Total Providers", ACCENT_BLUE))
        row.addWidget(divider())
        row.addWidget(stat(str(len(authed)), "Connected", STATUS_OK))
        row.addWidget(divider())
        row.addWidget(stat(str(len(errors)), "Errors", STATUS_ERROR if errors else TEXT_MUTED))
        row.addWidget(divider())
        row.addWidget(stat(f"{total:,}", "Total Resources", ACCENT_CYAN))
        row.addStretch()

        return frame
