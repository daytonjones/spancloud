"""CLI commands for authenticating with cloud providers."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

# Trigger provider registration.
import spancloud.providers  # noqa: F401
from spancloud.core.registry import registry

console = Console()
auth_app = typer.Typer(help="Authenticate with cloud providers.", no_args_is_help=True)


@auth_app.command("login")
def auth_login(
    provider_name: str = typer.Argument(
        help="Provider to authenticate with (e.g., 'aws', 'gcp')."
    ),
) -> None:
    """Interactively log in to a cloud provider.

    Walks you through the authentication flow for the selected provider,
    including credential setup and project/profile selection.
    """
    provider = registry.get(provider_name)
    if not provider:
        console.print(f"[red]Unknown provider:[/red] '{provider_name}'")
        console.print(f"Available: {', '.join(registry.provider_names)}")
        raise typer.Exit(code=1)

    # aws_login returns a profile name (str) or None; others return bool
    aws_profile: str | None = None

    match provider_name:
        case "aws":
            from spancloud.providers.aws.login import aws_login

            aws_profile = aws_login()
            success = aws_profile is not None
        case "gcp":
            from spancloud.providers.gcp.login import gcp_login

            success = gcp_login()
        case "vultr":
            from spancloud.providers.vultr.login import vultr_login

            success = asyncio.run(vultr_login())
        case "digitalocean":
            from spancloud.providers.digitalocean.login import (
                digitalocean_login,
            )

            success = asyncio.run(digitalocean_login())
        case "azure":
            from spancloud.providers.azure.login import azure_login

            success = asyncio.run(azure_login())
        case "oci":
            from spancloud.providers.oci.login import oci_login

            success = asyncio.run(oci_login())
        case "alibaba":
            from spancloud.providers.alibaba.login import alibaba_login

            success = asyncio.run(alibaba_login())
        case _:
            console.print(
                f"[yellow]Interactive login is not yet available for '{provider_name}'.[/yellow]"
            )
            console.print(
                "Please configure credentials manually using the provider's native tools."
            )
            raise typer.Exit(code=1)

    if success:
        # Set the active profile before verification (important for SSO)
        if aws_profile and provider_name == "aws":
            provider._auth.set_profile(aws_profile)

        # Verify the credentials actually work
        console.print("\n[dim]Verifying credentials...[/dim]")

        async def _verify() -> bool:
            return await provider.authenticate()

        try:
            verified = asyncio.run(_verify())
            if verified:
                console.print("[green]Credentials verified successfully![/green]")
            else:
                console.print(
                    "[yellow]Login completed but credential verification failed.[/yellow]\n"
                    "[dim]You may need to set additional configuration "
                    "(e.g., project ID, region).[/dim]"
                )
        except Exception as exc:
            console.print(f"[yellow]Login completed but verification errored: {exc}[/yellow]")
    else:
        console.print("\n[red]Login was not completed.[/red]")
        raise typer.Exit(code=1)


@auth_app.command("status")
def auth_status() -> None:
    """Show authentication status for all providers."""
    providers = registry.list_providers()

    async def _check_all() -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        for p in providers:
            if not p.supported_resource_types:
                results.append({
                    "provider": p.name,
                    "display_name": p.display_name,
                    "authenticated": "stub",
                })
                continue
            try:
                await p.authenticate()
                status = await p.get_status()
                results.append(status)
            except Exception:
                results.append({
                    "provider": p.name,
                    "display_name": p.display_name,
                    "authenticated": "False",
                })
        return results

    with console.status("[bold cyan]Checking all providers..."):
        statuses = asyncio.run(_check_all())

    table = Table(title="Authentication Status", show_header=True, header_style="bold cyan")
    table.add_column("Provider", style="bold")
    table.add_column("Status")
    table.add_column("Details")

    for status in statuses:
        auth = status.get("authenticated", "False")
        if auth == "True":
            status_str = "[green]Authenticated[/green]"
        elif auth == "stub":
            status_str = "[dim]Not implemented[/dim]"
        else:
            status_str = "[red]Not authenticated[/red]"

        # Build details string from extra fields
        detail_keys = [k for k in status if k not in ("provider", "display_name", "authenticated")]
        details = ", ".join(f"{k}={status[k]}" for k in detail_keys[:3]) or "—"

        table.add_row(status.get("display_name", status["provider"]), status_str, details)

    console.print(table)

    # Helpful hints for unauthenticated providers
    unauthed = [s for s in statuses if s.get("authenticated") == "False"]
    if unauthed:
        console.print("\n[dim]To authenticate a provider, run:[/dim]")
        for s in unauthed:
            name = s["provider"]
            console.print(f"  spancloud auth login {name}")


# Providers that use the Spancloud credential store (bearer-token flow)
_STORED_CRED_KEYS: dict[str, list[str]] = {
    "vultr": ["api_key"],
    "digitalocean": ["token"],
    "alibaba": ["access_key_id", "access_key_secret"],
}


@auth_app.command("logout")
def auth_logout(
    provider_name: str = typer.Argument(
        help="Provider to clear stored credentials for (e.g., 'vultr')."
    ),
) -> None:
    """Delete stored credentials for a provider from the secure credential store.

    Only affects providers that Spancloud stores credentials for (vultr,
    digitalocean). AWS/GCP/Azure use their native credential chains — use
    'aws sso logout', 'gcloud auth revoke', or 'az logout' for those.
    """
    from spancloud.utils import credentials

    if provider_name not in _STORED_CRED_KEYS:
        console.print(
            f"[yellow]'{provider_name}' does not use Spancloud's credential store.[/yellow]"
        )
        if provider_name == "aws":
            console.print("[dim]Use 'aws sso logout' or delete ~/.aws/credentials.[/dim]")
        elif provider_name == "gcp":
            console.print("[dim]Use 'gcloud auth revoke'.[/dim]")
        elif provider_name == "azure":
            console.print("[dim]Use 'az logout'.[/dim]")
        raise typer.Exit(code=1)

    removed_any = False
    for key in _STORED_CRED_KEYS[provider_name]:
        if credentials.delete(provider_name, key):
            console.print(f"[green]Removed[/green] {provider_name}.{key}")
            removed_any = True

    if not removed_any:
        console.print(
            f"[dim]No stored credentials found for '{provider_name}'.[/dim]"
        )


@auth_app.command("store-info")
def auth_store_info() -> None:
    """Show which backend Spancloud is using for credential storage."""
    from spancloud.utils import credentials

    console.print(
        f"[bold]Credential storage backend:[/bold] {credentials.backend_name()}"
    )
    console.print(
        "\n[dim]AWS, GCP, and Azure use their own native credential chains "
        "(~/.aws, ADC JSON, az CLI cache).[/dim]"
    )
    console.print(
        "[dim]Vultr and DigitalOcean API tokens are stored in the backend "
        "shown above after 'spancloud auth login'.[/dim]"
    )
