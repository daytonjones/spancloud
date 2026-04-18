"""Interactive OCI login — driven by the `oci` CLI (`oci setup config`)."""

from __future__ import annotations

import shutil
import subprocess

from rich.console import Console
from rich.prompt import Prompt

from spancloud.providers.oci.auth import OCIAuth
from spancloud.utils.logging import get_logger

console = Console()
logger = get_logger(__name__)


async def oci_login() -> bool:
    """Interactive OCI login flow.

    If the OCI CLI is available, delegates to `oci setup config`. If the
    user already has a config, lets them pick a profile instead.

    Returns:
        True when a usable profile is selected.
    """
    console.print("[bold cyan]OCI Login[/bold cyan]\n")

    auth = OCIAuth()
    profiles = auth.list_profiles()

    if profiles:
        console.print("[bold]Profiles detected in ~/.oci/config:[/bold]")
        for i, p in enumerate(profiles, start=1):
            console.print(f"  {i}. {p}")
        choice = Prompt.ask(
            "\nSelect profile number (or 'n' to set up a new one)",
            default="1",
            show_default=True,
        )
        if choice.lower().startswith("n"):
            return _run_oci_setup()
        try:
            idx = int(choice) - 1
            if idx < 0 or idx >= len(profiles):
                raise ValueError
        except ValueError:
            console.print("[red]Invalid selection.[/red]")
            return False

        chosen = profiles[idx]
        _persist_profile(chosen)
        console.print(f"[green]Selected profile:[/green] {chosen}")
        return True

    console.print(
        "[yellow]No OCI config found.[/yellow] "
        "Running `oci setup config` interactively...\n"
    )
    return _run_oci_setup()


def _run_oci_setup() -> bool:
    """Shell out to `oci setup config` to create the config file."""
    oci_path = shutil.which("oci")
    if not oci_path:
        console.print(
            "[red]OCI CLI not found.[/red] "
            "Install it from https://docs.oracle.com/iaas/tools/oci-cli/latest/"
        )
        return False

    try:
        result = subprocess.run([oci_path, "setup", "config"], check=False)
    except Exception as exc:
        console.print(f"[red]Failed to run oci setup config: {exc}[/red]")
        return False

    if result.returncode != 0:
        console.print("[red]`oci setup config` exited with an error.[/red]")
        return False

    console.print("\n[green]OCI config created.[/green]")
    _persist_profile("DEFAULT")
    return True


def _persist_profile(profile: str) -> None:
    """Remember the chosen profile for future Spancloud runs."""
    from spancloud.config import get_settings

    config_dir = get_settings().ensure_config_dir()
    env_path = config_dir / "oci.env"
    env_path.write_text(f"SPANCLOUD_OCI_PROFILE={profile}\n")

    import os

    os.environ["SPANCLOUD_OCI_PROFILE"] = profile
