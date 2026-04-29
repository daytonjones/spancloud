"""Global app settings screen — provider enable/disable and theme selection."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Label, Select, Static


_THEMES: list[tuple[str, str]] = [
    ("Tokyo Night (default)", "tokyo-night"),
    ("Dracula", "dracula"),
    ("Nord", "nord"),
    ("Gruvbox", "gruvbox"),
    ("Catppuccin Mocha (dark)", "catppuccin-mocha"),
    ("Catppuccin Latte (light)", "catppuccin-latte"),
    ("Solarized Light", "solarized-light"),
    ("Textual Dark", "textual-dark"),
    ("Textual Light", "textual-light"),
]


class AppSettingsScreen(ModalScreen[bool]):
    """Global settings: provider enable/disable and theme selection."""

    CSS = """
    AppSettingsScreen { align: center middle; }

    #settings-dialog {
        width: 68;
        height: auto;
        max-height: 40;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #settings-title { text-align: center; padding: 0 0 1 0; }
    .section-label {
        color: $accent;
        text-style: bold;
        padding: 1 0 0 0;
    }
    #provider-list {
        height: auto;
        max-height: 12;
        border: solid $primary;
        margin: 0 0 1 0;
        padding: 1;
    }
    #theme-row { height: 3; margin: 0 0 1 0; }
    #theme-label { width: 16; padding: 1 0; }
    #theme-select { width: 1fr; }
    #settings-buttons { height: 3; align: center middle; }
    #settings-buttons Button { margin: 0 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel", priority=True)]

    def __init__(self, current_theme: str = "tokyo-night") -> None:
        super().__init__()
        self._current_theme = current_theme

    def compose(self) -> ComposeResult:
        from spancloud.config.sidebar import get_enabled_providers
        import spancloud.providers  # noqa: F401
        from spancloud.core.registry import registry

        enabled = get_enabled_providers()
        all_providers = registry.list_providers()

        with Vertical(id="settings-dialog"):
            yield Static("[bold cyan]App Settings[/bold cyan]", id="settings-title")

            # ── Theme ──────────────────────────────────────────────────────
            yield Static("Theme", classes="section-label")
            with Horizontal(id="theme-row"):
                yield Label("Select theme:", id="theme-label")
                yield Select(
                    options=_THEMES,
                    value=self._current_theme,
                    id="theme-select",
                    allow_blank=False,
                )

            # ── Providers ──────────────────────────────────────────────────
            yield Static("Providers", classes="section-label")
            yield Static(
                "[dim]Disabled providers are hidden from tabs. Takes effect on restart.[/dim]"
            )
            with VerticalScroll(id="provider-list"):
                for p in all_providers:
                    yield Checkbox(
                        p.display_name,
                        value=p.name in enabled,
                        id=f"provider-{p.name}",
                        name=p.name,
                    )

            with Horizontal(id="settings-buttons"):
                yield Button("Save", id="save-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(False)
        elif event.button.id == "save-btn":
            self._save()

    def action_cancel(self) -> None:
        self.dismiss(False)

    def _save(self) -> None:
        import os
        from spancloud.config import get_settings
        from spancloud.config.sidebar import set_enabled_providers

        # --- Theme ---
        try:
            theme_val = self.query_one("#theme-select", Select).value
            if theme_val and theme_val != Select.BLANK:
                self.app.theme = str(theme_val)
                # Persist
                env_path = get_settings().ensure_config_dir() / "tui.env"
                content = ""
                if env_path.exists():
                    lines = [l for l in env_path.read_text().splitlines()
                             if not l.startswith("SPANCLOUD_TUI_THEME=")]
                    content = "\n".join(lines) + "\n" if lines else ""
                env_path.write_text(content + f"SPANCLOUD_TUI_THEME={theme_val}\n")
                os.environ["SPANCLOUD_TUI_THEME"] = str(theme_val)
        except Exception:
            pass

        # --- Providers ---
        enabled: list[str] = []
        for cb in self.query(Checkbox):
            if cb.name and cb.name.startswith("") and cb.value:
                if cb.id and cb.id.startswith("provider-"):
                    enabled.append(cb.name)
        set_enabled_providers(set(enabled))

        self.app.notify(
            "Settings saved. Provider changes take effect on restart.",
            timeout=4,
        )
        self.dismiss(True)
