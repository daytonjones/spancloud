"""Interactive Azure login — drives `az login` + subscription selection."""

from __future__ import annotations

import shutil
import subprocess

from rich.console import Console
from rich.prompt import Prompt

from skyforge.config import get_settings
from skyforge.utils.logging import get_logger

console = Console()
logger = get_logger(__name__)


async def azure_login() -> bool:
    """Run the interactive Azure login flow.

    Prefers the Azure CLI (`az login`) since it produces reusable
    credentials for DefaultAzureCredential. Falls back to prompting
    for service-principal env vars if the CLI is unavailable.

    Returns:
        True if login completed and a subscription was selected.
    """
    console.print("[bold cyan]Azure Login[/bold cyan]")
    console.print()

    az_path = shutil.which("az")

    if az_path:
        console.print("[dim]Found Azure CLI — launching 'az login'...[/dim]")
        console.print()
        try:
            result = subprocess.run([az_path, "login"], check=False)
            if result.returncode != 0:
                console.print("[red]Azure CLI login failed or was cancelled.[/red]")
                return False
        except Exception as exc:
            console.print(f"[red]Failed to run 'az login': {exc}[/red]")
            return False
    else:
        console.print(
            "[yellow]Azure CLI not found. "
            "Install it from https://learn.microsoft.com/cli/azure/install-azure-cli "
            "or set service-principal env vars:[/yellow]"
        )
        console.print(
            "  AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID\n"
        )
        return False

    # Pick a subscription
    subs = _list_subscriptions_cli(az_path)
    if not subs:
        console.print("[yellow]No subscriptions found for the signed-in account.[/yellow]")
        return False

    console.print("\n[bold]Available subscriptions:[/bold]")
    for i, sub in enumerate(subs, start=1):
        default_marker = " [green](default)[/green]" if sub.get("isDefault") else ""
        console.print(
            f"  {i}. {sub.get('name', '')} "
            f"[dim]({sub.get('id', '')})[/dim]{default_marker}"
        )

    choice = Prompt.ask(
        "\nSelect subscription number",
        default="1",
        show_default=True,
    )
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(subs):
            raise ValueError
    except ValueError:
        console.print("[red]Invalid selection.[/red]")
        return False

    chosen = subs[idx]
    subscription_id = chosen.get("id", "")
    tenant_id = chosen.get("tenantId", "")

    _save_subscription(subscription_id, tenant_id)

    console.print(
        f"\n[green]Selected subscription:[/green] "
        f"{chosen.get('name', '')} ({subscription_id})"
    )
    console.print("[dim]Saved to ~/.config/skyforge/azure.env[/dim]")
    return True


def _list_subscriptions_cli(az_path: str) -> list[dict[str, object]]:
    """Return subscriptions visible to the current az CLI session."""
    import json

    try:
        result = subprocess.run(
            [az_path, "account", "list", "--output", "json"],
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)
    except Exception as exc:
        logger.warning("Failed to list Azure subscriptions via CLI: %s", exc)
        return []


def _save_subscription(subscription_id: str, tenant_id: str) -> None:
    """Persist subscription selection to the skyforge config dir."""
    settings = get_settings()
    config_dir = settings.ensure_config_dir()
    env_path = config_dir / "azure.env"

    lines = [
        f"SKYFORGE_AZURE_SUBSCRIPTION_ID={subscription_id}",
    ]
    if tenant_id:
        lines.append(f"SKYFORGE_AZURE_TENANT_ID={tenant_id}")

    env_path.write_text("\n".join(lines) + "\n")

    # Also export for the current process so verify() works post-login
    import os

    os.environ["SKYFORGE_AZURE_SUBSCRIPTION_ID"] = subscription_id
    if tenant_id:
        os.environ["SKYFORGE_AZURE_TENANT_ID"] = tenant_id
