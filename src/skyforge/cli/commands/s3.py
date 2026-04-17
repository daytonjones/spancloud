"""CLI commands for S3 bucket details."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import skyforge.providers  # noqa: F401
from skyforge.core.registry import registry

console = Console()
s3_app = typer.Typer(help="S3 bucket management and details.", no_args_is_help=True)


@s3_app.command("info")
def bucket_info(
    bucket_name: str = typer.Argument(help="S3 bucket name."),
) -> None:
    """Show detailed information about an S3 bucket."""
    provider = registry.get("aws")
    if not provider:
        console.print("[red]AWS provider not available.[/red]")
        raise typer.Exit(code=1)

    async def _fetch():
        await provider.authenticate()
        from skyforge.providers.aws.s3_details import S3DetailAnalyzer

        analyzer = S3DetailAnalyzer(provider._auth)
        return await analyzer.get_bucket_details(bucket_name)

    with console.status(f"[bold cyan]Fetching details for '{bucket_name}'..."):
        try:
            details = asyncio.run(_fetch())
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    # Overview
    table = Table(
        title=f"S3 Bucket: {details.name}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Property", style="bold")
    table.add_column("Value")

    table.add_row("Region", details.region or "—")
    table.add_row("Versioning", details.versioning or "Disabled")
    table.add_row("Encryption", details.encryption or "None")
    table.add_row("Object Count", details.object_count or "—")
    table.add_row("Total Size", details.total_size or "—")
    table.add_row("Policy", details.policy_summary or "—")
    table.add_row(
        "Logging",
        f"→ {details.logging_target}" if details.logging_enabled else "Disabled",
    )

    console.print(table)

    # Public access block
    if details.public_access_block:
        pab_table = Table(
            title="Public Access Block",
            show_header=True,
            header_style="bold cyan",
        )
        pab_table.add_column("Setting")
        pab_table.add_column("Status")

        for key, val in details.public_access_block.items():
            color = "green" if val else "red"
            label = key.replace("_", " ").title()
            pab_table.add_row(label, f"[{color}]{val}[/{color}]")

        console.print(pab_table)

    # Lifecycle rules
    if details.lifecycle_rules:
        lc_table = Table(
            title=f"Lifecycle Rules ({len(details.lifecycle_rules)})",
            show_header=True,
            header_style="bold cyan",
        )
        lc_table.add_column("ID")
        lc_table.add_column("Status")
        lc_table.add_column("Prefix")
        lc_table.add_column("Transitions")
        lc_table.add_column("Expiration")

        for rule in details.lifecycle_rules:
            status_color = "green" if rule.status == "Enabled" else "dim"
            transitions = "; ".join(rule.transitions) if rule.transitions else "—"
            expiration = f"{rule.expiration_days}d" if rule.expiration_days else "—"

            lc_table.add_row(
                rule.id or "—",
                f"[{status_color}]{rule.status}[/{status_color}]",
                rule.prefix or "*",
                transitions,
                expiration,
            )

        console.print(lc_table)
    else:
        console.print(Panel("[dim]No lifecycle rules configured.[/dim]"))
