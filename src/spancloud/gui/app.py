"""Spancloud desktop GUI — PySide6 application."""

from __future__ import annotations

import sys
import importlib.resources as pkg_resources

from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import Qt
from PySide6.QtCore import QByteArray, QSettings
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from spancloud.gui.theme import (
    DARK_PALETTE,
    TEXT_MUTED,
    apply_stylesheet,
    apply_theme,
    build_palette,
    get_active_theme_name,
    get_tokens,
)
from spancloud.gui.widgets.overview import OverviewWidget
from spancloud.gui.widgets.provider_view import ProviderViewWidget
from spancloud.gui.widgets.sidebar import ProviderSidebar
from spancloud.gui.widgets.toolbar import AppToolbar


def _build_provider_list(mock: bool = False) -> list[dict]:
    """Return provider dicts — from the live registry, or mock data."""
    if mock:
        from spancloud.providers.mock import build_mock_providers
        providers_list = build_mock_providers()
    else:
        import spancloud.providers  # noqa: F401 — triggers provider self-registration
        from spancloud.core.registry import registry
        providers_list = registry.list_providers()

    return [
        {
            "name":      p.name,
            "display":   p.display_name,
            "status":    "authenticated" if mock else "checking",
            "resources": 0,
            "provider":  p,
        }
        for p in providers_list
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
    def __init__(self, mock: bool = False) -> None:
        super().__init__()
        self._mock = mock
        title = "Spancloud — Multi-Cloud Dashboard"
        if mock:
            title += "  [DEMO MODE]"
        self.setWindowTitle(title)
        self.resize(1400, 900)
        self.setMinimumSize(1000, 650)
        self.setWindowIcon(_load_window_icon())

        apply_stylesheet(self, get_active_theme_name())

        self._providers = _build_provider_list(mock=mock)
        self._auth_workers: list = []

        self._build_ui()
        self._setup_statusbar()
        self._restore_geometry()
        if mock:
            self._init_mock_ui()
        else:
            self._start_auth_checks()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._toolbar = AppToolbar()
        self._toolbar.refresh_clicked.connect(self._on_refresh)
        self._toolbar.settings_clicked.connect(self._on_settings)
        root.addWidget(self._toolbar)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(1)
        self._splitter.setStyleSheet("QSplitter::handle { background: #3b4261; }")

        self._sidebar = ProviderSidebar(self._providers)
        self._sidebar.provider_selected.connect(self._on_provider_selected)
        self._splitter.addWidget(self._sidebar)

        self._stack = QStackedWidget()

        self._overview = OverviewWidget(self._providers)
        self._overview.provider_clicked.connect(self._on_provider_selected)
        self._overview.connect_requested.connect(self._open_auth_dialog)
        self._stack.addWidget(self._overview)

        self._provider_views: dict[str, ProviderViewWidget] = {}
        for p in self._providers:
            view = ProviderViewWidget(p)
            view._controls.region_changed.connect(
                lambda region, pname=p["name"]: self._on_context_changed(pname)
            )
            view._controls.profile_changed.connect(
                lambda profile, pname=p["name"]: self._on_context_changed(pname)
            )
            view._controls.project_changed.connect(
                lambda project, pname=p["name"]: self._on_context_changed(pname)
            )
            view.auth_requested.connect(
                lambda pname=p["name"]: self._open_auth_dialog(pname)
            )
            self._provider_views[p["name"]] = view
            self._stack.addWidget(view)

        self._splitter.addWidget(self._stack)
        self._splitter.setSizes([220, 1180])
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, False)

        root.addWidget(self._splitter, stretch=1)

    def _setup_statusbar(self) -> None:
        bar = QStatusBar()
        bar.setContentsMargins(8, 0, 8, 0)
        self.setStatusBar(bar)

        self._status_label = QLabel("Checking provider connections…")
        bar.addWidget(self._status_label, 1)

        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet(f"color: {TEXT_MUTED}; padding-right: 8px;")
        bar.addPermanentWidget(self._summary_label)
        self._update_statusbar_summary()

    def _update_statusbar_summary(self) -> None:
        total = sum(p["resources"] for p in self._providers)
        authed = sum(1 for p in self._providers if p["status"] == "authenticated")
        self._summary_label.setText(
            f"{authed}/{len(self._providers)} providers connected   ·   "
            f"{total:,} total resources"
        )

    def _init_mock_ui(self) -> None:
        """Immediately mark all providers authenticated and fetch resource counts."""
        for p in self._providers:
            self._sidebar.update_status(p["name"], "authenticated")
            self._overview.update_provider_status(p["name"], "authenticated")
            view = self._provider_views.get(p["name"])
            if view:
                view.notify_auth_status("authenticated")
            self._fetch_resource_count(p)
        self._status_label.setText("Demo mode — showing sample data")

    def _start_auth_checks(self) -> None:
        from spancloud.gui.async_worker import AsyncWorker

        for p_dict in self._providers:
            provider = p_dict.get("provider")
            if provider is None:
                p_dict["status"] = "unauthenticated"
                continue
            worker = AsyncWorker(provider.authenticate())
            worker.result_ready.connect(
                lambda ok, pd=p_dict: self._on_auth_checked(pd, ok)
            )
            worker.error_occurred.connect(
                lambda err, pd=p_dict: self._on_auth_error(pd, err)
            )
            worker.start()
            self._auth_workers.append(worker)

    def _on_auth_checked(self, p_dict: dict, is_authed: bool) -> None:
        status = "authenticated" if is_authed else "unauthenticated"
        p_dict["status"] = status
        self._sidebar.update_status(p_dict["name"], status)
        self._overview.update_provider_status(p_dict["name"], status)
        self._update_statusbar_summary()
        view = self._provider_views.get(p_dict["name"])
        if view:
            view.notify_auth_status(status)
        if is_authed:
            self._fetch_resource_count(p_dict)

    def _fetch_resource_count(self, p_dict: dict) -> None:
        from spancloud.gui.async_worker import AsyncWorker

        provider = p_dict.get("provider")
        if provider is None:
            return

        async def _count() -> int:
            import asyncio

            async def _one(rt: object) -> int:
                try:
                    resources = await asyncio.wait_for(  # type: ignore[arg-type]
                        provider.list_resources(rt),  # type: ignore[arg-type]
                        timeout=20,
                    )
                    return len(resources)
                except Exception:
                    return 0

            counts = await asyncio.gather(
                *[_one(rt) for rt in provider.supported_resource_types]
            )
            return sum(counts)

        worker = AsyncWorker(_count())
        worker.result_ready.connect(
            lambda count, pd=p_dict: self._on_resource_count(pd, count)
        )
        worker.start()
        self._auth_workers.append(worker)

    def _on_resource_count(self, p_dict: dict, count: int) -> None:
        p_dict["resources"] = count
        self._overview.update_provider_status(p_dict["name"], p_dict["status"], count)
        self._update_statusbar_summary()

    def _on_auth_error(self, p_dict: dict, error: str) -> None:
        p_dict["status"] = "error"
        self._sidebar.update_status(p_dict["name"], "error")
        self._overview.update_provider_status(p_dict["name"], "error")
        self._update_statusbar_summary()
        view = self._provider_views.get(p_dict["name"])
        if view:
            view.notify_auth_status("error")

    def _open_auth_dialog(self, provider_name: str) -> None:
        from spancloud.gui.widgets.auth_dialog import AuthDialog

        p = next((p for p in self._providers if p["name"] == provider_name), None)
        if p is None:
            return
        provider = p.get("provider")
        if provider is None:
            return

        dlg = AuthDialog(provider, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._on_auth_checked(p, True)

    def _on_provider_selected(self, name: str) -> None:
        self._sidebar.select(name)
        if name == "overview":
            self._stack.setCurrentWidget(self._overview)
            self._toolbar.set_context("Overview", "All cloud providers at a glance")
            self._status_label.setText("Overview")
        elif name in self._provider_views:
            self._stack.setCurrentWidget(self._provider_views[name])
            p = next(p for p in self._providers if p["name"] == name)
            status_str = {
                "authenticated":   f"{p['resources']} resources",
                "checking":        "Checking connection…",
                "error":           "Authentication error",
                "unauthenticated": "Not connected",
            }.get(p["status"], "")
            self._toolbar.set_context(p["display"], status_str)
            self._status_label.setText(f"{p['display']} — {status_str}")

    def _on_context_changed(self, provider_name: str) -> None:
        view = self._provider_views.get(provider_name)
        if view is None or self._stack.currentWidget() is not view:
            return
        p = next(p for p in self._providers if p["name"] == provider_name)
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
        for p in self._providers:
            p["status"] = "checking"
            self._sidebar.update_status(p["name"], "checking")
            self._overview.update_provider_status(p["name"], "checking")
        self._start_auth_checks()

    def _restore_geometry(self) -> None:
        settings = QSettings("spancloud", "spancloud-gui")
        geometry = settings.value("windowGeometry")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)

    def closeEvent(self, event: object) -> None:
        settings = QSettings("spancloud", "spancloud-gui")
        settings.setValue("windowGeometry", self.saveGeometry())
        super().closeEvent(event)  # type: ignore[misc]

    def _on_settings(self) -> None:
        from spancloud.gui.widgets.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Apply theme if changed
            apply_theme(self, dlg.selected_theme())
            # Rebuild sidebar to reflect enable/disable changes
            from spancloud.config.sidebar import get_enabled_providers
            enabled = get_enabled_providers()
            for p in self._providers:
                visible = p["name"] in enabled
                self._sidebar.set_provider_visible(p["name"], visible)


def main(mock: bool = False) -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Spancloud")
    app.setOrganizationName("spancloud")
    app.setPalette(build_palette(get_tokens(get_active_theme_name())))

    icon = _load_window_icon()
    app.setWindowIcon(icon)

    window = MainWindow(mock=mock)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
