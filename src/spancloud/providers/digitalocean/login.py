"""Interactive DigitalOcean authentication login flow."""

from __future__ import annotations

import asyncio
import getpass

import httpx
from rich.console import Console
from rich.panel import Panel

console = Console()


async def digitalocean_login() -> bool:
    """Interactive DigitalOcean login flow.

    Prompts for a Personal Access Token, validates it, and prints
    the env var to set for persistence.
    """
    console.print(
        Panel(
            "[bold cyan]DigitalOcean Authentication Setup[/bold cyan]\n\n"
            "DigitalOcean uses Personal Access Tokens.\n"
            "Generate one at: "
            "[link]https://cloud.digitalocean.com/account/api/tokens[/link]\n\n"
            "The token needs [bold]read[/bold] scope at minimum. "
            "For actions (start/stop droplets), also grant [bold]write[/bold].",
            title="DigitalOcean Login",
        )
    )

    from spancloud.config import get_settings
    from spancloud.utils import credentials

    settings = get_settings().digitalocean
    existing_token = settings.token
    token_source = "environment"
    if not existing_token:
        stored = credentials.load("digitalocean", "token")
        if stored:
            existing_token = stored
            token_source = f"credential store ({credentials.backend_name()})"

    if existing_token:
        key_tail = existing_token[-8:]
        console.print(
            f"\n[green]Existing token found[/green] "
            f"(ending in ...{key_tail}, from {token_source})"
        )
        use_existing = input("Use existing token? [Y/n]: ").strip().lower()
        if use_existing in ("", "y", "yes"):
            ok = await _validate_token(existing_token)
            if ok:
                _persist_token(existing_token)
            return ok

    console.print()
    token = getpass.getpass("Enter your DigitalOcean API token: ").strip()

    if not token:
        console.print("[red]No token provided.[/red]")
        return False

    success = await _validate_token(token)

    if success:
        _persist_token(token)

    return success


def _persist_token(token: str) -> None:
    """Save the verified token to the secure credential store."""
    from spancloud.utils import credentials

    if credentials.save("digitalocean", "token", token):
        console.print(
            f"\n[dim]Token saved to {credentials.backend_name()}.[/dim]\n"
            "[dim]Next run will reuse it automatically.[/dim]"
        )
    else:
        console.print(
            "\n[yellow]Could not persist token securely.[/yellow]\n"
            "[dim]Set SPANCLOUD_DIGITALOCEAN_TOKEN in your shell to avoid "
            "re-entering it next time.[/dim]"
        )


async def _validate_token(token: str) -> bool:
    """Validate a DO API token against the account endpoint."""
    console.print("[dim]Validating token...[/dim]")

    def _check() -> tuple[int, dict | None]:
        try:
            response = httpx.get(
                "https://api.digitalocean.com/v2/account",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            return (
                response.status_code,
                response.json() if response.is_success else None,
            )
        except httpx.ConnectError as exc:
            return -1, {"error": str(exc)}

    try:
        status_code, data = await asyncio.to_thread(_check)
    except Exception as exc:
        console.print(f"[red]Connection error: {exc}[/red]")
        return False

    if status_code == 200 and data:
        account = data.get("account", {})
        email = account.get("email", "unknown")
        status = account.get("status", "")

        console.print("\n[green]Authentication successful![/green]")
        console.print(f"  Email:  [bold]{email}[/bold]")
        console.print(f"  Status: {status}")
        return True

    if status_code == 401:
        console.print("[red]Invalid token (401 Unauthorized).[/red]")
    elif status_code == -1:
        console.print(f"[red]Could not connect: {data}[/red]")
    else:
        console.print(f"[red]Unexpected API response: HTTP {status_code}[/red]")

    return False
