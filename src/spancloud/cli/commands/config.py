"""CLI commands for managing Spancloud configuration."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

console = Console()
config_app = typer.Typer(help="Manage Spancloud configuration.", no_args_is_help=True)


@config_app.command("sidebar")
def manage_sidebar(
    provider_name: str = typer.Argument(
        help="Provider (aws, gcp, vultr, digitalocean, azure, oci)."
    ),
    add: str | None = typer.Option(
        None, "--add", help="Add a service to the sidebar by name."
    ),
    remove: str | None = typer.Option(
        None, "--remove", help="Remove a service from the sidebar by name."
    ),
    reset: bool = typer.Option(
        False, "--reset", help="Reset sidebar to defaults."
    ),
    available: bool = typer.Option(
        False, "--available", help="Show all available services."
    ),
) -> None:
    """View or modify which resource types appear in the TUI sidebar."""
    from spancloud.config.sidebar import (
        get_available_services,
        get_sidebar_items,
        reset_sidebar,
        set_sidebar_items,
    )

    if reset:
        reset_sidebar(provider_name)
        console.print(f"[green]Sidebar reset to defaults for {provider_name}.[/green]")
        return

    if available:
        services = get_available_services(provider_name)
        current = {s["name"] for s in get_sidebar_items(provider_name)}

        table = Table(
            title=f"Available Services for {provider_name}",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("", width=2)
        table.add_column("Name")
        table.add_column("Label")
        table.add_column("Category")

        for svc in services:
            in_sidebar = svc["name"] in current
            marker = "[green]\u2714[/green]" if in_sidebar else ""
            table.add_row(marker, svc["name"], svc["label"], svc["type"])

        console.print(table)
        console.print(
            "\n[dim]\u2714 = in sidebar. "
            "Use --add <name> or --remove <name> to modify.[/dim]"
        )
        return

    if add:
        items = get_sidebar_items(provider_name)
        all_services = {s["name"]: s for s in get_available_services(provider_name)}

        if add not in all_services:
            console.print(f"[red]Unknown service:[/red] '{add}'")
            console.print(
                f"[dim]Run: spancloud config sidebar {provider_name} "
                f"--available[/dim]"
            )
            raise typer.Exit(code=1)

        if any(s["name"] == add for s in items):
            console.print(f"[yellow]'{add}' is already in the sidebar.[/yellow]")
            return

        items.append(all_services[add])
        set_sidebar_items(provider_name, items)
        console.print(f"[green]Added '{add}' to {provider_name} sidebar.[/green]")
        return

    if remove:
        items = get_sidebar_items(provider_name)
        new_items = [s for s in items if s["name"] != remove]
        if len(new_items) == len(items):
            console.print(f"[yellow]'{remove}' not found in sidebar.[/yellow]")
            return
        set_sidebar_items(provider_name, new_items)
        console.print(
            f"[green]Removed '{remove}' from {provider_name} sidebar.[/green]"
        )
        return

    # Default: show current sidebar
    items = get_sidebar_items(provider_name)
    table = Table(
        title=f"{provider_name} Sidebar ({len(items)} items)",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", width=3)
    table.add_column("Name")
    table.add_column("Label")
    table.add_column("Category")

    for i, svc in enumerate(items, 1):
        table.add_row(str(i), svc["name"], svc["label"], svc["type"])

    console.print(table)
    console.print(
        "\n[dim]Use --add/--remove to modify, "
        "--available to see all options, "
        "--reset for defaults.[/dim]"
    )


@config_app.command("providers")
def manage_providers(
    enable: str | None = typer.Option(
        None, "--enable", help="Enable a provider tab."
    ),
    disable: str | None = typer.Option(
        None, "--disable", help="Disable a provider tab."
    ),
) -> None:
    """View or toggle which providers appear as TUI tabs."""
    import spancloud.providers  # noqa: F401
    from spancloud.config.sidebar import (
        get_enabled_providers,
        set_enabled_providers,
    )
    from spancloud.core.registry import registry

    if enable:
        enabled = get_enabled_providers()
        enabled.add(enable)
        set_enabled_providers(enabled)
        console.print(f"[green]Enabled '{enable}'.[/green]")
        return

    if disable:
        enabled = get_enabled_providers()
        enabled.discard(disable)
        set_enabled_providers(enabled)
        console.print(f"[yellow]Disabled '{disable}'.[/yellow]")
        return

    # Show current state
    enabled = get_enabled_providers()
    providers = registry.list_providers()

    table = Table(
        title="Provider Tabs",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("", width=3)
    table.add_column("Provider")
    table.add_column("Status")

    for p in providers:
        is_on = p.name in enabled
        is_impl = bool(p.supported_resource_types)
        marker = "[green]\u2714[/green]" if is_on else ""
        status = (
            "[green]enabled[/green]" if is_on
            else "[dim]disabled[/dim]" if is_impl
            else "[dim]not implemented[/dim]"
        )
        table.add_row(marker, f"[bold]{p.display_name}[/bold] ({p.name})", status)

    console.print(table)
    console.print(
        "\n[dim]Use --enable/--disable to toggle. "
        "Changes apply on next TUI launch.[/dim]"
    )
