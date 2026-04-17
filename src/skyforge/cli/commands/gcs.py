"""CLI commands for GCS bucket details."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import skyforge.providers  # noqa: F401
from skyforge.core.registry import registry

console = Console()
gcs_app = typer.Typer(help="GCS bucket management and details.", no_args_is_help=True)


@gcs_app.command("info")
def bucket_info(
    bucket_name: str = typer.Argument(help="GCS bucket name."),
) -> None:
    """Show detailed information about a GCS bucket."""
    provider = registry.get("gcp")
    if not provider:
        console.print("[red]GCP provider not available.[/red]")
        raise typer.Exit(code=1)

    async def _fetch():
        await provider.authenticate()
        from skyforge.providers.gcp.gcs_details import GCSDetailAnalyzer

        analyzer = GCSDetailAnalyzer(provider._auth)
        return await analyzer.get_bucket_details(bucket_name)

    with console.status(f"[bold cyan]Fetching details for '{bucket_name}'..."):
        try:
            details = asyncio.run(_fetch())
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    # Overview
    table = Table(
        title=f"GCS Bucket: {details.name}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Property", style="bold")
    table.add_column("Value")

    table.add_row("Location", f"{details.location} ({details.location_type})")
    table.add_row("Storage Class", details.storage_class or "—")
    table.add_row("Versioning", "Enabled" if details.versioning else "Disabled")
    table.add_row("Encryption", details.encryption)
    table.add_row("Object Count", details.object_count or "—")
    table.add_row("Total Size", details.total_size or "—")
    table.add_row(
        "Public Access Prevention",
        details.public_access_prevention or "—",
    )
    table.add_row(
        "Uniform Access",
        "Enabled" if details.uniform_access else "Disabled",
    )
    table.add_row(
        "Logging",
        f"→ {details.logging_bucket}" if details.logging_bucket else "Disabled",
    )
    table.add_row("Created", details.created or "—")

    if details.labels:
        label_str = ", ".join(f"{k}={v}" for k, v in details.labels.items())
        table.add_row("Labels", label_str)

    console.print(table)

    # IAM bindings
    if details.iam_bindings:
        iam_table = Table(
            title=f"IAM Bindings ({len(details.iam_bindings)})",
            show_header=True,
            header_style="bold cyan",
        )
        iam_table.add_column("Binding")

        for binding in details.iam_bindings[:20]:
            iam_table.add_row(binding)

        console.print(iam_table)

    # Lifecycle rules
    if details.lifecycle_rules:
        lc_table = Table(
            title=f"Lifecycle Rules ({len(details.lifecycle_rules)})",
            show_header=True,
            header_style="bold cyan",
        )
        lc_table.add_column("Action")
        lc_table.add_column("Storage Class")
        lc_table.add_column("Condition")

        for rule in details.lifecycle_rules:
            lc_table.add_row(
                rule.action,
                rule.storage_class or "—",
                rule.condition or "—",
            )

        console.print(lc_table)
    else:
        console.print(Panel("[dim]No lifecycle rules configured.[/dim]"))
