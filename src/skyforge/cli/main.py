"""Main CLI entry point for Skyforge."""

from __future__ import annotations

import typer
from rich.console import Console

import skyforge
from skyforge.cli.commands.action import action_app
from skyforge.cli.commands.audit import audit_app
from skyforge.cli.commands.auth import auth_app
from skyforge.cli.commands.config import config_app
from skyforge.cli.commands.cost import cost_app
from skyforge.cli.commands.gcs import gcs_app
from skyforge.cli.commands.map import map_app
from skyforge.cli.commands.monitor import monitor_app
from skyforge.cli.commands.profile import profile_app
from skyforge.cli.commands.provider import provider_app
from skyforge.cli.commands.resource import resource_app
from skyforge.cli.commands.s3 import s3_app
from skyforge.cli.commands.tui import launch_tui
from skyforge.cli.commands.unused import unused_app
from skyforge.cli.commands.vultr_storage import vultr_app

console = Console()

app = typer.Typer(
    name="skyforge",
    help="Skyforge — Multi-cloud infrastructure orchestrator.",
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
app.add_typer(config_app, name="config", help="Manage Skyforge configuration.")
app.add_typer(vultr_app, name="vultr", help="Vultr storage details.")


@app.command()
def tui() -> None:
    """Launch the Skyforge TUI dashboard."""
    launch_tui()


@app.command()
def version() -> None:
    """Show the Skyforge version."""
    console.print(f"[bold cyan]Skyforge[/bold cyan] v{skyforge.__version__}")


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output."),
    profile: str | None = typer.Option(
        None, "--profile", "-P",
        help="AWS profile name for multi-account access (overrides SKYFORGE_AWS_PROFILE).",
    ),
) -> None:
    """Skyforge — an all-seeing eye into your multi-cloud infrastructure."""
    if verbose:
        from skyforge.utils.logging import setup_logging

        setup_logging("DEBUG")
    else:
        from skyforge.utils.logging import setup_logging

        setup_logging("WARNING")

    # Apply AWS profile override if specified
    if profile:
        import skyforge.providers  # noqa: F401
        from skyforge.core.registry import registry

        aws = registry.get("aws")
        if aws:
            aws._auth.set_profile(profile)

    # Launch TUI if no subcommand was given
    if ctx.invoked_subcommand is None:
        launch_tui()
