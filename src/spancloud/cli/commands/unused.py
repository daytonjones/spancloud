"""CLI commands for unused resource detection."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

import spancloud.providers  # noqa: F401
from spancloud.core.registry import registry

console = Console()
unused_app = typer.Typer(help="Find unused and idle cloud resources.", no_args_is_help=True)


@unused_app.command("scan")
def scan_unused(
    provider_name: str = typer.Argument(
        help="Provider: aws, gcp, vultr, digitalocean, azure, oci."
    ),
    region: str | None = typer.Option(None, "--region", "-r", help="Region to scan."),
    stopped_days: int = typer.Option(
        30, "--stopped-days", help="Days stopped before flagging instances."
    ),
    snapshot_days: int = typer.Option(
        90, "--snapshot-days", help="Days old before flagging snapshots."
    ),
    profile: str | None = typer.Option(
        None, "--profile", "-P", help="AWS profile for multi-account access."
    ),
) -> None:
    """Scan for unused or idle resources that may be wasting money."""
    from spancloud.cli.helpers import apply_aws_profile

    apply_aws_profile(profile)
    provider = registry.get(provider_name)
    if not provider:
        console.print(f"[red]Unknown provider:[/red] '{provider_name}'")
        raise typer.Exit(code=1)

    async def _fetch():
        await provider.authenticate()

        if provider_name == "aws":
            from spancloud.providers.aws.unused import AWSUnusedDetector
            detector = AWSUnusedDetector(provider._auth)
        elif provider_name == "gcp":
            from spancloud.providers.gcp.unused import GCPUnusedDetector
            detector = GCPUnusedDetector(provider._auth)
        elif provider_name == "vultr":
            from spancloud.providers.vultr.unused import VultrUnusedDetector
            detector = VultrUnusedDetector(provider._auth)
        elif provider_name == "digitalocean":
            from spancloud.providers.digitalocean.unused import (
                DigitalOceanUnusedDetector,
            )
            detector = DigitalOceanUnusedDetector(provider._auth)
        elif provider_name == "azure":
            from spancloud.providers.azure.unused import AzureUnusedDetector
            detector = AzureUnusedDetector(provider._auth)
        elif provider_name == "oci":
            from spancloud.providers.oci.unused import OCIUnusedDetector
            detector = OCIUnusedDetector(provider._auth)
        elif provider_name == "alibaba":
            from spancloud.providers.alibaba.unused import (
                AlibabaUnusedDetector,
            )
            detector = AlibabaUnusedDetector(provider._auth)
        else:
            console.print(f"[yellow]Unused detection not available for {provider_name}[/yellow]")
            raise typer.Exit(code=1)

        return await detector.scan(
            region=region,
            stopped_days_threshold=stopped_days,
            snapshot_days_threshold=snapshot_days,
        )

    scan_desc = region or "default region"
    with console.status(
        f"[bold cyan]Scanning {provider.display_name} for unused resources ({scan_desc})..."
    ):
        try:
            report = asyncio.run(_fetch())
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    if not report.resources:
        console.print(
            f"[bold green]No unused resources found in {provider.display_name}![/bold green]"
        )
        return

    console.print(
        f"\n[bold]{provider.display_name} Unused Resources[/bold]"
        f"  —  {report.total_count:,} item(s) found"
    )

    # Potential monthly savings banner
    total_savings = report.total_estimated_monthly_savings
    unestimated = report.unestimated_count
    if total_savings > 0 or unestimated > 0:
        savings_line = (
            f"[bold green]Potential monthly savings: "
            f"${total_savings:,.2f}/mo[/bold green]"
            if total_savings > 0
            else "[dim]No parseable $ estimates.[/dim]"
        )
        if unestimated:
            savings_line += (
                f"  [dim]({unestimated:,} item(s) without a $ estimate "
                "— actual savings may be higher)[/dim]"
            )
        console.print(savings_line)

    table = Table(
        title="Unused Resources",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Type")
    table.add_column("Resource")
    table.add_column("Region")
    table.add_column("Reason")
    table.add_column("Est. Savings", justify="right")

    # Group by type for readability
    by_type: dict[str, list] = {}
    for res in report.resources:
        by_type.setdefault(res.resource_type, []).append(res)

    for resource_type in sorted(by_type):
        for res in by_type[resource_type]:
            table.add_row(
                res.resource_type,
                res.resource_name or res.resource_id,
                res.region or "—",
                res.reason,
                res.estimated_monthly_savings or "—",
            )

    console.print(table)

    # Total potential savings
    savings_items = [r for r in report.resources if r.estimated_monthly_savings]
    if savings_items:
        console.print(
            f"\n[dim]{len(savings_items):,} resource(s) with estimated savings. "
            f"Review each before deleting.[/dim]"
        )
