"""Settings screen — modal for configuring sidebar items."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from skyforge.core.provider import BaseProvider


class SidebarSettingsScreen(ModalScreen[bool]):
    """Modal for toggling which services appear in the sidebar."""

    CSS = """
    SidebarSettingsScreen {
        align: center middle;
    }

    #settings-dialog {
        width: 70;
        height: auto;
        max-height: 35;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    #settings-title {
        text-align: center;
        padding: 0 0 1 0;
    }

    #settings-list {
        height: 20;
        border: solid $primary;
        margin: 1 0;
        padding: 1;
    }

    #settings-buttons {
        height: 3;
        align: center middle;
    }

    #settings-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    def __init__(self, provider: BaseProvider) -> None:
        super().__init__()
        self._provider = provider

    def compose(self) -> ComposeResult:
        from skyforge.config.sidebar import get_available_services, get_sidebar_items

        current = {s["name"] for s in get_sidebar_items(self._provider.name)}
        available = get_available_services(self._provider.name)

        with Vertical(id="settings-dialog"):
            yield Static(
                f"[bold cyan]Sidebar Settings: "
                f"{self._provider.display_name}[/bold cyan]",
                id="settings-title",
            )
            yield Static(
                "[dim]Check the services to show in the sidebar "
                "(max ~10 recommended)[/dim]"
            )

            with VerticalScroll(id="settings-list"):
                for svc in available:
                    yield Checkbox(
                        f"{svc['label']}  [dim]({svc['type']})[/dim]",
                        value=svc["name"] in current,
                        id=f"svc-{svc['name']}",
                        name=svc["name"],
                    )

            with Horizontal(id="settings-buttons"):
                yield Button("Save", id="settings-save", variant="primary")
                yield Button("Reset Defaults", id="settings-reset")
                yield Button("Cancel", id="settings-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "settings-cancel":
            self.dismiss(False)
        elif event.button.id == "settings-reset":
            from skyforge.config.sidebar import reset_sidebar

            reset_sidebar(self._provider.name)
            self.app.notify("Sidebar reset to defaults.", timeout=3)
            self.dismiss(True)
        elif event.button.id == "settings-save":
            self._save()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def _save(self) -> None:
        from skyforge.config.sidebar import get_available_services, set_sidebar_items

        available = {
            s["name"]: s for s in get_available_services(self._provider.name)
        }

        selected: list[dict[str, str]] = []
        for checkbox in self.query(Checkbox):
            if checkbox.value and checkbox.name:
                svc = available.get(checkbox.name)
                if svc:
                    selected.append(svc)

        if not selected:
            self.app.notify(
                "Select at least one service.", severity="warning"
            )
            return

        set_sidebar_items(self._provider.name, selected)
        self.app.notify(
            f"Saved {len(selected)} sidebar items. "
            f"Restart TUI to apply.",
            timeout=5,
        )
        self.dismiss(True)
