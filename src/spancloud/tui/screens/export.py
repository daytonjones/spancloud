"""Export screen — modal for exporting resources to file."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, RadioButton, RadioSet, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from skyforge.core.resource import Resource


class ExportScreen(ModalScreen[bool]):
    """Modal for exporting resources to JSON, CSV, or YAML."""

    CSS = """
    ExportScreen {
        align: center middle;
    }

    #export-dialog {
        width: 60;
        height: auto;
        max-height: 20;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    #export-title {
        text-align: center;
        padding: 0 0 1 0;
    }

    #export-format {
        height: 5;
        margin: 1 0;
    }

    #export-path {
        margin: 1 0;
    }

    #export-buttons {
        height: 3;
        align: center middle;
    }

    #export-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    def __init__(self, resources: list[Resource]) -> None:
        super().__init__()
        self._resources = resources

    def compose(self) -> ComposeResult:
        with Vertical(id="export-dialog"):
            yield Static(
                f"[bold cyan]Export {len(self._resources)} Resource(s)[/bold cyan]",
                id="export-title",
            )

            with RadioSet(id="export-format"):
                yield RadioButton("JSON", value=True)
                yield RadioButton("CSV")
                yield RadioButton("YAML")

            yield Input(
                value="skyforge-export",
                placeholder="Filename (without extension)",
                id="export-path",
            )

            with Horizontal(id="export-buttons"):
                yield Button("Export", id="export-go", variant="primary")
                yield Button("Cancel", id="export-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "export-cancel":
            self.dismiss(False)
        elif event.button.id == "export-go":
            self._do_export()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def _do_export(self) -> None:
        from skyforge.core.export import to_csv, to_json, to_yaml

        # Get format
        radio_set = self.query_one("#export-format", RadioSet)
        pressed = radio_set.pressed_index
        formats = [
            ("json", to_json, ".json"),
            ("csv", to_csv, ".csv"),
            ("yaml", to_yaml, ".yaml"),
        ]
        fmt_name, formatter, ext = formats[pressed]

        # Get filename
        base = self.query_one("#export-path", Input).value.strip()
        if not base:
            base = "skyforge-export"
        filepath = Path(base + ext)

        try:
            result = formatter(self._resources)
            filepath.write_text(result)
            self.app.notify(
                f"Exported {len(self._resources)} resource(s) to {filepath}",
                timeout=5,
            )
            self.dismiss(True)
        except Exception as exc:
            self.app.notify(f"Export failed: {exc}", severity="error")
