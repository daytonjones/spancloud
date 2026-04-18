"""Overview tab — summary of all providers at a glance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import work
from textual.containers import Grid, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Checkbox, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from spancloud.core.provider import BaseProvider


class ProviderStatusCard(Static):
    """Status card for a single provider in the overview.

    Click to open auth popup (if not authenticated) or re-verify.
    """

    def __init__(self, provider: BaseProvider) -> None:
        super().__init__()
        self._provider = provider
        self._is_stub = len(provider.supported_resource_types) == 0

    def compose(self) -> ComposeResult:
        if self._is_stub:
            self.add_class("stub")
            yield Static(
                f"[bold]{self._provider.display_name}[/bold]  "
                f"[dim italic]— not yet implemented[/dim italic]"
            )
        else:
            types = ", ".join(
                rt.value for rt in self._provider.supported_resource_types
            )
            yield Static(
                f"[bold]{self._provider.display_name}[/bold]  "
                f"[dim]checking...[/dim]",
                id=f"overview-status-{self._provider.name}",
            )
            yield Static(f"  [dim]Resources:[/dim] {types}")
            yield Static(
                "  [dim italic]click to re-authenticate[/dim italic]",
                id=f"overview-hint-{self._provider.name}",
            )

    def on_mount(self) -> None:
        if not self._is_stub:
            self._do_auth()

    def on_click(self) -> None:
        """Open auth popup or re-verify on click."""
        if self._is_stub:
            return

        if self.has_class("error") or not self.has_class("authenticated"):
            # Not authenticated — open the auth popup
            from spancloud.tui.screens.auth import AuthScreen

            def _on_dismiss(result: bool) -> None:
                if result:
                    self.remove_class("error")
                    self._do_auth()

            self.app.push_screen(AuthScreen(self._provider), _on_dismiss)
        else:
            # Already authenticated — just re-verify
            status = self.query_one(
                f"#overview-status-{self._provider.name}", Static
            )
            status.update(
                f"[bold]{self._provider.display_name}[/bold]  "
                f"[yellow]re-verifying...[/yellow]"
            )
            self.remove_class("authenticated")
            self._do_auth()

    @work(exclusive=True)
    async def _do_auth(self) -> None:
        status = self.query_one(
            f"#overview-status-{self._provider.name}", Static
        )
        hint = self.query_one(
            f"#overview-hint-{self._provider.name}", Static
        )
        try:
            success = await self._provider.authenticate()
            count = len(self._provider.supported_resource_types)

            # Get extra identity info
            identity = ""
            if hasattr(self._provider, "_auth"):
                auth = self._provider._auth
                if hasattr(auth, "active_profile"):
                    identity = f"  profile: {auth.active_profile}"
                elif hasattr(auth, "project_id") and auth.project_id:
                    identity = f"  project: {auth.project_id}"

            if success:
                self.add_class("authenticated")
                self.remove_class("error")
                status.update(
                    f"[bold]{self._provider.display_name}[/bold]  "
                    f"[green]\u2714 authenticated[/green]  "
                    f"[dim]({count} resource types){identity}[/dim]"
                )
                hint.update(
                    "  [dim italic]click to re-authenticate[/dim italic]"
                )
                self.app.notify(
                    f"{self._provider.display_name}: authenticated",
                    timeout=3,
                )
            else:
                self.add_class("error")
                status.update(
                    f"[bold]{self._provider.display_name}[/bold]  "
                    f"[red]\u2718 not authenticated[/red]"
                )
                hint.update(
                    "  [yellow]click to authenticate[/yellow]"
                )
        except Exception as exc:
            self.add_class("error")
            status.update(
                f"[bold]{self._provider.display_name}[/bold]  "
                f"[red]\u2718 error[/red]"
            )
            hint.update(f"  [red]{exc}[/red] — click to authenticate")


class ProviderCell(Vertical):
    """Checkbox + status card bundled as a single grid cell."""

    def __init__(self, provider: BaseProvider, enabled: bool) -> None:
        super().__init__(id=f"provider-cell-{provider.name}")
        self._provider = provider
        self._enabled = enabled

    def compose(self) -> ComposeResult:
        yield Checkbox(
            f" {self._provider.display_name}",
            value=self._enabled,
            id=f"enable-{self._provider.name}",
            name=self._provider.name,
        )
        yield ProviderStatusCard(self._provider)

    def on_mount(self) -> None:
        if not self._enabled:
            self.add_class("available")


class OverviewTab(VerticalScroll):
    """Overview tab showing all providers and their status."""

    class ProviderToggled(Message):
        """Posted when a provider is enabled or disabled via the Overview."""

        def __init__(self, provider_name: str, enabled: bool) -> None:
            super().__init__()
            self.provider_name = provider_name
            self.enabled = enabled

    def __init__(self, providers: list[BaseProvider]) -> None:
        super().__init__()
        self._providers = providers

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold cyan]Spancloud[/bold cyan] — "
            "Multi-Cloud Infrastructure Overview\n",
            id="overview-title",
        )

        from spancloud.config.sidebar import is_provider_enabled

        implemented = [p for p in self._providers if p.supported_resource_types]
        stubs = [p for p in self._providers if not p.supported_resource_types]

        active = [p for p in implemented if is_provider_enabled(p.name)]
        available = [p for p in implemented if not is_provider_enabled(p.name)]

        # Both sections are always in the DOM; visibility is managed at runtime.
        yield Static(
            "[bold]Active Providers[/bold]  "
            "[dim](click a card to authenticate, toggle checkbox to disable)[/dim]",
            id="active-header",
        )
        with Grid(id="provider-grid"):
            for provider in active:
                yield ProviderCell(provider, enabled=True)

        yield Static(
            "[bold]Available Providers[/bold]  "
            "[dim](toggle checkbox to enable)[/dim]",
            id="available-header",
        )
        with Grid(id="available-grid"):
            for provider in available:
                yield ProviderCell(provider, enabled=False)

        if stubs:
            yield Static("\n[bold dim]Planned Providers[/bold dim]")
            with Grid(id="stub-grid"):
                for provider in stubs:
                    yield ProviderStatusCard(provider)

    def on_mount(self) -> None:
        self._update_section_visibility()

    def _update_section_visibility(self) -> None:
        active_grid = self.query_one("#provider-grid")
        available_grid = self.query_one("#available-grid")
        has_active = bool(active_grid.children)
        has_available = bool(available_grid.children)
        self.query_one("#active-header").display = has_active
        active_grid.display = has_active
        self.query_one("#available-header").display = has_available
        available_grid.display = has_available

    async def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Toggle provider enabled/disabled, move its card, and update tabs."""
        checkbox_id = event.checkbox.id or ""
        if not checkbox_id.startswith("enable-"):
            return

        provider_name = event.checkbox.name or ""
        if not provider_name:
            return

        from spancloud.config.sidebar import get_enabled_providers, set_enabled_providers

        enabled_set = get_enabled_providers()
        if event.value:
            enabled_set.add(provider_name)
        else:
            enabled_set.discard(provider_name)
        set_enabled_providers(enabled_set)

        # Remove the existing cell and remount a fresh one in the correct grid.
        provider = next((p for p in self._providers if p.name == provider_name), None)
        if provider is None:
            return

        try:
            old_cell = self.query_one(f"#provider-cell-{provider_name}", ProviderCell)
            await old_cell.remove()
        except Exception:
            pass

        if event.value:
            await self.query_one("#provider-grid").mount(ProviderCell(provider, enabled=True))
        else:
            await self.query_one("#available-grid").mount(ProviderCell(provider, enabled=False))

        self._update_section_visibility()
        self.post_message(OverviewTab.ProviderToggled(provider_name, event.value))
