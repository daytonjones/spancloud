"""CLI command for showing authentication status and capabilities for all providers."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

console = Console()
status_app = typer.Typer()


@status_app.callback(invoke_without_command=True)
def status_all(ctx: typer.Context) -> None:
    """Show authentication status and capabilities for all providers."""
    asyncio.run(_show_status())


async def _show_status() -> None:
    import spancloud.providers  # noqa: F401 — triggers auto-registration
    from spancloud.core.registry import registry

    providers = list(registry.all())

    # Check auth for all providers concurrently
    async def _check(provider):  # type: ignore[no-untyped-def]
        try:
            ok = await provider.authenticate()
            return provider, ok, None
        except Exception as exc:
            return provider, False, str(exc)

    results = await asyncio.gather(*[_check(p) for p in providers])

    table = Table(title="Spancloud Provider Status", show_header=True)
    table.add_column("Provider", style="bold")
    table.add_column("Status")
    table.add_column("Identity / Details")
    table.add_column("Resource Types", style="dim")

    for provider, ok, err in results:
        if not provider.supported_resource_types:
            table.add_row(
                provider.display_name,
                "[dim]planned[/dim]",
                "—",
                "[dim]not yet implemented[/dim]",
            )
            continue

        # Get identity details
        details = ""
        if ok:
            try:
                identity = await provider.get_status()
                # get_status returns dict — pick meaningful fields
                for key in ("profile", "email", "project_id", "account_id", "user", "tenant"):
                    val = identity.get(key, "")
                    if val:
                        details = f"{key}: {val}"
                        break
            except Exception:
                pass

        status_str = "[green]✓ authenticated[/green]" if ok else "[red]✗ not authenticated[/red]"
        if err:
            details = f"[red]{err[:60]}[/red]"

        types = ", ".join(rt.value for rt in provider.supported_resource_types)
        table.add_row(provider.display_name, status_str, details or "—", types)

    console.print(table)
