"""CLI commands for AWS multi-account profile management."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

import spancloud.providers  # noqa: F401
from spancloud.core.registry import registry

console = Console()
profile_app = typer.Typer(
    help="Manage AWS profiles for multi-account access.",
    no_args_is_help=True,
)


@profile_app.command("list")
def list_profiles(
    verify: bool = typer.Option(
        False, "--verify", help="Validate each profile via STS (slower)."
    ),
) -> None:
    """List all configured AWS profiles.

    Shows profile name, type (SSO, access keys, assume role),
    region, and optionally validates each against STS.
    """
    from spancloud.providers.aws.auth import AWSAuth

    profiles = AWSAuth.list_configured_profiles()

    if not profiles:
        console.print("[yellow]No AWS profiles found.[/yellow]")
        console.print(
            "[dim]Configure profiles with 'aws configure' or "
            "'spancloud auth login aws'.[/dim]"
        )
        raise typer.Exit(code=0)

    # Get current active profile
    aws_provider = registry.get("aws")
    active = aws_provider._auth.active_profile if aws_provider else ""

    table = Table(
        title=f"AWS Profiles ({len(profiles)})",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("", width=2)  # Active indicator
    table.add_column("Profile")
    table.add_column("Type")
    table.add_column("Region")
    table.add_column("Details")

    if verify:
        table.add_column("Account")
        table.add_column("Status")

    # Validate profiles if requested
    account_info: dict[str, dict[str, str]] = {}
    if verify:
        async def _verify_all():
            results: dict[str, dict[str, str]] = {}
            for prof in profiles:
                name = prof["name"]
                try:
                    import boto3

                    session = boto3.Session(profile_name=name)
                    sts = session.client("sts")
                    identity = await asyncio.to_thread(sts.get_caller_identity)
                    results[name] = {
                        "account": identity.get("Account", ""),
                        "arn": identity.get("Arn", ""),
                        "status": "ok",
                    }
                except Exception as exc:
                    results[name] = {
                        "account": "",
                        "arn": "",
                        "status": str(exc)[:40],
                    }
            return results

        with console.status("[bold cyan]Validating profiles via STS..."):
            account_info = asyncio.run(_verify_all())

    for prof in profiles:
        name = prof["name"]
        is_active = name == active or (active == "(default)" and name == "default")
        marker = "[green]>[/green]" if is_active else ""

        name_style = "[bold green]" if is_active else "[bold]"
        name_display = f"{name_style}{name}[/]"

        prof_type = prof.get("type", "unknown")
        type_colors = {
            "sso": "cyan",
            "access_keys": "yellow",
            "assume_role": "magenta",
        }
        type_color = type_colors.get(prof_type, "white")
        type_display = f"[{type_color}]{prof_type}[/{type_color}]"

        # Build details from available info
        details_parts: list[str] = []
        if prof.get("sso_account"):
            details_parts.append(f"SSO acct: {prof['sso_account']}")
        if prof.get("role_arn"):
            role_short = prof["role_arn"].rsplit("/", 1)[-1]
            details_parts.append(f"role: {role_short}")
        if prof.get("source_profile"):
            details_parts.append(f"via: {prof['source_profile']}")
        details = ", ".join(details_parts) or "—"

        row = [marker, name_display, type_display, prof.get("region", "—"), details]

        if verify:
            info = account_info.get(name, {})
            acct = info.get("account", "")
            status = info.get("status", "")
            if status == "ok":
                row.extend([acct, "[green]valid[/green]"])
            else:
                row.extend(["—", f"[red]{status}[/red]"])

        table.add_row(*row)

    console.print(table)

    if not verify:
        console.print(
            "\n[dim]Use --verify to validate credentials for each profile. "
            "Use --profile <name> on any command to switch accounts.[/dim]"
        )


@profile_app.command("show")
def show_profile(
    profile_name: str | None = typer.Argument(
        default=None, help="Profile to inspect (default: current)."
    ),
) -> None:
    """Show detailed info for a specific AWS profile, including STS identity."""
    aws_provider = registry.get("aws")
    if not aws_provider:
        console.print("[red]AWS provider not available.[/red]")
        raise typer.Exit(code=1)

    if profile_name:
        aws_provider._auth.set_profile(profile_name)

    async def _fetch():
        await aws_provider.authenticate()
        return await aws_provider._auth.get_identity()

    active = aws_provider._auth.active_profile
    with console.status(
        f"[bold cyan]Authenticating profile '{active}'..."
    ):
        try:
            identity = asyncio.run(_fetch())
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    table = Table(
        title=f"AWS Profile: {active}",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Profile", identity.get("profile", active))
    table.add_row("Account ID", identity.get("account", "unknown"))
    table.add_row("ARN", identity.get("arn", "unknown"))
    table.add_row("User ID", identity.get("user_id", "unknown"))

    console.print(table)
