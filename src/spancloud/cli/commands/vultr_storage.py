"""CLI commands for Vultr storage details."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

import spancloud.providers  # noqa: F401
from spancloud.core.registry import registry

console = Console()
vultr_app = typer.Typer(
    help="Vultr storage details.", no_args_is_help=True
)


@vultr_app.command("block-info")
def block_info(
    block_id: str = typer.Argument(help="Block storage ID."),
) -> None:
    """Show detailed information about a Vultr block storage volume."""
    provider = registry.get("vultr")
    if not provider:
        console.print("[red]Vultr provider not available.[/red]")
        raise typer.Exit(code=1)

    async def _fetch():
        await provider.authenticate()
        from spancloud.providers.vultr.storage_details import (
            VultrStorageDetailAnalyzer,
        )

        analyzer = VultrStorageDetailAnalyzer(provider._auth)
        return await analyzer.get_block_details(block_id)

    with console.status(f"[bold cyan]Fetching block storage '{block_id}'..."):
        try:
            details = asyncio.run(_fetch())
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    table = Table(
        title=f"Vultr Block Storage: {details.label or details.id}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Property", style="bold")
    table.add_column("Value")

    table.add_row("ID", details.id)
    table.add_row("Label", details.label or "—")
    table.add_row("Region", details.region or "—")
    table.add_row("Size", f"{details.size_gb} GB")
    table.add_row("Status", details.status or "—")
    table.add_row("Type", details.block_type or "—")
    table.add_row("Mount ID", details.mount_id or "—")
    table.add_row("Attached To", details.attached_to or "not attached")
    table.add_row("Cost", f"${details.cost}/mo" if details.cost else "—")
    table.add_row("Created", details.date_created or "—")

    console.print(table)


@vultr_app.command("object-info")
def object_info(
    obj_id: str = typer.Argument(help="Object storage ID."),
) -> None:
    """Show detailed information about a Vultr object storage subscription."""
    provider = registry.get("vultr")
    if not provider:
        console.print("[red]Vultr provider not available.[/red]")
        raise typer.Exit(code=1)

    async def _fetch():
        await provider.authenticate()
        from spancloud.providers.vultr.storage_details import (
            VultrStorageDetailAnalyzer,
        )

        analyzer = VultrStorageDetailAnalyzer(provider._auth)
        return await analyzer.get_object_details(obj_id)

    with console.status(f"[bold cyan]Fetching object storage '{obj_id}'..."):
        try:
            details = asyncio.run(_fetch())
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    table = Table(
        title=f"Vultr Object Storage: {details.label or details.id}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Property", style="bold")
    table.add_column("Value")

    table.add_row("ID", details.id)
    table.add_row("Label", details.label or "—")
    table.add_row("Region", details.region or "—")
    table.add_row("Status", details.status or "—")
    table.add_row("S3 Hostname", details.s3_hostname or "—")
    table.add_row("S3 Access Key", details.s3_access_key or "—")
    table.add_row("Created", details.date_created or "—")

    console.print(table)
