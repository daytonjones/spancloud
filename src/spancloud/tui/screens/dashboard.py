"""Dashboard screen — tabbed view with one tab per provider."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.screen import Screen
from textual.widgets import Footer, Header, TabbedContent, TabPane

# Import providers to ensure registration.
import spancloud.providers  # noqa: F401
from spancloud.config.sidebar import is_provider_enabled
from spancloud.core.registry import registry
from spancloud.tui.widgets.overview_tab import OverviewTab
from spancloud.tui.widgets.provider_tab import ProviderTab  # noqa: F401 — used in compose + handler

if TYPE_CHECKING:
    from textual.app import ComposeResult


class DashboardScreen(Screen):
    """Main dashboard with tabbed provider views.

    Layout:
    - Header with clock
    - Tabbed content: Overview + per-enabled-provider tabs
    - Footer with keyboard shortcuts

    Only providers marked as enabled in the config get their own tab.
    All providers (including disabled/stubs) appear on the Overview.
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        providers = registry.list_providers()
        # Only show tabs for implemented AND enabled providers
        tab_providers = [
            p for p in providers
            if p.supported_resource_types and is_provider_enabled(p.name)
        ]

        with TabbedContent(id="provider-tabs"):
            with TabPane("Overview", id="tab-overview"):
                yield OverviewTab(providers)

            for provider in tab_providers:
                with TabPane(
                    provider.display_name,
                    id=f"tab-{provider.name}",
                ):
                    yield ProviderTab(provider)

        yield Footer()

    async def on_overview_tab_provider_toggled(
        self, event: OverviewTab.ProviderToggled
    ) -> None:
        """Add or remove a provider tab when the user toggles it in the Overview."""
        tabs = self.query_one("#provider-tabs", TabbedContent)
        pane_id = f"tab-{event.provider_name}"

        if event.enabled:
            provider = next(
                (p for p in registry.list_providers() if p.name == event.provider_name),
                None,
            )
            if provider and provider.supported_resource_types:
                await tabs.add_pane(
                    TabPane(provider.display_name, ProviderTab(provider), id=pane_id)
                )
                self.app.notify(f"{provider.display_name} tab added", timeout=3)
        else:
            try:
                await tabs.remove_pane(pane_id)
                self.app.notify(f"{event.provider_name} tab removed", timeout=3)
            except Exception:
                pass

    def refresh_data(self) -> None:
        """Refresh the currently active tab."""
        self.app.notify(
            "Select a resource type or analysis item to reload.",
            timeout=3,
        )
