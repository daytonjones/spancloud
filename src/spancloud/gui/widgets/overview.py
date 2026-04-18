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

_RESOURCE_TYPE_COLORS: dict[str, str] = {
    "compute":       ACCENT_CYAN,
    "storage":       ACCENT_BLUE,
    "network":       "#73daca",
    "database":      "#bb9af7",
    "container":     "#7aa2f7",
    "serverless":    "#e0af68",
    "load_balancer": "#9ece6a",
    "dns":           "#7dcfff",
}

_MOCK_RESOURCE_BREAKDOWN: dict[str, dict[str, int]] = {
    "aws":          {"compute": 24, "storage": 18, "network": 31, "database": 9, "container": 5, "serverless": 42, "load_balancer": 8, "dns": 5},
    "gcp":          {"compute": 12, "storage": 27, "network": 18, "database": 6, "container": 11, "serverless": 8, "load_balancer": 3, "dns": 2},
    "digitalocean": {"compute": 8,  "storage": 5,  "network": 4,  "database": 2, "container": 3, "load_balancer": 1},
    "oci":          {"compute": 10, "storage": 8,  "network": 7,  "database": 3, "container": 2, "load_balancer": 1},
    "azure":        {},
    "vultr":        {},
    "alibaba":      {},
}


class ProviderCard(QFrame):
    clicked = Signal(str)

    def __init__(self, provider: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name = provider["name"]
        status = provider["status"]

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setProperty("class", "provider-card")
        self.setProperty("status", status)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        # Header row: name + status badge
        header = QHBoxLayout()
        name_lbl = QLabel(provider["display"])
        name_lbl.setObjectName("card-name")
        header.addWidget(name_lbl)
        header.addStretch()

        status_text = {
            "authenticated":   "● Connected",
            "error":           "● Auth Error",
            "unauthenticated": "○ Not Connected",
        }.get(status, status)
        status_lbl = QLabel(status_text)
        status_lbl.setObjectName("card-status")
        status_lbl.setProperty("status", status)
        header.addWidget(status_lbl)
        layout.addLayout(header)

        # Resource count
        count = provider["resources"]
        count_lbl = QLabel(str(count) if count else "—")
        count_lbl.setObjectName("card-count")
        layout.addWidget(count_lbl)
        layout.addWidget(self._small_label("resources", "card-count-label"))

        layout.addSpacing(6)

        # Mini breakdown bar
        if count and _MOCK_RESOURCE_BREAKDOWN.get(provider["name"]):
            layout.addWidget(self._make_breakdown(provider["name"], count))

    def _small_label(self, text: str, obj_name: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName(obj_name)
        return lbl

    def _make_breakdown(self, name: str, total: int) -> QWidget:
        breakdown = _MOCK_RESOURCE_BREAKDOWN[name]
        bar = QFrame()
        bar.setFixedHeight(6)
        bar.setStyleSheet(f"background: #292e42; border-radius: 3px;")

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        for rt, count in breakdown.items():
            if count == 0:
                continue
            color = _RESOURCE_TYPE_COLORS.get(rt, TEXT_MUTED)
            pct = max(1, int(count / total * 100))
            seg = QFrame()
            seg.setFixedHeight(6)
            seg.setStyleSheet(f"background: {color}; border-radius: 2px;")
            row.addWidget(seg, stretch=pct)

        bar.setLayout(row)

        legend = QHBoxLayout()
        legend.setContentsMargins(0, 4, 0, 0)
        legend.setSpacing(10)
        for rt, count in list(breakdown.items())[:4]:
            if count == 0:
                continue
            color = _RESOURCE_TYPE_COLORS.get(rt, TEXT_MUTED)
            dot = QLabel(f"<span style='color:{color}'>●</span> <span style='color:{TEXT_MUTED};font-size:10px'>{rt} {count}</span>")
            dot.setTextFormat(Qt.TextFormat.RichText)
            legend.addWidget(dot)
        legend.addStretch()

        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(bar)
        v.addLayout(legend)
        return container

    def mousePressEvent(self, event: object) -> None:
        self.clicked.emit(self._name)


class OverviewWidget(QWidget):
    provider_clicked = Signal(str)

    def __init__(self, providers: list[dict], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build(providers)

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

        # Summary bar
        v.addWidget(self._make_summary(providers))

        # Provider cards grid
        grid = QGridLayout()
        grid.setSpacing(16)
        cols = 3
        for i, p in enumerate(providers):
            card = ProviderCard(p)
            card.clicked.connect(self.provider_clicked)
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
