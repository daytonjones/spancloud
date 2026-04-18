"""Overview tab — summary of all providers at a glance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual import work
from textual.containers import VerticalScroll
from textual.widgets import Button, Checkbox, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from skyforge.core.provider import BaseProvider


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
            from skyforge.tui.screens.auth import AuthScreen

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


class OverviewTab(VerticalScroll):
    """Overview tab showing all providers and their status."""

    def __init__(self, providers: list[BaseProvider]) -> None:
        super().__init__()
        self._providers = providers

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold cyan]Skyforge[/bold cyan] — "
            "Multi-Cloud Infrastructure Overview\n",
            id="overview-title",
        )

        from skyforge.config.sidebar import is_provider_enabled

        implemented = [p for p in self._providers if p.supported_resource_types]
        stubs = [p for p in self._providers if not p.supported_resource_types]

        if implemented:
            yield Static(
                "[bold]Active Providers[/bold]  "
                "[dim](click a card to authenticate, "
                "toggle checkbox to show/hide tab)[/dim]"
            )
            for provider in implemented:
                yield Checkbox(
                    f" {provider.display_name}",
                    value=is_provider_enabled(provider.name),
                    id=f"enable-{provider.name}",
                    name=provider.name,
                )
                yield ProviderStatusCard(provider)

        if stubs:
            yield Static("\n[bold dim]Planned Providers[/bold dim]")
            for provider in stubs:
                yield ProviderStatusCard(provider)

        yield Static("")
        yield Button(
            "\u274c  Quit Skyforge",
            id="quit-button",
            variant="error",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "quit-button":
            self.app.exit()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Toggle provider enabled/disabled and save."""
        checkbox_id = event.checkbox.id or ""
        if not checkbox_id.startswith("enable-"):
            return

        provider_name = event.checkbox.name or ""
        if not provider_name:
            return

        from skyforge.config.sidebar import get_enabled_providers, set_enabled_providers

        enabled = get_enabled_providers()
        if event.value:
            enabled.add(provider_name)
        else:
            enabled.discard(provider_name)

        set_enabled_providers(enabled)
        self.app.notify(
            f"{provider_name}: {'enabled' if event.value else 'disabled'} "
            f"— restart TUI to update tabs",
            timeout=4,
        )
