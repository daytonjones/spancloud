"""Spancloud desktop GUI — PySide6 mockup (visual only)."""

from __future__ import annotations

import sys
import importlib.resources as pkg_resources

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from spancloud.gui.theme import DARK_PALETTE, TEXT_MUTED, apply_stylesheet
from spancloud.gui.widgets.overview import OverviewWidget
from spancloud.gui.widgets.provider_view import ProviderViewWidget
from spancloud.gui.widgets.sidebar import ProviderSidebar
from spancloud.gui.widgets.toolbar import AppToolbar


_MOCK_PROVIDERS = [
    {"name": "aws",          "display": "Amazon Web Services", "status": "authenticated", "resources": 142},
    {"name": "gcp",          "display": "Google Cloud",        "status": "authenticated", "resources": 87},
    {"name": "azure",        "display": "Microsoft Azure",     "status": "error",         "resources": 0},
    {"name": "digitalocean", "display": "DigitalOcean",        "status": "authenticated", "resources": 23},
    {"name": "vultr",        "display": "Vultr",               "status": "unauthenticated","resources": 0},
    {"name": "oci",          "display": "Oracle Cloud (OCI)",  "status": "authenticated", "resources": 31},
    {"name": "alibaba",      "display": "Alibaba Cloud",       "status": "unauthenticated","resources": 0},
]


def _load_window_icon() -> QIcon:
    try:
        svg_path = str(
            pkg_resources.files("spancloud.gui.assets").joinpath("icon.svg")
        )
        renderer = QSvgRenderer(svg_path)
        from PySide6.QtGui import QPainter
        pix = QPixmap(256, 256)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        renderer.render(painter)
        painter.end()
        return QIcon(pix)
    except Exception:
        return QIcon()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Spancloud — Multi-Cloud Dashboard")
        self.resize(1400, 900)
        self.setMinimumSize(1000, 650)
        self.setWindowIcon(_load_window_icon())

        apply_stylesheet(self)
        self._build_ui()
        self._setup_statusbar()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Full-width toolbar ──────────────────────────────────────────
        self._toolbar = AppToolbar()
        self._toolbar.refresh_clicked.connect(self._on_refresh)
        self._toolbar.settings_clicked.connect(self._on_settings)
        root.addWidget(self._toolbar)

        # ── Body: resizable sidebar + content ───────────────────────────
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(1)
        self._splitter.setStyleSheet("QSplitter::handle { background: #3b4261; }")

        self._sidebar = ProviderSidebar(_MOCK_PROVIDERS)
        self._sidebar.provider_selected.connect(self._on_provider_selected)
        self._splitter.addWidget(self._sidebar)

        # Content stack
        self._stack = QStackedWidget()

        self._overview = OverviewWidget(_MOCK_PROVIDERS)
        self._overview.provider_clicked.connect(self._on_provider_selected)
        self._stack.addWidget(self._overview)

        self._provider_views: dict[str, ProviderViewWidget] = {}
        for p in _MOCK_PROVIDERS:
            view = ProviderViewWidget(p)
            # Forward region/profile/project changes to the toolbar subtitle
            view._controls.region_changed.connect(
                lambda region, pname=p["name"]: self._on_context_changed(pname)
            )
            view._controls.profile_changed.connect(
                lambda profile, pname=p["name"]: self._on_context_changed(pname)
            )
            view._controls.project_changed.connect(
                lambda project, pname=p["name"]: self._on_context_changed(pname)
            )
            self._provider_views[p["name"]] = view
            self._stack.addWidget(view)

        self._splitter.addWidget(self._stack)

        # Sidebar starts at 220px, content takes the rest; both resizable
        self._splitter.setSizes([220, 1180])
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, False)

        root.addWidget(self._splitter, stretch=1)

    def _setup_statusbar(self) -> None:
        bar = QStatusBar()
        bar.setContentsMargins(8, 0, 8, 0)
        self.setStatusBar(bar)

        self._status_label = QLabel("Ready")
        bar.addWidget(self._status_label, 1)

        total = sum(p["resources"] for p in _MOCK_PROVIDERS)
        authed = sum(1 for p in _MOCK_PROVIDERS if p["status"] == "authenticated")
        summary = QLabel(
            f"{authed}/{len(_MOCK_PROVIDERS)} providers connected   ·   "
            f"{total:,} total resources"
        )
        summary.setStyleSheet(f"color: {TEXT_MUTED}; padding-right: 8px;")
        bar.addPermanentWidget(summary)

    def _on_provider_selected(self, name: str) -> None:
        self._sidebar.select(name)
        if name == "overview":
            self._stack.setCurrentWidget(self._overview)
            self._toolbar.set_context("Overview", "All cloud providers at a glance")
            self._status_label.setText("Overview")
        elif name in self._provider_views:
            self._stack.setCurrentWidget(self._provider_views[name])
            p = next(p for p in _MOCK_PROVIDERS if p["name"] == name)
            status_str = {
                "authenticated":   f"{p['resources']} resources",
                "error":           "Authentication error",
                "unauthenticated": "Not connected",
            }.get(p["status"], "")
            self._toolbar.set_context(p["display"], status_str)
            self._status_label.setText(f"{p['display']} — {status_str}")

    def _on_context_changed(self, provider_name: str) -> None:
        """Update toolbar subtitle when region/profile/project changes."""
        view = self._provider_views.get(provider_name)
        if view is None or self._stack.currentWidget() is not view:
            return
        p = next(p for p in _MOCK_PROVIDERS if p["name"] == provider_name)
        parts = []
        if view._current_region:
            parts.append(view._current_region)
        if view._current_profile:
            parts.append(f"profile: {view._current_profile}")
        if view._current_project:
            parts.append(f"project: {view._current_project}")
        if not parts and p["resources"]:
            parts.append(f"{p['resources']} resources")
        self._toolbar.set_context(p["display"], "  ·  ".join(parts))

    def _on_refresh(self) -> None:
        self._status_label.setText("Refreshing…")

    def _on_settings(self) -> None:
        self._status_label.setText("Settings (not yet implemented)")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Spancloud")
    app.setOrganizationName("spancloud")
    app.setPalette(DARK_PALETTE)

    icon = _load_window_icon()
    app.setWindowIcon(icon)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
