"""Interactive Vultr authentication login flow.

Prompts the user for their API key and validates it against the Vultr API.
"""

from __future__ import annotations

import asyncio

import httpx
from rich.console import Console
from rich.panel import Panel

console = Console()


async def vultr_login() -> bool:
    """Interactive Vultr login flow.

    Prompts for API key, validates against the Vultr API,
    and prints the environment variable to set.

    Returns:
        True if authentication succeeded.
    """
    console.print(
        Panel(
            "[bold cyan]Vultr Authentication Setup[/bold cyan]\n\n"
            "Vultr uses API keys for authentication.\n"
            "Generate one at: [link]https://my.vultr.com/settings/#settingsapi[/link]",
            title="Vultr Login",
        )
    )

    # Check for existing key — env/settings first, then credential store
    from spancloud.config import get_settings
    from spancloud.utils import credentials

    settings = get_settings().vultr
    existing_key = settings.api_key
    key_source = "environment"
    if not existing_key:
        stored = credentials.load("vultr", "api_key")
        if stored:
            existing_key = stored
            key_source = f"credential store ({credentials.backend_name()})"

    if existing_key:
        key_tail = existing_key[-8:]
        console.print(
            f"\n[green]Existing API key found[/green] "
            f"(ending in ...{key_tail}, from {key_source})"
        )
        use_existing = input("Use existing key? [Y/n]: ").strip().lower()
        if use_existing in ("", "y", "yes"):
            ok = await _validate_key(existing_key)
            if ok:
                _persist_key(existing_key)
            return ok

    # Use getpass to mask the API key input
    import getpass

    console.print()
    api_key = getpass.getpass("Enter your Vultr API key: ").strip()

    if not api_key:
        console.print("[red]No API key provided.[/red]")
        return False

    success = await _validate_key(api_key)

    if success:
        _persist_key(api_key)

    return success


def _persist_key(api_key: str) -> None:
    """Save the verified key to the secure credential store."""
    from spancloud.utils import credentials

    if credentials.save("vultr", "api_key", api_key):
        console.print(
            f"\n[dim]API key saved to {credentials.backend_name()}.[/dim]\n"
            "[dim]Next run will reuse it automatically.[/dim]"
        )
    else:
        console.print(
            "\n[yellow]Could not persist API key securely.[/yellow]\n"
            "[dim]Set SPANCLOUD_VULTR_API_KEY in your shell to avoid re-entering "
            "it next time.[/dim]"
        )


async def _validate_key(api_key: str) -> bool:
    """Validate an API key against the Vultr API."""
    console.print("[dim]Validating API key...[/dim]")

    def _check() -> tuple[int, dict | None]:
        try:
            response = httpx.get(
                "https://api.vultr.com/v2/account",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15,
            )
            return response.status_code, response.json() if response.is_success else None
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
        name = account.get("name", "")
        balance = account.get("balance", "")

        console.print("\n[green]Authentication successful![/green]")
        console.print(f"  Account: [bold]{name or email}[/bold]")
        console.print(f"  Email: {email}")
        if balance:
            console.print(f"  Balance: ${balance}")

        return True

    if status_code == 401:
        console.print("[red]API returned 401 Unauthorized.[/red]")
        console.print(
            "[dim]Verify the key at https://my.vultr.com/settings/#settingsapi\n"
            "New keys may take a minute to activate.[/dim]"
        )
    elif status_code == 403:
        console.print("[red]API returned 403 Forbidden — key may lack permissions.[/red]")
    elif status_code == -1:
        console.print(f"[red]Could not connect to Vultr API: {data}[/red]")
    else:
        console.print(f"[red]Unexpected API response: HTTP {status_code}[/red]")

    return False
