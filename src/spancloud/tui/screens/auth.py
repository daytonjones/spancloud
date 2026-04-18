"""Auth screen — modal popup for authenticating with a provider."""

from __future__ import annotations

import asyncio
import subprocess
from typing import TYPE_CHECKING

from textual import work
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, RichLog, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from spancloud.core.provider import BaseProvider


class AuthScreen(ModalScreen[bool]):
    """Modal screen for authenticating with a cloud provider.

    Runs the appropriate auth flow (SSO, API key, ADC) and streams
    output. Returns True if auth succeeded.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    CSS = """
    AuthScreen {
        align: center middle;
    }

    #auth-dialog {
        width: 80;
        max-width: 100;
        height: auto;
        max-height: 35;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }

    #auth-title {
        text-align: center;
        padding: 0 0 1 0;
    }

    #auth-log {
        height: 15;
        border: solid $primary;
        margin: 1 0;
    }

    #auth-api-key {
        display: none;
        margin: 1 0;
    }

    #auth-buttons {
        height: 3;
        align: center middle;
    }

    #auth-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, provider: BaseProvider) -> None:
        super().__init__()
        self._provider = provider
        # Azure is two-phase: run az login, then pick a subscription.
        # Tracks which phase the next button press should drive.
        self._azure_phase: str = "idle"  # idle | subscription_pick
        self._azure_subs: list[dict] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="auth-dialog"):
            yield Static(
                f"[bold cyan]Authenticate: "
                f"{self._provider.display_name}[/bold cyan]",
                id="auth-title",
            )
            yield RichLog(
                id="auth-log", wrap=True, highlight=True, markup=True
            )

            # API key/token input (shown for Vultr, DigitalOcean)
            yield Input(
                placeholder="Enter API key / token...",
                password=True,
                id="auth-api-key",
            )

            with Horizontal(id="auth-buttons"):
                yield Button(
                    "Start", id="auth-start", variant="primary"
                )
                yield Button(
                    "Cancel", id="auth-cancel", variant="error"
                )

    def on_mount(self) -> None:
        log = self.query_one("#auth-log", RichLog)
        name = self._provider.name

        if name == "aws":
            log.write("[bold]AWS SSO Authentication[/bold]")
            log.write("This will open your browser for SSO login.")
            log.write("Press [bold]Start[/bold] to begin.\n")
        elif name == "gcp":
            log.write("[bold]GCP Authentication[/bold]")
            log.write("This will open your browser for Google auth.")
            log.write("Press [bold]Start[/bold] to begin.\n")
        elif name == "vultr":
            log.write("[bold]Vultr Authentication[/bold]")
            log.write("Enter your API key below, then press [bold]Start[/bold].")
            log.write(
                "Generate a key at: https://my.vultr.com/settings/#settingsapi\n"
            )
            self.query_one("#auth-api-key").display = True
            self.query_one("#auth-start").label = "Validate Key"
        elif name == "digitalocean":
            log.write("[bold]DigitalOcean Authentication[/bold]")
            log.write(
                "Enter your Personal Access Token below, "
                "then press [bold]Start[/bold]."
            )
            log.write(
                "Generate a token at: "
                "https://cloud.digitalocean.com/account/api/tokens\n"
            )
            log.write(
                "[dim]Grant [bold]read[/bold] for listing, plus "
                "[bold]write[/bold] for actions (start/stop droplets).[/dim]\n"
            )
            self.query_one("#auth-api-key").display = True
            self.query_one("#auth-start").label = "Validate Token"
        elif name == "azure":
            log.write("[bold]Azure Authentication[/bold]")
            log.write(
                "This will run [bold]az login[/bold] (opens your browser),\n"
                "then let you pick a subscription.\n"
            )
            log.write("Press [bold]Start[/bold] to begin.\n")
        elif name == "oci":
            log.write("[bold]OCI Authentication[/bold]")
            log.write(
                "Loads profiles from ~/.oci/config. If none exist, this will\n"
                "shell out to [bold]oci setup config[/bold] to create one.\n"
            )
            log.write("Press [bold]Start[/bold] to begin.\n")
        elif name == "alibaba":
            log.write("[bold]Alibaba Cloud Authentication[/bold]")
            log.write(
                "Paste [bold]AccessKeyID:AccessKeySecret[/bold] below, then "
                "press [bold]Start[/bold]."
            )
            log.write(
                "Generate keys at: "
                "https://ram.console.aliyun.com/manage/ak\n"
            )
            log.write(
                "[dim]Example: LTAI5t...:abc123def456... "
                "(use a RAM sub-user, not root keys).[/dim]\n"
            )
            self.query_one("#auth-api-key").display = True
            self.query_one("#auth-start").label = "Validate Keys"
        else:
            log.write(
                f"[yellow]No interactive auth for "
                f"{self._provider.display_name}[/yellow]"
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "auth-cancel":
            self.dismiss(False)
        elif event.button.id == "auth-start":
            event.button.disabled = True
            event.button.label = "Authenticating..."
            self._run_auth()

    def action_cancel(self) -> None:
        """Close the modal without authenticating."""
        self.dismiss(False)

    @work(exclusive=True)
    async def _run_auth(self) -> None:
        log = self.query_one("#auth-log", RichLog)
        name = self._provider.name

        try:
            if name == "aws":
                success = await self._auth_aws(log)
            elif name == "gcp":
                success = await self._auth_gcp(log)
            elif name == "vultr":
                success = await self._auth_vultr(log)
            elif name == "digitalocean":
                success = await self._auth_digitalocean(log)
            elif name == "oci":
                success = await self._auth_oci(log)
            elif name == "alibaba":
                success = await self._auth_alibaba(log)
            elif name == "azure":
                success = await self._handle_azure(log)
                # Phase 1 just finished — wait for the user to pick a
                # subscription before we verify. Button flips to
                # "Select Subscription" and we bail early.
                if self._azure_phase == "subscription_pick":
                    start_btn = self.query_one("#auth-start", Button)
                    start_btn.disabled = False
                    start_btn.label = "Select Subscription"
                    return
            else:
                log.write("[red]No auth flow available.[/red]")
                success = False

            if success:
                log.write("\n[cyan]Verifying credentials...[/cyan]")
                verified = await self._provider.authenticate()
                if verified:
                    log.write(
                        "[bold green]Authentication successful![/bold green]"
                    )
                else:
                    log.write(
                        "[yellow]Auth completed but verification failed."
                        "[/yellow]"
                    )
                    success = False
            else:
                log.write("\n[red]Authentication failed.[/red]")

        except Exception as exc:
            log.write(f"\n[red]Error: {exc}[/red]")
            success = False

        # Update buttons
        start_btn = self.query_one("#auth-start", Button)
        start_btn.disabled = False
        start_btn.label = "Retry" if not success else "Done"

        cancel_btn = self.query_one("#auth-cancel", Button)
        cancel_btn.label = "Close"

        if success:
            await asyncio.sleep(1.5)
            self.dismiss(True)

    async def _auth_aws(self, log: RichLog) -> bool:
        """Authenticate AWS — try existing credentials, fall back to SSO.

        Order of preference:
          1. Whatever boto3's default chain resolves (env vars, ~/.aws/credentials
             default, instance profile, etc). AWSAuth.verify() walks every
             configured profile — SSO and access-key — looking for one that
             produces a valid STS response.
          2. If nothing works and there are SSO profiles on disk, run
             `aws sso login` for the first SSO profile.
          3. Otherwise print a helpful message pointing the user at the full
             interactive CLI flow or `aws configure`.
        """
        import shutil

        from spancloud.providers.aws.login import (
            _get_existing_profiles,
            _get_sso_profiles,
        )

        # Step 1: try existing credentials first. verify() will iterate through
        # every configured profile looking for one that works.
        log.write("[cyan]Checking existing AWS credentials...[/cyan]")
        try:
            if await self._provider.authenticate():
                info = await self._provider._auth.get_identity()
                log.write(
                    f"[green]Already authenticated![/green]\n"
                    f"  Profile: [bold]{info.get('profile', '')}[/bold]\n"
                    f"  Account: [bold]{info.get('account', '')}[/bold]\n"
                    f"  ARN:     [bold]{info.get('arn', '')}[/bold]"
                )
                return True
        except Exception as exc:
            log.write(f"[dim]verify() raised: {exc}[/dim]")

        log.write("[yellow]No working credentials found in the default chain.[/yellow]\n")

        # Step 2: SSO fallback, if available
        sso_profiles = _get_sso_profiles() if shutil.which("aws") else []
        if sso_profiles:
            profile = sso_profiles[0]
            if hasattr(self._provider, "_auth") and hasattr(
                self._provider._auth, "active_profile"
            ):
                active = self._provider._auth.active_profile
                if active in sso_profiles:
                    profile = active

            log.write(f"SSO profile: [bold]{profile}[/bold]")
            log.write("Opening browser...\n")

            def _run() -> tuple[int, str]:
                result = subprocess.run(
                    ["aws", "sso", "login", "--profile", profile],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                return result.returncode, result.stdout + result.stderr

            try:
                returncode, output = await asyncio.to_thread(_run)
                for line in output.strip().split("\n"):
                    if line.strip():
                        log.write(line)
                if returncode == 0:
                    # Pin the profile we just logged into so the follow-up
                    # verify() picks the freshly-cached SSO tokens.
                    if hasattr(self._provider, "_auth"):
                        self._provider._auth.set_profile(profile)
                    return True
            except subprocess.TimeoutExpired:
                log.write("[yellow]SSO login timed out (2 minutes).[/yellow]")
            return False

        # Step 3: nothing to do here — tell the user what options they have.
        existing = _get_existing_profiles()
        log.write(
            "[yellow]AWS credentials not found.[/yellow]\n"
            "Options (any one of):\n"
            "  \u2022 Set env vars: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY\n"
            "  \u2022 Run [bold]aws configure[/bold] in a terminal to store access keys\n"
            "  \u2022 Run [bold]aws configure sso[/bold] to set up SSO\n"
            "  \u2022 Run [bold]spancloud auth login aws[/bold] for the full "
            "interactive flow (SSO / access keys / profile switch)"
        )
        if existing:
            log.write(
                f"\n[dim]Profiles in ~/.aws/: {', '.join(existing)} — "
                "none of them had valid credentials.[/dim]"
            )
        if not shutil.which("aws"):
            log.write(
                "\n[dim]AWS CLI is not installed; only access keys via env "
                "vars or ~/.aws/credentials will work without it.[/dim]"
            )
        return False

    async def _auth_gcp(self, log: RichLog) -> bool:
        """Run GCP application-default login."""
        import shutil

        if not shutil.which("gcloud"):
            log.write("[red]gcloud CLI not found. Install it first.[/red]")
            return False

        log.write("Running: gcloud auth application-default login")
        log.write("Opening browser...\n")

        def _run() -> tuple[int, str]:
            result = subprocess.run(
                ["gcloud", "auth", "application-default", "login"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.returncode, result.stdout + result.stderr

        try:
            returncode, output = await asyncio.to_thread(_run)
            for line in output.strip().split("\n"):
                if line.strip():
                    log.write(line)
            return returncode == 0
        except subprocess.TimeoutExpired:
            log.write("[yellow]Login timed out (2 minutes).[/yellow]")
            return False

    async def _auth_vultr(self, log: RichLog) -> bool:
        """Validate Vultr API key."""
        import httpx

        api_key = self.query_one("#auth-api-key", Input).value.strip()
        if not api_key:
            log.write("[yellow]Please enter an API key above.[/yellow]")
            # Re-enable start button
            self.query_one("#auth-start", Button).disabled = False
            self.query_one("#auth-start", Button).label = "Validate Key"
            return False

        log.write("Validating API key...")

        def _check() -> tuple[int, dict | None]:
            try:
                resp = httpx.get(
                    "https://api.vultr.com/v2/account",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=15,
                )
                return (
                    resp.status_code,
                    resp.json() if resp.is_success else None,
                )
            except Exception as exc:
                return -1, {"error": str(exc)}

        status, data = await asyncio.to_thread(_check)

        if status == 200 and data:
            acct = data.get("account", {})
            log.write(
                f"[green]Valid![/green] Account: {acct.get('email', '')}"
            )
            if hasattr(self._provider, "_auth"):
                self._provider._auth._api_key = api_key

            # Persist to the OS keychain so future sessions reuse it
            from spancloud.utils import credentials

            if credentials.save("vultr", "api_key", api_key):
                log.write(
                    f"[dim]Saved to {credentials.backend_name()} — "
                    "future sessions will reuse this key.[/dim]"
                )
            else:
                log.write(
                    "[yellow]Could not save key to keychain.[/yellow] "
                    "[dim]Set SPANCLOUD_VULTR_API_KEY to avoid re-entering "
                    "it next session.[/dim]"
                )
            return True

        if status == 401:
            log.write("[red]Invalid API key (401 Unauthorized).[/red]")
        elif status == -1:
            log.write(f"[red]Connection error: {data}[/red]")
        else:
            log.write(f"[red]API returned HTTP {status}[/red]")
        return False

    async def _auth_digitalocean(self, log: RichLog) -> bool:
        """Validate a DigitalOcean Personal Access Token."""
        import httpx

        token = self.query_one("#auth-api-key", Input).value.strip()
        if not token:
            log.write("[yellow]Please enter a token above.[/yellow]")
            self.query_one("#auth-start", Button).disabled = False
            self.query_one("#auth-start", Button).label = "Validate Token"
            return False

        log.write("Validating token...")

        def _check() -> tuple[int, dict | None]:
            try:
                resp = httpx.get(
                    "https://api.digitalocean.com/v2/account",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=15,
                )
                return (
                    resp.status_code,
                    resp.json() if resp.is_success else None,
                )
            except Exception as exc:
                return -1, {"error": str(exc)}

        status, data = await asyncio.to_thread(_check)

        if status == 200 and data:
            acct = data.get("account", {})
            log.write(
                f"[green]Valid![/green] Account: {acct.get('email', '')}"
            )
            if hasattr(self._provider, "_auth"):
                self._provider._auth._token = token

            from spancloud.utils import credentials

            if credentials.save("digitalocean", "token", token):
                log.write(
                    f"[dim]Saved to {credentials.backend_name()} — "
                    "future sessions will reuse this token.[/dim]"
                )
            else:
                log.write(
                    "[yellow]Could not save token to keychain.[/yellow] "
                    "[dim]Set SPANCLOUD_DIGITALOCEAN_TOKEN to avoid "
                    "re-entering it next session.[/dim]"
                )
            return True

        if status == 401:
            log.write("[red]Invalid token (401 Unauthorized).[/red]")
        elif status == -1:
            log.write(f"[red]Connection error: {data}[/red]")
        else:
            log.write(f"[red]API returned HTTP {status}[/red]")
        return False

    # ---- Azure (two-phase) ----

    async def _handle_azure(self, log: RichLog) -> bool:
        """Dispatch to the current Azure phase."""
        if self._azure_phase == "subscription_pick":
            return await self._azure_select_subscription(log)
        return await self._azure_run_login(log)

    async def _azure_run_login(self, log: RichLog) -> bool:
        """Phase 1: run `az login` and list subscriptions for selection."""
        import json
        import shutil

        az_path = shutil.which("az")
        if not az_path:
            log.write(
                "[red]Azure CLI not found.[/red] Install it from "
                "https://learn.microsoft.com/cli/azure/install-azure-cli"
            )
            return False

        log.write("Running: az login")
        log.write("Opening browser...\n")

        def _run_login() -> tuple[int, str]:
            result = subprocess.run(
                [az_path, "login"],
                capture_output=True,
                text=True,
                timeout=180,
            )
            return result.returncode, result.stdout + result.stderr

        try:
            rc, output = await asyncio.to_thread(_run_login)
        except subprocess.TimeoutExpired:
            log.write("[yellow]az login timed out (3 minutes).[/yellow]")
            return False

        # Stream condensed output (az login dumps the whole JSON array)
        if rc != 0:
            for line in output.strip().split("\n")[-8:]:
                if line.strip():
                    log.write(line)
            log.write("[red]az login failed.[/red]")
            return False

        log.write("[green]az login succeeded.[/green]\n")

        # List subscriptions
        def _list_subs() -> list[dict]:
            result = subprocess.run(
                [az_path, "account", "list", "--output", "json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return []
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return []

        subs = await asyncio.to_thread(_list_subs)
        if not subs:
            log.write(
                "[yellow]No subscriptions visible to this account.[/yellow]"
            )
            return False

        self._azure_subs = subs
        log.write("[bold]Available subscriptions:[/bold]")
        for i, sub in enumerate(subs, start=1):
            default = " [green](default)[/green]" if sub.get("isDefault") else ""
            log.write(
                f"  {i}. {sub.get('name', '')} "
                f"[dim]({sub.get('id', '')})[/dim]{default}"
            )

        # Flip the input to a number picker and change the start button
        inp = self.query_one("#auth-api-key", Input)
        inp.display = True
        inp.password = False
        inp.placeholder = f"Subscription number (1-{len(subs)})"
        inp.value = "1"

        log.write(
            "\nEnter the subscription number above, "
            "then press [bold]Select Subscription[/bold]."
        )
        self._azure_phase = "subscription_pick"
        # Phase 1 complete but no verify yet — caller will short-circuit.
        return False

    async def _azure_select_subscription(self, log: RichLog) -> bool:
        """Phase 2: parse the chosen subscription number, persist, and signal verify."""
        from spancloud.providers.azure.login import _save_subscription

        raw = self.query_one("#auth-api-key", Input).value.strip() or "1"
        try:
            idx = int(raw) - 1
            if idx < 0 or idx >= len(self._azure_subs):
                raise ValueError
        except ValueError:
            log.write(
                f"[red]Enter a number between 1 and {len(self._azure_subs)}."
                "[/red]"
            )
            return False

        chosen = self._azure_subs[idx]
        subscription_id = chosen.get("id", "") or ""
        tenant_id = chosen.get("tenantId", "") or ""
        name = chosen.get("name", "")

        log.write(f"\n[cyan]Selected:[/cyan] {name} ({subscription_id})")

        # Persist for future sessions (writes ~/.config/spancloud/azure.env +
        # updates os.environ for the current process).
        _save_subscription(subscription_id, tenant_id)

        # Update the live auth object so authenticate() sees the new sub.
        if hasattr(self._provider, "_auth"):
            auth = self._provider._auth
            if hasattr(auth, "set_subscription"):
                auth.set_subscription(subscription_id)
            if hasattr(auth, "_tenant_id") and tenant_id:
                auth._tenant_id = tenant_id

        log.write("[dim]Saved to ~/.config/spancloud/azure.env[/dim]")
        # Reset phase so closing and reopening starts fresh.
        self._azure_phase = "idle"
        return True

    # ---- OCI ----

    async def _auth_oci(self, log: RichLog) -> bool:
        """Validate OCI by loading its config file and selecting a profile."""
        from spancloud.providers.oci.auth import OCIAuth

        auth = OCIAuth()
        profiles = await asyncio.to_thread(auth.list_profiles)

        if not profiles:
            log.write(
                "[yellow]No ~/.oci/config found.[/yellow] "
                "Run [bold]oci setup config[/bold] in a terminal, then retry."
            )
            return False

        log.write(f"Detected {len(profiles)} OCI profile(s):")
        for p in profiles:
            log.write(f"  \u2022 {p}")

        # Just use the first profile automatically; CLI has the picker.
        chosen = profiles[0]
        log.write(f"\n[cyan]Using profile:[/cyan] {chosen}")

        if hasattr(self._provider, "_auth"):
            self._provider._auth.set_profile(chosen)

        # Persist for future runs.
        from spancloud.config import get_settings

        env_path = get_settings().ensure_config_dir() / "oci.env"
        env_path.write_text(f"SPANCLOUD_OCI_PROFILE={chosen}\n")
        import os

        os.environ["SPANCLOUD_OCI_PROFILE"] = chosen
        log.write("[dim]Saved to ~/.config/spancloud/oci.env[/dim]")
        return True

    # ---- Alibaba ----

    async def _auth_alibaba(self, log: RichLog) -> bool:
        """Validate Alibaba AccessKey ID:Secret entered in the input field."""
        from spancloud.config import get_settings
        from spancloud.utils import credentials

        raw = self.query_one("#auth-api-key", Input).value.strip()
        if ":" not in raw:
            log.write(
                "[yellow]Enter as AccessKeyID:AccessKeySecret[/yellow]"
            )
            self.query_one("#auth-start", Button).disabled = False
            self.query_one("#auth-start", Button).label = "Validate Keys"
            return False

        key_id, _, key_secret = raw.partition(":")
        if not key_id or not key_secret:
            log.write("[red]Empty AccessKey ID or Secret.[/red]")
            return False

        region = get_settings().alibaba.default_region or "us-west-1"
        log.write(f"Validating (region={region})...")

        def _check() -> tuple[bool, str]:
            try:
                from alibabacloud_ecs20140526 import models as ecs_models
                from alibabacloud_ecs20140526.client import Client as EcsClient
                from alibabacloud_tea_openapi import models as open_api_models

                config = open_api_models.Config(
                    access_key_id=key_id,
                    access_key_secret=key_secret,
                    endpoint=f"ecs.{region}.aliyuncs.com",
                )
                client = EcsClient(config)
                response = client.describe_regions(
                    ecs_models.DescribeRegionsRequest()
                )
                regions = getattr(response.body, "regions", None)
                count = (
                    len(getattr(regions, "region", []) or []) if regions else 0
                )
                return True, f"Found {count} regions"
            except Exception as exc:
                return False, str(exc)

        ok, msg = await asyncio.to_thread(_check)
        if not ok:
            log.write(f"[red]Authentication failed:[/red] {msg}")
            return False

        log.write(f"[green]Valid![/green] {msg}")

        # Push credentials to the live auth object
        if hasattr(self._provider, "_auth"):
            self._provider._auth.set_credentials(key_id, key_secret)

        # Persist to the secure credential store
        ok_id = credentials.save("alibaba", "access_key_id", key_id)
        ok_sec = credentials.save(
            "alibaba", "access_key_secret", key_secret
        )
        if ok_id and ok_sec:
            log.write(
                f"[dim]Saved to {credentials.backend_name()} — "
                "future sessions will reuse these keys.[/dim]"
            )
        else:
            log.write(
                "[yellow]Could not persist keys to credential store.[/yellow]"
            )
        return True
