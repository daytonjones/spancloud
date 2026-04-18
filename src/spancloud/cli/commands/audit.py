"""CLI commands for security auditing."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

import spancloud.providers  # noqa: F401
from spancloud.core.registry import registry

console = Console()
audit_app = typer.Typer(help="Run security audits on cloud infrastructure.", no_args_is_help=True)


@audit_app.command("run")
def run_audit(
    provider_name: str = typer.Argument(
        help="Provider: aws, gcp, vultr, digitalocean, azure, oci, alibaba."
    ),
    region: str | None = typer.Option(None, "--region", "-r", help="Region to scan."),
    profile: str | None = typer.Option(
        None, "--profile", "-P", help="AWS profile for multi-account access."
    ),
) -> None:
    """Run a security audit on a cloud provider."""
    from spancloud.cli.helpers import apply_aws_profile

    apply_aws_profile(profile)
    provider = registry.get(provider_name)
    if not provider:
        console.print(f"[red]Unknown provider:[/red] '{provider_name}'")
        raise typer.Exit(code=1)

    async def _fetch():
        await provider.authenticate()

        if provider_name == "aws":
            from spancloud.providers.aws.security import AWSSecurityAuditor
            auditor = AWSSecurityAuditor(provider._auth)
        elif provider_name == "gcp":
            from spancloud.providers.gcp.security import GCPSecurityAuditor
            auditor = GCPSecurityAuditor(provider._auth)
        elif provider_name == "vultr":
            from spancloud.providers.vultr.security import VultrSecurityAuditor
            auditor = VultrSecurityAuditor(provider._auth)
        elif provider_name == "digitalocean":
            from spancloud.providers.digitalocean.security import (
                DigitalOceanSecurityAuditor,
            )
            auditor = DigitalOceanSecurityAuditor(provider._auth)
        elif provider_name == "azure":
            from spancloud.providers.azure.security import AzureSecurityAuditor
            auditor = AzureSecurityAuditor(provider._auth)
        elif provider_name == "oci":
            from spancloud.providers.oci.security import OCISecurityAuditor
            auditor = OCISecurityAuditor(provider._auth)
        elif provider_name == "alibaba":
            from spancloud.providers.alibaba.security import (
                AlibabaSecurityAuditor,
            )
            auditor = AlibabaSecurityAuditor(provider._auth)
        else:
            console.print(f"[yellow]Security audit not available for {provider_name}[/yellow]")
            raise typer.Exit(code=1)

        return await auditor.run_audit(region=region)

    scan_desc = region or "default region"
    with console.status(
        f"[bold cyan]Running security audit on {provider.display_name} ({scan_desc})..."
    ):
        try:
            result = asyncio.run(_fetch())
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    if not result.findings:
        console.print(
            f"[bold green]No security issues found in {provider.display_name}![/bold green]"
        )
        return

    # Summary
    console.print(f"\n[bold]{provider.display_name} Security Audit[/bold]  —  {result.summary}")

    # Severity color map
    severity_colors = {
        "critical": "bold red",
        "high": "red",
        "medium": "yellow",
        "low": "dim yellow",
        "info": "dim",
    }

    # Findings table
    table = Table(
        title=f"{len(result.findings):,} Finding(s)",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Severity", width=10)
    table.add_column("Resource")
    table.add_column("Issue")
    table.add_column("Recommendation")

    # Sort by severity: critical first
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    sorted_findings = sorted(
        result.findings,
        key=lambda f: severity_order.get(f.severity.value, 5),
    )

    for finding in sorted_findings:
        color = severity_colors.get(finding.severity.value, "white")
        table.add_row(
            f"[{color}]{finding.severity.value.upper()}[/{color}]",
            f"{finding.resource_type}/{finding.resource_id}"
            + (f" ({finding.region})" if finding.region else ""),
            finding.title,
            finding.recommendation,
        )

    console.print(table)
