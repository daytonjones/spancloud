"""CLI commands for cost analysis."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import spancloud.providers  # noqa: F401
from spancloud.core.registry import registry

console = Console()
cost_app = typer.Typer(help="Analyze cloud costs and spending.", no_args_is_help=True)


@cost_app.command("show")
def show_cost(
    provider_name: str = typer.Argument(
        help="Provider: aws, gcp, vultr, digitalocean, azure, oci."
    ),
    days: int = typer.Option(30, "--days", "-d", help="Number of days to analyze."),
    profile: str | None = typer.Option(
        None, "--profile", "-P", help="AWS profile for multi-account access."
    ),
) -> None:
    """Show cost summary for a cloud provider."""
    from spancloud.cli.helpers import apply_aws_profile

    apply_aws_profile(profile)
    provider = registry.get(provider_name)
    if not provider:
        console.print(f"[red]Unknown provider:[/red] '{provider_name}'")
        raise typer.Exit(code=1)

    async def _fetch():
        await provider.authenticate()

        if provider_name == "aws":
            from spancloud.providers.aws.cost import AWSCostAnalyzer
            analyzer = AWSCostAnalyzer(provider._auth)
        elif provider_name == "gcp":
            from spancloud.providers.gcp.cost import GCPCostAnalyzer
            analyzer = GCPCostAnalyzer(provider._auth)
        elif provider_name == "vultr":
            from spancloud.providers.vultr.cost import VultrCostAnalyzer
            analyzer = VultrCostAnalyzer(provider._auth)
        elif provider_name == "digitalocean":
            from spancloud.providers.digitalocean.cost import (
                DigitalOceanCostAnalyzer,
            )
            analyzer = DigitalOceanCostAnalyzer(provider._auth)
        elif provider_name == "azure":
            from spancloud.providers.azure.cost import AzureCostAnalyzer
            analyzer = AzureCostAnalyzer(provider._auth)
        elif provider_name == "oci":
            from spancloud.providers.oci.cost import OCICostAnalyzer
            analyzer = OCICostAnalyzer(provider._auth)
        elif provider_name == "alibaba":
            from spancloud.providers.alibaba.cost import AlibabaCostAnalyzer
            analyzer = AlibabaCostAnalyzer(provider._auth)
        else:
            console.print(f"[yellow]Cost analysis not available for {provider_name}[/yellow]")
            raise typer.Exit(code=1)

        return await analyzer.get_cost_summary(period_days=days)

    with console.status(f"[bold cyan]Analyzing {provider.display_name} costs ({days} days)..."):
        try:
            summary = asyncio.run(_fetch())
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    # Display notes (e.g., GCP setup guidance)
    if summary.notes:
        console.print(Panel(summary.notes, title="Notes", border_style="yellow"))
        if not summary.by_service and summary.total_cost == 0:
            return

    # Cost overview
    console.print(
        f"\n[bold]{provider.display_name} Cost Summary[/bold]"
        f"  ({summary.period_start} to {summary.period_end})"
    )
    if summary.account_id:
        profile_info = ""
        if provider_name == "aws" and hasattr(provider, "_auth"):
            profile_info = f"  Profile: {provider._auth.active_profile}"
        console.print(f"[dim]Account: {summary.account_id}{profile_info}[/dim]")

    console.print(
        f"\n[bold green]Total: ${summary.total_cost:,.2f} {summary.currency}[/bold green]"
    )

    # Per-service breakdown
    if summary.by_service:
        svc_table = Table(title="Cost by Service", show_header=True, header_style="bold cyan")
        svc_table.add_column("Service")
        svc_table.add_column("Cost", justify="right")
        svc_table.add_column("% of Total", justify="right")

        for svc in summary.by_service[:20]:  # Top 20 services
            pct = (
                f"{(svc.cost / summary.total_cost * 100):.1f}%"
                if summary.total_cost > 0
                else "—"
            )
            svc_table.add_row(svc.service, f"${svc.cost:,.2f}", pct)

        console.print(svc_table)

    # Daily trend (last 7 days)
    if summary.daily_costs:
        recent = summary.daily_costs[-7:]
        trend_table = Table(
            title="Daily Cost Trend (last 7 days)",
            show_header=True,
            header_style="bold cyan",
        )
        trend_table.add_column("Date")
        trend_table.add_column("Cost", justify="right")
        trend_table.add_column("Trend")

        for day in recent:
            bar_len = 0
            if summary.total_cost > 0:
                max_daily = max(d.cost for d in recent)
                if max_daily > 0:
                    bar_len = int(float(day.cost / max_daily) * 20)

            bar = "[green]" + "█" * bar_len + "[/green]"
            trend_table.add_row(str(day.date), f"${day.cost:,.2f}", bar)

        console.print(trend_table)
