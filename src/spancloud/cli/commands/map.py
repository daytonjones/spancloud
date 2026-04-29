"""CLI commands for resource relationship mapping."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

import spancloud.providers  # noqa: F401
from spancloud.core.registry import registry

console = Console()
map_app = typer.Typer(help="Map relationships between cloud resources.", no_args_is_help=True)


@map_app.command("show")
def show_map(
    provider_name: str = typer.Argument(
        help="Provider: aws, gcp, vultr, digitalocean, azure, oci."
    ),
    region: str | None = typer.Option(None, "--region", "-r", help="Region to scan."),
    resource_id: str | None = typer.Option(
        None, "--resource", help="Filter to a specific resource ID."
    ),
    tree_view: bool = typer.Option(
        False, "--tree", "-T", help="Display as a tree instead of a table."
    ),
    profile: str | None = typer.Option(
        None, "--profile", "-P", help="AWS profile for multi-account access."
    ),
) -> None:
    """Show resource relationships for a cloud provider."""
    from spancloud.cli.helpers import apply_aws_profile

    apply_aws_profile(profile)
    provider = registry.get(provider_name)
    if not provider:
        console.print(f"[red]Unknown provider:[/red] '{provider_name}'")
        raise typer.Exit(code=1)

    async def _fetch():
        await provider.authenticate()

        if provider_name == "aws":
            from spancloud.providers.aws.relationships import AWSRelationshipMapper
            mapper = AWSRelationshipMapper(provider._auth)
        elif provider_name == "gcp":
            from spancloud.providers.gcp.relationships import GCPRelationshipMapper
            mapper = GCPRelationshipMapper(provider._auth)
        elif provider_name == "vultr":
            from spancloud.providers.vultr.relationships import VultrRelationshipMapper
            mapper = VultrRelationshipMapper(provider._auth)
        elif provider_name == "digitalocean":
            from spancloud.providers.digitalocean.relationships import (
                DigitalOceanRelationshipMapper,
            )
            mapper = DigitalOceanRelationshipMapper(provider._auth)
        elif provider_name == "azure":
            from spancloud.providers.azure.relationships import (
                AzureRelationshipMapper,
            )
            mapper = AzureRelationshipMapper(provider._auth)
        elif provider_name == "oci":
            from spancloud.providers.oci.relationships import (
                OCIRelationshipMapper,
            )
            mapper = OCIRelationshipMapper(provider._auth)
        elif provider_name == "alibaba":
            from spancloud.providers.alibaba.relationships import (
                AlibabaRelationshipMapper,
            )
            mapper = AlibabaRelationshipMapper(provider._auth)
        else:
            console.print(
                f"[yellow]Relationship mapping not available for {provider_name}[/yellow]"
            )
            raise typer.Exit(code=1)

        return await mapper.map_relationships(region=region)

    scan_desc = region or "default region"
    with console.status(
        f"[bold cyan]Mapping {provider.display_name} resource relationships ({scan_desc})..."
    ):
        try:
            rel_map = asyncio.run(_fetch())
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    # Filter to specific resource if requested
    relationships = (
        rel_map.for_resource(resource_id) if resource_id else rel_map.relationships
    )

    if not relationships:
        msg = f"No relationships found in {provider.display_name}"
        if resource_id:
            msg += f" for resource '{resource_id}'"
        console.print(f"[yellow]{msg}[/yellow]")
        return

    console.print(
        f"\n[bold]{provider.display_name} Resource Relationships[/bold]"
        f"  —  {len(relationships):,} relationship(s)"
    )

    if tree_view:
        _render_tree(relationships, resource_id)
    else:
        _render_table(relationships)


def _render_table(relationships: list) -> None:
    """Render relationships as a flat table."""
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Source")
    table.add_column("Relationship")
    table.add_column("Target")
    table.add_column("Type")

    # Sort by source then relationship
    sorted_rels = sorted(relationships, key=lambda r: (r.source_type, r.source_id))

    for rel in sorted_rels:
        source_label = rel.source_name or rel.source_id
        target_label = rel.target_name or rel.target_id

        table.add_row(
            f"[bold]{source_label}[/bold] [dim]({rel.source_type})[/dim]",
            f"[cyan]{rel.relationship.value}[/cyan]",
            f"{target_label} [dim]({rel.target_type})[/dim]",
            rel.target_type,
        )

    console.print(table)


def _render_tree(relationships: list, root_id: str | None = None) -> None:
    """Render relationships as a tree view."""
    # Group by source
    by_source: dict[str, list] = {}
    for rel in relationships:
        key = rel.source_name or rel.source_id
        by_source.setdefault(key, []).append(rel)

    if root_id and root_id in by_source:
        # Single resource tree
        tree = Tree(f"[bold]{root_id}[/bold]")
        for rel in by_source[root_id]:
            target_label = rel.target_name or rel.target_id
            tree.add(
                f"[cyan]{rel.relationship.value}[/cyan] → "
                f"{target_label} [dim]({rel.target_type})[/dim]"
            )
        console.print(tree)
    else:
        # Full tree grouped by source type
        source_types: dict[str, dict[str, list]] = {}
        for source_key, rels in by_source.items():
            stype = rels[0].source_type
            source_types.setdefault(stype, {})[source_key] = rels

        for stype in sorted(source_types):
            type_tree = Tree(f"[bold magenta]{stype}[/bold magenta]")
            for source_key in sorted(source_types[stype]):
                source_branch = type_tree.add(f"[bold]{source_key}[/bold]")
                for rel in source_types[stype][source_key]:
                    target_label = rel.target_name or rel.target_id
                    source_branch.add(
                        f"[cyan]{rel.relationship.value}[/cyan] → "
                        f"{target_label} [dim]({rel.target_type})[/dim]"
                    )
            console.print(type_tree)
