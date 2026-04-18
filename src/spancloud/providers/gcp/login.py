"""Interactive GCP login flow."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from skyforge.utils.logging import get_logger

logger = get_logger(__name__)
console = Console()

ADC_PATH = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"


def _gcloud_available() -> bool:
    """Check if the gcloud CLI is installed."""
    return shutil.which("gcloud") is not None


def _adc_exists() -> bool:
    """Check if Application Default Credentials file exists."""
    return ADC_PATH.exists()


def _get_current_project() -> str:
    """Get the currently configured gcloud project."""
    try:
        result = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True,
            text=True,
            check=False,
        )
        project = result.stdout.strip()
        if project and project != "(unset)":
            return project
    except Exception:
        pass
    return ""


def _get_current_account() -> str:
    """Get the currently authenticated gcloud account."""
    try:
        result = subprocess.run(
            ["gcloud", "config", "get-value", "account"],
            capture_output=True,
            text=True,
            check=False,
        )
        account = result.stdout.strip()
        if account and account != "(unset)":
            return account
    except Exception:
        pass
    return ""


def _adc_is_valid() -> bool:
    """Quick check if existing ADC credentials can authenticate."""
    try:
        import google.auth

        credentials, _ = google.auth.default()
        return credentials is not None
    except Exception:
        return False


def _list_projects() -> list[dict[str, str]]:
    """List accessible GCP projects.

    Uses JSON format for reliability. Returns empty list on failure.
    """
    try:
        result = subprocess.run(
            ["gcloud", "projects", "list", "--format=json(projectId,name)", "--limit=50"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            import json

            data = json.loads(result.stdout)
            projects: list[dict[str, str]] = []
            for item in data:
                pid = item.get("projectId", "")
                name = item.get("name", pid)
                if pid:
                    projects.append({"id": pid, "name": name})
            if projects:
                return projects

        if result.returncode != 0 and result.stderr:
            logger.debug("gcloud projects list failed: %s", result.stderr.strip())

    except subprocess.TimeoutExpired:
        logger.debug("gcloud projects list timed out")
    except Exception as exc:
        logger.debug("gcloud projects list error: %s", exc)

    return []


def gcp_login() -> bool:
    """Run the interactive GCP login flow.

    Detects existing credentials and skips steps that are already done.

    Returns:
        True if authentication was set up successfully.
    """
    console.print()
    console.print(Panel("[bold cyan]GCP Authentication[/bold cyan]", expand=False))

    if not _gcloud_available():
        console.print("[red]gcloud CLI is not installed.[/red] Install it from:")
        console.print("  https://cloud.google.com/sdk/docs/install")
        console.print(
            "\n[dim]After installing, run [bold]skyforge auth login gcp[/bold] again.[/dim]"
        )
        return False

    # Show current state
    current_account = _get_current_account()
    current_project = _get_current_project()
    has_adc = _adc_exists() and _adc_is_valid()

    if current_account:
        console.print(f"Current gcloud account: [bold]{current_account}[/bold]")
    if current_project:
        console.print(f"Current gcloud project: [bold]{current_project}[/bold]")

    # Step 1: Application Default Credentials
    if has_adc:
        console.print("\n[green]Application Default Credentials already configured.[/green]")
        if not Confirm.ask("Re-authenticate anyway?", default=False):
            return _handle_project_selection(current_project)
    else:
        console.print("\n[bold]Step 1:[/bold] Set up Application Default Credentials")
        console.print(
            "[dim]This is required for Skyforge (and other Python SDKs) to access GCP.\n"
            "Note: 'gcloud auth login' alone is NOT sufficient — "
            "ADC is a separate credential.[/dim]\n"
        )

    if not Confirm.ask("Open browser for GCP authentication?", default=True):
        if has_adc:
            # They skipped re-auth but already have ADC — still valid
            return _handle_project_selection(current_project)
        console.print("[yellow]Skipped.[/yellow]")
        return False

    console.print("\n[cyan]Running:[/cyan] gcloud auth application-default login")
    console.print("[dim]Your browser will open for authentication...[/dim]\n")

    result = subprocess.run(
        ["gcloud", "auth", "application-default", "login"],
        check=False,
    )

    if result.returncode != 0:
        console.print("\n[red]Authentication failed.[/red]")
        return False

    console.print("\n[green]Application Default Credentials set up successfully![/green]")
    return _handle_project_selection(current_project)


def _handle_project_selection(current_project: str) -> bool:
    """Handle Step 2: project selection/configuration.

    Args:
        current_project: Currently configured project, if any.

    Returns:
        True if a project was configured (or was already set).
    """
    console.print("\n[bold]Step 2:[/bold] Configure GCP project")

    if current_project and Confirm.ask(
        f"Keep current project [bold]{current_project}[/bold]?",
        default=True,
    ):
        _set_quota_project(current_project)
        console.print(f"\n[green]Using project:[/green] {current_project}")
        _print_env_hint(current_project)
        return True

    console.print("\n[dim]Fetching available projects...[/dim]")
    projects = _list_projects()

    if not projects:
        console.print(
            "[yellow]No projects found.[/yellow]\n"
            "[dim]This is normal for new accounts without an organization.\n"
            "Create a project at https://console.cloud.google.com "
            "then enter its ID below, or press Enter to skip.[/dim]\n"
        )
        project_id = Prompt.ask("GCP Project ID (or Enter to skip)", default="")
        if project_id:
            _set_project(project_id)
            return True
        console.print(
            "\n[green]ADC is set up.[/green] "
            "Run [bold]skyforge auth login gcp[/bold] again after creating a project."
        )
        return True

    # Show projects for selection
    console.print(f"\n[bold]Available projects ({len(projects)}):[/bold]")
    display_count = min(len(projects), 20)
    for i, p in enumerate(projects[:display_count], 1):
        name_suffix = f" ({p['name']})" if p["name"] != p["id"] else ""
        console.print(f"  [bold]{i}[/bold]) {p['id']}{name_suffix}")

    if len(projects) > display_count:
        console.print(f"  [dim]... and {len(projects) - display_count} more[/dim]")

    console.print(f"  [bold]{display_count + 1}[/bold]) Enter manually")

    choice = Prompt.ask(
        "\nSelect project",
        choices=[str(i) for i in range(1, display_count + 2)],
    )
    choice_idx = int(choice)

    if choice_idx <= display_count:
        project_id = projects[choice_idx - 1]["id"]
    else:
        project_id = Prompt.ask("GCP Project ID")

    if project_id:
        _set_project(project_id)
        return True

    return False


def _set_project(project_id: str) -> None:
    """Set the gcloud default project, ADC quota project, and print env hints."""
    subprocess.run(
        ["gcloud", "config", "set", "project", project_id],
        check=False,
        capture_output=True,
    )
    _set_quota_project(project_id)
    console.print(f"\n[green]Project set to:[/green] [bold]{project_id}[/bold]")
    _print_env_hint(project_id)


def _set_quota_project(project_id: str) -> None:
    """Set the ADC quota project to avoid 'quota exceeded' errors."""
    subprocess.run(
        ["gcloud", "auth", "application-default", "set-quota-project", project_id],
        check=False,
        capture_output=True,
    )


def _print_env_hint(project_id: str) -> None:
    """Print environment variable hints for the project."""
    console.print(
        f"\n[dim]To set this permanently for Skyforge, add to your shell profile:\n"
        f"  export SKYFORGE_GCP_PROJECT_ID={project_id}[/dim]"
    )
