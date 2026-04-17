"""Launcher for the Skyforge TUI."""

from __future__ import annotations

from rich.console import Console

console = Console()


def launch_tui() -> None:
    """Import and run the Textual TUI application."""
    try:
        import textual  # noqa: F401
    except ImportError as exc:
        console.print(
            "[red]Error:[/red] Textual is required for the TUI. "
            "Install it with: [bold]pip install 'skyforge'[/bold]"
        )
        raise SystemExit(1) from exc

    from skyforge.tui.app import SkyforgeApp

    app = SkyforgeApp()
    app.run()
