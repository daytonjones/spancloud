"""CLI commands for cloud monitoring — alarms/alerts and resource metrics."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

import spancloud.providers  # noqa: F401
from spancloud.core.registry import registry

console = Console()
monitor_app = typer.Typer(
    help="View monitoring alarms/alerts and resource metrics.",
    no_args_is_help=True,
)


@monitor_app.command("alerts")
def list_alerts(
    provider_name: str = typer.Argument(
        default="aws",
        help="Provider name (aws, gcp, digitalocean, azure).",
    ),
    region: str | None = typer.Option(None, "--region", "-r", help="Region."),
    state: str | None = typer.Option(
        None, "--state", "-s",
        help="Filter by state (AWS: ALARM/OK/INSUFFICIENT_DATA).",
    ),
    profile: str | None = typer.Option(
        None, "--profile", "-P", help="AWS profile for multi-account access."
    ),
) -> None:
    """List monitoring alerts/alarms.

    AWS CloudWatch alarms include live state (ALARM/OK/INSUFFICIENT_DATA).
    GCP, DigitalOcean, and Azure report alert *policies* (enabled/disabled).
    Vultr is not supported — no public alerts API.
    """
    from spancloud.cli.helpers import apply_aws_profile

    apply_aws_profile(profile)
    provider = registry.get(provider_name)
    if not provider:
        console.print(f"[red]Unknown provider:[/red] '{provider_name}'")
        raise typer.Exit(code=1)

    async def _fetch():
        await provider.authenticate()

        if provider_name == "aws":
            from spancloud.providers.aws.cloudwatch import CloudWatchAnalyzer

            analyzer = CloudWatchAnalyzer(provider._auth)
            return "aws", await analyzer.list_alarms(
                region=region, state_filter=state
            )
        elif provider_name == "gcp":
            from spancloud.providers.gcp.monitoring import CloudMonitoringAnalyzer

            analyzer = CloudMonitoringAnalyzer(provider._auth)
            return "policies", await analyzer.list_alert_policies()
        elif provider_name == "digitalocean":
            from spancloud.providers.digitalocean.monitoring import (
                DigitalOceanMonitoringAnalyzer,
            )

            analyzer = DigitalOceanMonitoringAnalyzer(provider._auth)
            return "policies", await analyzer.list_alert_policies()
        elif provider_name == "azure":
            from spancloud.providers.azure.monitoring import (
                AzureMonitoringAnalyzer,
            )

            analyzer = AzureMonitoringAnalyzer(provider._auth)
            return "policies", await analyzer.list_alert_policies()
        elif provider_name == "oci":
            from spancloud.providers.oci.monitoring import (
                OCIMonitoringAnalyzer,
            )

            analyzer = OCIMonitoringAnalyzer(provider._auth)
            return "policies", await analyzer.list_alert_policies()
        elif provider_name == "alibaba":
            from spancloud.providers.alibaba.monitoring import (
                AlibabaMonitoringAnalyzer,
            )

            analyzer = AlibabaMonitoringAnalyzer(provider._auth)
            return "policies", await analyzer.list_alert_policies()
        else:
            console.print(
                f"[yellow]Monitoring not available for {provider_name}.[/yellow]"
            )
            if provider_name == "vultr":
                console.print(
                    "[dim]Vultr's monitoring lives in the dashboard only; "
                    "no public alerts API.[/dim]"
                )
            raise typer.Exit(code=1)

    with console.status(
        f"[bold cyan]Fetching {provider.display_name} alerts..."
    ):
        try:
            prov, alerts = asyncio.run(_fetch())
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    if not alerts:
        console.print("[green]No alerts found.[/green]")
        return

    if prov == "aws":
        _render_aws_alarms(alerts)
    else:
        _render_policy_alerts(alerts, provider.display_name)


def _render_aws_alarms(alarms: list) -> None:
    """Render AWS CloudWatch alarms."""
    state_colors = {
        "ALARM": "bold red",
        "OK": "green",
        "INSUFFICIENT_DATA": "yellow",
    }

    table = Table(
        title=f"CloudWatch Alarms ({len(alarms):,})",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("State", width=18)
    table.add_column("Name")
    table.add_column("Metric")
    table.add_column("Threshold")
    table.add_column("Resource")

    for alarm in alarms:
        color = state_colors.get(alarm.state, "white")
        resource = ", ".join(
            f"{k}={v}" for k, v in alarm.dimensions.items()
        ) or "—"

        table.add_row(
            f"[{color}]{alarm.state}[/{color}]",
            alarm.name,
            (
                f"{alarm.namespace}/{alarm.metric_name}"
                if alarm.metric_name
                else "composite"
            ),
            alarm.threshold or "—",
            resource,
        )

    console.print(table)


def _render_policy_alerts(alerts: list, provider_label: str) -> None:
    """Render alert policies (GCP / DigitalOcean / Azure)."""
    table = Table(
        title=f"{provider_label} Alert Policies ({len(alerts):,})",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Enabled", width=8)
    table.add_column("Name")
    table.add_column("Conditions")
    table.add_column("Channels")
    table.add_column("Combiner/Type")

    for alert in alerts:
        enabled_color = "green" if alert.enabled else "dim"
        label = "ON" if alert.enabled else "OFF"
        table.add_row(
            f"[{enabled_color}]{label}[/{enabled_color}]",
            alert.display_name or alert.name,
            str(alert.conditions_count),
            str(alert.notification_channels),
            alert.combiner or "—",
        )

    console.print(table)


@monitor_app.command("metrics")
def show_metrics(
    instance_id: str = typer.Argument(help="Instance ID or name."),
    provider_name: str = typer.Option(
        "aws", "--provider", "-p",
        help="Provider: aws, gcp, azure, digitalocean, oci.",
    ),
    region: str | None = typer.Option(
        None, "--region", "-r",
        help="Region or zone. Required for GCP (zone) and OCI. For Azure, pass resource group here.",
    ),
    hours: int = typer.Option(1, "--hours", "-H", help="Hours of data."),
    profile: str | None = typer.Option(
        None, "--profile", "-P", help="AWS profile for multi-account access."
    ),
) -> None:
    """Show key metrics for a compute instance (CPU, network, disk)."""
    from spancloud.cli.helpers import apply_aws_profile

    apply_aws_profile(profile)
    provider = registry.get(provider_name)
    if not provider:
        console.print(f"[red]Unknown provider:[/red] '{provider_name}'")
        raise typer.Exit(code=1)

    async def _fetch():
        await provider.authenticate()

        if provider_name == "aws":
            from spancloud.providers.aws.cloudwatch import CloudWatchAnalyzer
            return await CloudWatchAnalyzer(provider._auth).get_instance_metrics(
                instance_id, region=region, hours=hours
            )
        elif provider_name == "gcp":
            from spancloud.providers.gcp.monitoring import CloudMonitoringAnalyzer
            if not region:
                console.print(
                    "[red]Zone is required for GCP metrics "
                    "(--region us-central1-a)[/red]"
                )
                raise typer.Exit(code=1)
            return await CloudMonitoringAnalyzer(provider._auth).get_instance_metrics(
                instance_id, zone=region, hours=hours
            )
        elif provider_name == "digitalocean":
            from spancloud.providers.digitalocean.monitoring import DigitalOceanMonitoringAnalyzer
            return await DigitalOceanMonitoringAnalyzer(provider._auth).get_instance_metrics(
                instance_id, hours=hours
            )
        elif provider_name == "azure":
            from spancloud.providers.azure.monitoring import AzureMonitoringAnalyzer
            return await AzureMonitoringAnalyzer(provider._auth).get_instance_metrics(
                instance_id, resource_group=region, hours=hours
            )
        elif provider_name == "oci":
            from spancloud.providers.oci.monitoring import OCIMonitoringAnalyzer
            return await OCIMonitoringAnalyzer(provider._auth).get_instance_metrics(
                instance_id, region=region, hours=hours
            )
        else:
            console.print(
                f"[yellow]Metrics not available for {provider_name}[/yellow]"
            )
            raise typer.Exit(code=1)

    with console.status(
        f"[bold cyan]Fetching metrics for {instance_id}..."
    ):
        try:
            result = asyncio.run(_fetch())
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    if not result.metrics:
        console.print(f"[yellow]No metrics found for {instance_id}.[/yellow]")
        return

    console.print(
        f"\n[bold]Metrics for {instance_id}[/bold]  (last {hours}h)"
    )

    for metric_name, points in result.metrics.items():
        if not points:
            continue

        latest = points[-1]
        avg = sum(p.value for p in points) / len(points)
        max_val = max(p.value for p in points)
        min_val = min(p.value for p in points)

        console.print(
            f"\n  [cyan]{metric_name}[/cyan]: "
            f"latest={latest.value:,.2f}, "
            f"avg={avg:,.2f}, "
            f"min={min_val:,.2f}, "
            f"max={max_val:,.2f} "
            f"[dim]({len(points):,} points)[/dim]"
        )

        # Mini sparkline
        if len(points) > 1:
            spark_chars = "▁▂▃▄▅▆▇█"
            vals = [p.value for p in points[-20:]]
            vmin, vmax = min(vals), max(vals)
            spread = vmax - vmin if vmax != vmin else 1
            spark = "".join(
                spark_chars[min(int((v - vmin) / spread * 7), 7)]
                for v in vals
            )
            console.print(f"  [dim]{spark}[/dim]")
