"""Launcher for the Spancloud TUI."""

from __future__ import annotations

from rich.console import Console

console = Console()


def launch_tui(mock: bool = False) -> None:
    """Import and run the Textual TUI application."""
    try:
        import textual  # noqa: F401
    except ImportError as exc:
        console.print(
            "[red]Error:[/red] Textual is required for the TUI. "
            "Install it with: [bold]pip install 'spancloud'[/bold]"
        )
        raise SystemExit(1) from exc

    from spancloud.tui.app import SpancloudApp

    app = SpancloudApp(mock=mock)
    app.run()
