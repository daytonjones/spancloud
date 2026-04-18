"""Resource table widget for displaying cloud resources in the TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import DataTable

from spancloud.utils.logging import get_logger

if TYPE_CHECKING:
    from spancloud.core.provider import BaseProvider
    from spancloud.core.resource import Resource
    from spancloud.tui.widgets.provider_panel import ProviderSelected

logger = get_logger(__name__)


class ResourceTableWidget(DataTable):
    """Displays resources from a selected provider in a data table.

    Listens for ProviderSelected messages and loads resources
    for the chosen provider.
    """

    DEFAULT_CSS = """
    ResourceTableWidget {
        height: 1fr;
        min-height: 10;
    }
    """

    def on_mount(self) -> None:
        """Set up table columns."""
        self.add_columns("ID", "Name", "Type", "Region", "State")
        self.cursor_type = "row"
        self.zebra_stripes = True

    def on_provider_selected(self, event: ProviderSelected) -> None:
        """Handle provider selection — load resources from the selected provider."""
        self.run_worker(
            self._load_resources(event.provider),
            name=f"resources-{event.provider.name}",
        )

    async def _load_resources(self, provider: BaseProvider) -> None:
        """Fetch and display resources from the given provider."""
        self.clear()
        self.loading = True

        try:
            if not await provider.is_authenticated():
                await provider.authenticate()

            all_resources: list[Resource] = []
            for rt in provider.supported_resource_types:
                try:
                    resources = await provider.list_resources(rt)
                    all_resources.extend(resources)
                except Exception as exc:
                    logger.warning(
                        "Failed to list %s from %s: %s", rt.value, provider.name, exc
                    )

            self._populate_table(all_resources)

        except Exception as exc:
            logger.error("Failed to load resources from %s: %s", provider.name, exc)
            self.app.notify(
                f"Error loading resources from {provider.display_name}: {exc}",
                severity="error",
            )
        finally:
            self.loading = False

    def _populate_table(self, resources: list[Resource]) -> None:
        """Fill the table with resource data."""
        self.clear()

        for r in sorted(resources, key=lambda x: (x.resource_type.value, x.name)):
            state_display = r.state.value
            self.add_row(
                r.id,
                r.display_name,
                r.resource_type.value,
                r.region,
                state_display,
                key=f"{r.provider}:{r.id}",
            )
