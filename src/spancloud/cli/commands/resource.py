"""CLI commands for discovering and managing cloud resources."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

# Trigger provider registration.
import spancloud.providers  # noqa: F401
from spancloud.core.exceptions import ProviderError, ProviderNotImplementedError
from spancloud.core.registry import registry
from spancloud.core.resource import ResourceType

console = Console()
resource_app = typer.Typer(help="Discover and manage cloud resources.", no_args_is_help=True)


def _resource_type_callback(value: str) -> str:
    """Validate the resource type argument."""
    valid = [rt.value for rt in ResourceType]
    if value not in valid:
        raise typer.BadParameter(f"Must be one of: {', '.join(valid)}")
    return value


def _parse_tags(tag_list: list[str] | None) -> dict[str, str] | None:
    """Parse --tag key=value arguments into a dict."""
    if not tag_list:
        return None
    tags: dict[str, str] = {}
    for item in tag_list:
        if "=" not in item:
            raise typer.BadParameter(f"Tag must be in key=value format, got: '{item}'")
        key, _, value = item.partition("=")
        tags[key] = value
    return tags


@resource_app.command("list")
def list_resources(
    provider_name: str = typer.Argument(
        help="Provider: aws, gcp, vultr, digitalocean, azure, oci."
    ),
    resource_type: str = typer.Argument(
        help="Resource type: compute, storage, network, database, serverless, "
        "load_balancer, container, dns, iam, other.",
        callback=_resource_type_callback,
    ),
    region: str | None = typer.Option(None, "--region", "-r", help="Region filter."),
    all_regions: bool = typer.Option(
        False, "--all-regions", "-A", help="Scan all enabled regions (AWS)."
    ),
    tag: list[str] | None = typer.Option(  # noqa: B008
        None, "--tag", "-t", help="Filter by tag (repeatable, format: key=value)."
    ),
    profile: str | None = typer.Option(
        None, "--profile", "-P", help="AWS profile for multi-account access."
    ),
    export: str | None = typer.Option(
        None, "--export", "-e",
        help="Export format: json, csv, or yaml. Outputs to stdout.",
    ),
    output_file: str | None = typer.Option(
        None, "--output", "-o", help="Write export to file instead of stdout."
    ),
) -> None:
    """List resources of a given type from a provider."""
    from spancloud.cli.helpers import apply_aws_profile

    apply_aws_profile(profile)
    provider = registry.get(provider_name)
    if not provider:
        console.print(f"[red]Unknown provider:[/red] '{provider_name}'")
        console.print(f"Available: {', '.join(registry.provider_names)}")
        raise typer.Exit(code=1)

    rt = ResourceType(resource_type)
    tags = _parse_tags(tag)

    # --all-regions overrides --region
    effective_region = "*" if all_regions else region

    scan_desc = "all regions" if all_regions else (region or "default region")

    async def _fetch() -> list:
        await provider.authenticate()
        return await provider.list_resources(rt, region=effective_region, tags=tags)

    with console.status(
        f"[bold cyan]Fetching {resource_type} from {provider.display_name} ({scan_desc})..."
    ):
        try:
            resources = asyncio.run(_fetch())
        except ProviderNotImplementedError as exc:
            console.print(f"[yellow]{exc}[/yellow]")
            raise typer.Exit(code=1) from exc
        except ProviderError as exc:
            console.print(f"[red]Provider error:[/red] {exc}")
            raise typer.Exit(code=1) from exc
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    if not resources:
        console.print(f"[yellow]No {resource_type} resources found.[/yellow]")
        return

    # Export mode — output data and exit
    if export:
        from spancloud.core.export import to_csv, to_json, to_yaml

        format_map = {"json": to_json, "csv": to_csv, "yaml": to_yaml}
        formatter = format_map.get(export.lower())
        if not formatter:
            console.print(
                f"[red]Unknown format:[/red] '{export}'. Use: json, csv, yaml"
            )
            raise typer.Exit(code=1)

        result = formatter(resources)
        if output_file:
            from pathlib import Path

            Path(output_file).write_text(result)
            console.print(
                f"[green]Exported {len(resources):,} resource(s) to "
                f"{output_file}[/green]"
            )
        else:
            # Print raw to stdout (no rich formatting)
            import sys

            sys.stdout.write(result)
        return

    # Table display mode
    title = f"{provider.display_name} — {resource_type.title()} Resources"
    if all_regions:
        title += " (all regions)"
    elif region:
        title += f" ({region})"

    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Region")
    table.add_column("State")
    table.add_column("Info")

    for r in resources:
        state_color = {
            "running": "green",
            "stopped": "red",
            "pending": "yellow",
            "terminated": "dim red",
            "error": "bold red",
        }.get(r.state.value, "white")

        subtype = r.metadata.get("resource_subtype", "")
        tag_str = ", ".join(f"{k}={v}" for k, v in sorted(r.tags.items())[:3])
        if len(r.tags) > 3:
            tag_str += f" (+{len(r.tags) - 3} more)"
        info = subtype or tag_str or "—"

        table.add_row(
            r.id,
            r.name,
            r.region,
            f"[{state_color}]{r.state.value}[/{state_color}]",
            info,
        )

    console.print(table)
    console.print(f"\n[dim]{len(resources):,} resource(s) found.[/dim]")


@resource_app.command("show")
def show_resource(
    provider_name: str = typer.Argument(help="Provider name."),
    resource_type: str = typer.Argument(
        help="Resource type.",
        callback=_resource_type_callback,
    ),
    resource_id: str = typer.Argument(help="Resource ID."),
    region: str | None = typer.Option(None, "--region", "-r", help="Region or zone."),
    profile: str | None = typer.Option(
        None, "--profile", "-P", help="AWS profile for multi-account access."
    ),
) -> None:
    """Show detailed information about a single resource."""
    from spancloud.cli.helpers import apply_aws_profile

    apply_aws_profile(profile)
    provider = registry.get(provider_name)
    if not provider:
        console.print(f"[red]Unknown provider:[/red] '{provider_name}'")
        raise typer.Exit(code=1)

    rt = ResourceType(resource_type)

    async def _fetch():
        await provider.authenticate()
        return await provider.get_resource(rt, resource_id, region=region)

    with console.status(f"[bold cyan]Fetching {resource_id}..."):
        try:
            resource = asyncio.run(_fetch())
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    table = Table(title=str(resource), show_header=True)
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("ID", resource.id)
    table.add_row("Name", resource.name)
    table.add_row("Provider", resource.provider)
    table.add_row("Type", resource.resource_type.value)
    table.add_row("Region", resource.region)
    table.add_row("State", resource.state.value)
    table.add_row("Created", str(resource.created_at) if resource.created_at else "—")

    if resource.tags:
        for k, v in sorted(resource.tags.items()):
            table.add_row(f"Tag: {k}", v)

    if resource.metadata:
        for k, v in sorted(resource.metadata.items()):
            if v:
                table.add_row(f"Meta: {k}", v)

    console.print(table)
