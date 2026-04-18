"""CLI commands for managing cloud providers."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

# Trigger provider registration by importing the providers package.
import spancloud.providers  # noqa: F401
from spancloud.core.registry import registry

console = Console()
provider_app = typer.Typer(help="Manage cloud providers.", no_args_is_help=True)


@provider_app.command("list")
def list_providers() -> None:
    """List all registered cloud providers and their status."""
    providers = registry.list_providers()

    table = Table(title="Cloud Providers", show_header=True, header_style="bold cyan")
    table.add_column("Name", style="bold")
    table.add_column("Display Name")
    table.add_column("Status")
    table.add_column("Resource Types")

    for p in providers:
        has_resources = len(p.supported_resource_types) > 0
        status = "[green]Available[/green]" if has_resources else "[yellow]Stub[/yellow]"
        resource_types = ", ".join(rt.value for rt in p.supported_resource_types) or "—"
        table.add_row(p.name, p.display_name, status, resource_types)

    console.print(table)


@provider_app.command("status")
def provider_status(
    name: str = typer.Argument(
        help="Provider: aws, gcp, vultr, digitalocean, azure, oci, alibaba."
    ),
) -> None:
    """Check authentication status and details for a provider."""
    provider = registry.get(name)
    if not provider:
        console.print(f"[red]Unknown provider:[/red] '{name}'")
        console.print(f"Available: {', '.join(registry.provider_names)}")
        raise typer.Exit(code=1)

    async def _check() -> dict[str, str]:
        await provider.authenticate()
        return await provider.get_status()

    with console.status(f"[bold cyan]Checking {provider.display_name}..."):
        try:
            status = asyncio.run(_check())
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    table = Table(title=f"{provider.display_name} Status", show_header=True)
    table.add_column("Property", style="bold")
    table.add_column("Value")

    for key, value in status.items():
        # Highlight authentication status
        if key == "authenticated":
            value = "[green]Yes[/green]" if value == "True" else "[red]No[/red]"
        table.add_row(key, value)

    console.print(table)
