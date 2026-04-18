"""Launcher for the Spancloud desktop GUI."""

from __future__ import annotations

from rich.console import Console

console = Console()


def launch_gui() -> None:
    """Import and run the PySide6 desktop GUI application."""
    try:
        import PySide6  # noqa: F401
    except ImportError as exc:
        console.print(
            "[red]Error:[/red] PySide6 is required for the desktop GUI. "
            "Install it with: [bold]pip install PySide6[/bold]"
        )
        raise SystemExit(1) from exc

    from spancloud.gui.app import main

    main()
