"""Main Textual application for Spancloud."""

from __future__ import annotations

import os

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import TabbedContent  # noqa: TCH002

from spancloud.tui.screens.dashboard import DashboardScreen


def _set_terminal_title(title: str) -> None:
    """Set the terminal window/tab title via /dev/tty."""
    try:
        fd = os.open("/dev/tty", os.O_WRONLY)
        os.write(fd, f"\033]0;{title}\007".encode())
        os.close(fd)
    except OSError:
        pass


class SpancloudApp(App):  # type: ignore[type-arg]
    """Spancloud — the all-seeing eye into multi-cloud infrastructure.

    A Textual TUI application providing a tabbed dashboard view
    with one tab per cloud provider for maximum screen real estate.
    """

    TITLE = "Spancloud"
    SUB_TITLE = "Overview"
    CSS_PATH = "styles/app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("r", "refresh", "Refresh"),
        Binding("?", "toggle_help", "Help"),
        Binding("a", "about", "About"),
    ]

    SCREENS = {
        "dashboard": DashboardScreen,
    }

    def __init__(self, mock: bool = False, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._mock = mock

    def compose(self) -> ComposeResult:
        """Base app has no widgets — the dashboard screen provides everything."""
        return []

    def on_mount(self) -> None:
        """Push the dashboard screen on startup."""
        _set_terminal_title("Spancloud :: Overview")
        if self._mock:
            from spancloud.providers.mock import build_mock_providers
            from spancloud.core.registry import registry
            registry._providers.clear()
            for p in build_mock_providers():
                registry.register(p)
            self.sub_title = "DEMO MODE"
        self.push_screen("dashboard")

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        """Update the header and terminal title when switching tabs.

        Also re-checks auth for the provider tab in case auth happened
        elsewhere (e.g., the Overview tab's auth modal).
        """
        tab_label = event.tab.label_text
        self.sub_title = tab_label
        _set_terminal_title(f"Spancloud :: {tab_label}")

        # Re-check auth on the newly active provider tab
        from spancloud.tui.widgets.provider_tab import ResourceTypeSidebar

        for sidebar in self.screen.query(ResourceTypeSidebar):
            if sidebar.display and sidebar.parent and sidebar.parent.display:
                sidebar.run_worker(
                    sidebar._check_auth(),
                    name=f"reauth-tab-switch-{id(sidebar)}",
                )

    def action_refresh(self) -> None:
        """Trigger a refresh of the current screen."""
        screen = self.screen
        if hasattr(screen, "refresh_data"):
            screen.refresh_data()

    def action_toggle_help(self) -> None:
        """Toggle the help panel."""
        self.notify(
            "Tab / Shift+Tab — switch provider tabs\n"
            "Up / Down — navigate sidebar items\n"
            "Enter — load resource type or run analysis\n"
            "Click row — view resource details\n"
            "/ — search/filter resources\n"
            "Escape — close detail panel or search\n"
            "[r] Refresh  [a] About  [q] Quit",
            title="Keyboard Shortcuts",
            timeout=10,
        )

    def action_about(self) -> None:
        """Show the About dialog."""
        import spancloud
        self.notify(
            f"v{spancloud.__version__}\n"
            "Multi-cloud infrastructure orchestrator\n\n"
            "Providers: AWS · GCP · Azure · DigitalOcean · Vultr · OCI\n"
            "License: MIT\n\n"
            "github.com/daytonjones/spancloud\n"
            "pypi.org/project/spancloud",
            title="About Spancloud",
            timeout=12,
        )
