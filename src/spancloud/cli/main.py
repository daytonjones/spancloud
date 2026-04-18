"""Main CLI entry point for Spancloud."""

from __future__ import annotations

import typer
from rich.console import Console

import spancloud
from spancloud.cli.commands.action import action_app
from spancloud.cli.commands.audit import audit_app
from spancloud.cli.commands.auth import auth_app
from spancloud.cli.commands.config import config_app
from spancloud.cli.commands.cost import cost_app
from spancloud.cli.commands.gcs import gcs_app
from spancloud.cli.commands.map import map_app
from spancloud.cli.commands.monitor import monitor_app
from spancloud.cli.commands.profile import profile_app
from spancloud.cli.commands.provider import provider_app
from spancloud.cli.commands.resource import resource_app
from spancloud.cli.commands.s3 import s3_app
from spancloud.cli.commands.status import status_app
from spancloud.cli.commands.gui import launch_gui
from spancloud.cli.commands.tui import launch_tui
from spancloud.cli.commands.unused import unused_app
from spancloud.cli.commands.vultr_storage import vultr_app

console = Console()

app = typer.Typer(
    name="spancloud",
    help="Spancloud — Multi-cloud infrastructure orchestrator.",
    invoke_without_command=True,
    rich_markup_mode="rich",
)

# Register sub-command groups.
app.add_typer(auth_app, name="auth", help="Authenticate with cloud providers.")
app.add_typer(provider_app, name="provider", help="Manage cloud providers.")
app.add_typer(resource_app, name="resource", help="Discover and manage cloud resources.")
app.add_typer(cost_app, name="cost", help="Analyze cloud costs and spending.")
app.add_typer(audit_app, name="audit", help="Run security audits.")
app.add_typer(unused_app, name="unused", help="Find unused and idle resources.")
app.add_typer(map_app, name="map", help="Map resource relationships.")
app.add_typer(monitor_app, name="monitor", help="Monitoring alerts and resource metrics.")
app.add_typer(s3_app, name="s3", help="S3 bucket details and management.")
app.add_typer(gcs_app, name="gcs", help="GCS bucket details and management.")
app.add_typer(action_app, name="action", help="Resource actions (start/stop/reboot/terminate).")
app.add_typer(profile_app, name="profile", help="AWS profile management for multi-account access.")
app.add_typer(config_app, name="config", help="Manage Spancloud configuration.")
app.add_typer(status_app, name="status", help="Show authentication status for all providers.")
app.add_typer(vultr_app, name="vultr", help="Vultr storage details.")


@app.command()
def tui() -> None:
    """Launch the Spancloud TUI dashboard."""
    launch_tui()


@app.command()
def gui() -> None:
    """Launch the Spancloud desktop GUI (requires PySide6)."""
    launch_gui()


@app.command()
def version() -> None:
    """Show the Spancloud version."""
    console.print(f"[bold cyan]Spancloud[/bold cyan] v{spancloud.__version__}")


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output."),
    profile: str | None = typer.Option(
        None, "--profile", "-P",
        help="AWS profile name for multi-account access (overrides SPANCLOUD_AWS_PROFILE).",
    ),
    gcp_project: str | None = typer.Option(
        None, "--gcp-project", "-G",
        help="GCP project ID (overrides SPANCLOUD_GCP_PROJECT_ID and ADC default).",
    ),
) -> None:
    """Spancloud — an all-seeing eye into your multi-cloud infrastructure."""
    if verbose:
        from spancloud.utils.logging import setup_logging

        setup_logging("DEBUG")
    else:
        from spancloud.utils.logging import setup_logging

        setup_logging("WARNING")

    # Apply provider overrides if specified (registered once here so every
    # subcommand sees the swap).
    if profile or gcp_project:
        import spancloud.providers  # noqa: F401
        from spancloud.core.registry import registry

        if profile:
            aws = registry.get("aws")
            if aws:
                aws._auth.set_profile(profile)
        if gcp_project:
            gcp = registry.get("gcp")
            if gcp:
                gcp._auth.set_project(gcp_project)

    # Launch TUI if no subcommand was given
    if ctx.invoked_subcommand is None:
        launch_tui()
