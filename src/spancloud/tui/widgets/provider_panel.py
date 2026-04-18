"""Provider status panel widget for the TUI dashboard."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from skyforge.core.provider import BaseProvider


class ProviderSelected(Message):
    """Emitted when a user selects a provider panel."""

    def __init__(self, provider: BaseProvider) -> None:
        self.provider = provider
        super().__init__()


class ProviderPanel(Static):
    """Displays the status of a single cloud provider.

    Shows the provider name, authentication status, and supported
    resource types. Clickable to select the provider for resource browsing.
    """

    DEFAULT_CSS = """
    ProviderPanel {
        width: 1fr;
        height: auto;
        min-height: 7;
        border: solid $primary;
        padding: 1 2;
        margin: 0 1;
    }

    ProviderPanel:hover {
        border: double $accent;
    }

    ProviderPanel.authenticated {
        border: solid $success;
    }

    ProviderPanel.stub {
        border: dashed $warning;
    }
    """

    def __init__(self, provider: BaseProvider) -> None:
        super().__init__()
        self._provider = provider
        self._status: str = "checking..."

    def compose(self) -> ComposeResult:
        """Build the panel content."""
        is_stub = len(self._provider.supported_resource_types) == 0
        status_indicator = "[yellow]stub[/yellow]" if is_stub else "[dim]checking...[/dim]"

        with Vertical():
            yield Static(
                f"[bold]{self._provider.display_name}[/bold]",
                id=f"provider-name-{self._provider.name}",
            )
            yield Static(
                f"Status: {status_indicator}",
                id=f"provider-status-{self._provider.name}",
            )
            if is_stub:
                yield Static("[dim italic]Not yet implemented[/dim italic]")
            else:
                types = ", ".join(rt.value for rt in self._provider.supported_resource_types)
                yield Static(f"[dim]Resources: {types}[/dim]")

    def check_status(self) -> None:
        """Kick off an async status check for this provider."""
        if not self._provider.supported_resource_types:
            self.add_class("stub")
            return

        self.run_worker(self._check_auth(), name=f"auth-{self._provider.name}")

    async def _check_auth(self) -> None:
        """Attempt authentication and update the panel display."""
        status_widget = self.query_one(
            f"#provider-status-{self._provider.name}", Static
        )

        try:
            success = await self._provider.authenticate()
            if success:
                self._status = "authenticated"
                status_widget.update("Status: [green]authenticated[/green]")
                self.add_class("authenticated")
            else:
                self._status = "not authenticated"
                status_widget.update("Status: [red]not authenticated[/red]")
        except Exception as exc:
            self._status = f"error: {exc}"
            status_widget.update("Status: [red]error[/red]")

    def on_click(self) -> None:
        """Handle click to select this provider."""
        self.post_message(ProviderSelected(self._provider))
