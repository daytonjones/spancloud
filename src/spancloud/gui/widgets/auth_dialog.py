"""Auth dialog — Qt port of the TUI AuthScreen for each cloud provider."""

from __future__ import annotations

import asyncio
import subprocess
from typing import TYPE_CHECKING

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from spancloud.gui.theme import (
    ACCENT_BLUE,
    BG_ELEVATED,
    BG_SURFACE,
    BORDER_SUBTLE,
    STATUS_ERROR,
    STATUS_OK,
    TEXT_MUTED,
    TEXT_PRIMARY,
)

if TYPE_CHECKING:
    from spancloud.core.provider import BaseProvider

# ---------------------------------------------------------------------------
# Colour map for log levels → HTML spans
# ---------------------------------------------------------------------------
_LOG_COLORS: dict[str, str] = {
    "success": STATUS_OK,
    "error":   STATUS_ERROR,
    "warning": "#e0af68",
    "info":    "#7dcfff",
    "dim":     "#565f89",
    "normal":  TEXT_PRIMARY,
}


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _AuthWorker(QThread):
    """Run the async auth flow for one provider in a background thread."""

    log_line           = Signal(str, str)   # (text, level)
    auth_done          = Signal(bool)       # True = authenticated successfully
    azure_subs_ready   = Signal(list)       # list[dict] — triggers Phase 2 UI
    gcp_projects_ready = Signal(list)       # list[str]  — triggers project picker

    def __init__(
        self,
        provider: BaseProvider,
        api_key: str = "",
        profile: str = "",
    ) -> None:
        super().__init__()
        self._provider = provider
        self._api_key = api_key
        self._profile = profile
        self._phase = "auth"
        self._azure_subs: list[dict] = []
        self._azure_sub_idx = 0
        self._gcp_project_id: str = ""

    def start_azure_phase2(self, subs: list[dict], sub_idx: int) -> None:
        self._azure_subs = subs
        self._azure_sub_idx = sub_idx
        self._phase = "azure_subscription"
        self.start()

    def start_gcp_phase2(self, project_id: str) -> None:
        self._gcp_project_id = project_id
        self._phase = "gcp_project"
        self.start()

    def _log(self, text: str, level: str = "normal") -> None:
        self.log_line.emit(text, level)

    def run(self) -> None:
        try:
            asyncio.run(self._dispatch())
        except Exception as exc:
            self._log(f"Unexpected error: {exc}", "error")
            self.auth_done.emit(False)

    async def _dispatch(self) -> None:
        name = self._provider.name
        success = False

        if self._phase == "azure_subscription":
            success = await self._azure_select_subscription()
        elif self._phase == "gcp_project":
            success = await self._gcp_set_project()
        elif name == "aws":
            success = await self._auth_aws()
        elif name == "gcp":
            success = await self._auth_gcp()
        elif name == "vultr":
            success = await self._auth_vultr()
        elif name == "digitalocean":
            success = await self._auth_digitalocean()
        elif name == "azure":
            success = await self._auth_azure()
            # Azure phase 1 done — signal the dialog to set up phase 2 UI.
            # Don't emit auth_done; the dialog restarts the worker for phase 2.
            if self._phase == "azure_awaiting_pick":
                return
        elif name == "oci":
            success = await self._auth_oci()
        elif name == "alibaba":
            success = await self._auth_alibaba()
        else:
            self._log(f"No interactive auth available for {name}.", "warning")

        if success:
            self._log("Verifying credentials…", "info")
            try:
                verified = await self._provider.authenticate()
                if verified:
                    self._log("Authentication successful!", "success")
                    self.auth_done.emit(True)
                    return
                self._log("Auth completed but credential verification failed.", "warning")
            except Exception as exc:
                self._log(f"Verification error: {exc}", "error")
        self.auth_done.emit(False)

    # ------------------------------------------------------------------
    # AWS
    # ------------------------------------------------------------------
    async def _auth_aws(self) -> bool:
        import shutil

        from spancloud.providers.aws.auth import AWSAuth

        all_profiles = AWSAuth.list_configured_profiles()
        if not all_profiles:
            self._log("No AWS credentials found.", "warning")
            self._log(
                "Options:\n"
                "  • aws configure          — store access keys\n"
                "  • aws configure sso      — set up SSO\n"
                "  • Set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars",
                "dim",
            )
            return False

        profile = self._profile
        if not profile:
            # Auto-pick: SSO first, then access keys
            sso = [p for p in all_profiles if p.get("type") == "sso"]
            keys = [p for p in all_profiles if p.get("type") == "access_keys"]
            if sso:
                profile = sso[0]["name"]
            elif keys:
                profile = keys[0]["name"]
            else:
                profile = all_profiles[0]["name"]

        if hasattr(self._provider, "_auth"):
            self._provider._auth.set_profile(profile)

        profile_type = next(
            (p.get("type", "unknown") for p in all_profiles if p["name"] == profile),
            "unknown",
        )

        self._log(f"Checking credentials for profile: {profile}…", "info")
        try:
            if await self._provider.authenticate():
                info = await self._provider._auth.get_identity()  # type: ignore[attr-defined]
                self._log(
                    f"Already authenticated!\n"
                    f"  Profile: {info.get('profile', '')}\n"
                    f"  Account: {info.get('account', '')}\n"
                    f"  ARN:     {info.get('arn', '')}",
                    "success",
                )
                _persist_aws_profile(profile)
                return True
        except Exception as exc:
            self._log(f"Credential check: {exc}", "dim")

        self._log("Credentials not valid — attempting login…", "warning")

        if profile_type == "sso":
            if not shutil.which("aws"):
                self._log("AWS CLI is required for SSO login but was not found.", "error")
                return False
            self._log(f"Running: aws sso login --profile {profile}", "dim")
            self._log("Opening browser…")

            def _run_sso() -> tuple[int, str]:
                r = subprocess.run(
                    ["aws", "sso", "login", "--profile", profile],
                    capture_output=True, text=True, timeout=120,
                )
                return r.returncode, r.stdout + r.stderr

            try:
                rc, output = await asyncio.to_thread(_run_sso)
                for line in output.strip().split("\n"):
                    if line.strip():
                        self._log(line, "dim")
                if rc == 0:
                    if hasattr(self._provider, "_auth"):
                        self._provider._auth.set_profile(profile)
                    _persist_aws_profile(profile)
                    self._log("Profile saved for future sessions.", "dim")
                    return True
                self._log("SSO login failed.", "error")
            except subprocess.TimeoutExpired:
                self._log("SSO login timed out (2 minutes).", "warning")
            return False

        if profile_type == "access_keys":
            self._log(
                f"Credentials for profile '{profile}' are invalid or expired.\n"
                f"Run:  aws configure --profile {profile}  to update your keys.",
                "error",
            )
            return False

        self._log("Could not determine credential type.", "error")
        return False

    # ------------------------------------------------------------------
    # GCP
    # ------------------------------------------------------------------
    async def _auth_gcp(self) -> bool:
        import shutil

        if not shutil.which("gcloud"):
            self._log("gcloud CLI not found. Install it first.", "error")
            return False

        self._log("Running: gcloud auth application-default login", "dim")
        self._log("Opening browser…")

        def _run() -> tuple[int, str]:
            r = subprocess.run(
                ["gcloud", "auth", "application-default", "login"],
                capture_output=True, text=True, timeout=120,
            )
            return r.returncode, r.stdout + r.stderr

        try:
            rc, output = await asyncio.to_thread(_run)
            for line in output.strip().split("\n"):
                if line.strip():
                    self._log(line, "dim")
            if rc != 0:
                return False
        except subprocess.TimeoutExpired:
            self._log("Login timed out (2 minutes).", "warning")
            return False

        # Check if a project is already configured
        existing_project = ""
        try:
            r = subprocess.run(
                ["gcloud", "config", "get-value", "project"],
                capture_output=True, text=True, timeout=5,
            )
            p = r.stdout.strip()
            if p and p != "(unset)":
                existing_project = p
        except Exception:
            pass

        if existing_project:
            self._log(f"Using project: {existing_project}", "info")
            if hasattr(self._provider, "_auth"):
                self._provider._auth.set_project(existing_project)  # type: ignore[attr-defined]
            return True

        # No project set — list available projects and ask user to pick
        self._log("Fetching available GCP projects…", "dim")

        def _list_projects() -> list[str]:
            r = subprocess.run(
                ["gcloud", "projects", "list", "--format=value(projectId)"],
                capture_output=True, text=True, timeout=30,
            )
            return [p.strip() for p in r.stdout.strip().splitlines() if p.strip()]

        projects = await asyncio.to_thread(_list_projects)

        if not projects:
            self._log(
                "No GCP projects found. Create one at console.cloud.google.com\n"
                "or set SPANCLOUD_GCP_PROJECT_ID in your environment.",
                "warning",
            )
            return True  # auth itself succeeded; project can be set later

        if len(projects) == 1:
            self._log(f"Auto-selected project: {projects[0]}", "info")
            if hasattr(self._provider, "_auth"):
                self._provider._auth.set_project(projects[0])  # type: ignore[attr-defined]
            _persist_gcp_project(projects[0])
            return True

        # Multiple projects — hand off to the dialog for user selection
        self._log(f"Found {len(projects)} projects — please select one.", "info")
        self._phase = "gcp_awaiting_project"
        self.gcp_projects_ready.emit(projects)
        return False  # phase 2 will emit auth_done

    async def _gcp_set_project(self) -> bool:
        project_id = self._gcp_project_id
        self._log(f"Selected project: {project_id}", "info")
        if hasattr(self._provider, "_auth"):
            self._provider._auth.set_project(project_id)  # type: ignore[attr-defined]
        _persist_gcp_project(project_id)
        self._log("Saved to ~/.config/spancloud/gcp.env", "dim")
        return True

    # ------------------------------------------------------------------
    # Vultr
    # ------------------------------------------------------------------
    async def _auth_vultr(self) -> bool:
        import httpx

        api_key = self._api_key.strip()
        if not api_key:
            self._log("Please enter an API key.", "warning")
            return False

        self._log("Validating API key…", "info")

        def _check() -> tuple[int, dict | None]:
            try:
                resp = httpx.get(
                    "https://api.vultr.com/v2/account",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=15,
                )
                return resp.status_code, resp.json() if resp.is_success else None
            except Exception as exc:
                return -1, {"error": str(exc)}

        status, data = await asyncio.to_thread(_check)

        if status == 200 and data:
            acct = data.get("account", {})
            self._log(f"Valid!  Account: {acct.get('email', '')}", "success")
            if hasattr(self._provider, "_auth"):
                self._provider._auth._api_key = api_key  # type: ignore[attr-defined]
            _save_credential("vultr", "api_key", api_key, self._log)
            return True
        if status == 401:
            self._log("Invalid API key (401 Unauthorized).", "error")
        elif status == -1:
            self._log(f"Connection error: {data}", "error")
        else:
            self._log(f"API returned HTTP {status}.", "error")
        return False

    # ------------------------------------------------------------------
    # DigitalOcean
    # ------------------------------------------------------------------
    async def _auth_digitalocean(self) -> bool:
        import httpx

        token = self._api_key.strip()
        if not token:
            self._log("Please enter a Personal Access Token.", "warning")
            return False

        self._log("Validating token…", "info")

        def _check() -> tuple[int, dict | None]:
            try:
                resp = httpx.get(
                    "https://api.digitalocean.com/v2/account",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=15,
                )
                return resp.status_code, resp.json() if resp.is_success else None
            except Exception as exc:
                return -1, {"error": str(exc)}

        status, data = await asyncio.to_thread(_check)

        if status == 200 and data:
            acct = data.get("account", {})
            self._log(f"Valid!  Account: {acct.get('email', '')}", "success")
            if hasattr(self._provider, "_auth"):
                self._provider._auth._token = token  # type: ignore[attr-defined]
            _save_credential("digitalocean", "token", token, self._log)
            return True
        if status == 401:
            self._log("Invalid token (401 Unauthorized).", "error")
        elif status == -1:
            self._log(f"Connection error: {data}", "error")
        else:
            self._log(f"API returned HTTP {status}.", "error")
        return False

    # ------------------------------------------------------------------
    # Azure (two-phase)
    # ------------------------------------------------------------------
    async def _auth_azure(self) -> bool:
        import json
        import shutil

        az_path = shutil.which("az")
        if not az_path:
            self._log(
                "Azure CLI not found.\n"
                "Install from: https://learn.microsoft.com/cli/azure/install-azure-cli",
                "error",
            )
            return False

        self._log("Running: az login", "dim")
        self._log("Opening browser…")

        def _run_login() -> tuple[int, str]:
            r = subprocess.run(
                [az_path, "login"], capture_output=True, text=True, timeout=180,
            )
            return r.returncode, r.stdout + r.stderr

        try:
            rc, output = await asyncio.to_thread(_run_login)
        except subprocess.TimeoutExpired:
            self._log("az login timed out (3 minutes).", "warning")
            return False

        if rc != 0:
            for line in output.strip().split("\n")[-8:]:
                if line.strip():
                    self._log(line, "dim")
            self._log("az login failed.", "error")
            return False

        self._log("az login succeeded.", "success")

        def _list_subs() -> list[dict]:
            r = subprocess.run(
                [az_path, "account", "list", "--output", "json"],
                capture_output=True, text=True, timeout=30,
            )
            try:
                return json.loads(r.stdout) if r.returncode == 0 else []
            except json.JSONDecodeError:
                return []

        subs = await asyncio.to_thread(_list_subs)
        if not subs:
            self._log("No subscriptions visible to this account.", "warning")
            return False

        self._log("Available subscriptions:")
        for i, sub in enumerate(subs, 1):
            default = " (default)" if sub.get("isDefault") else ""
            self._log(f"  {i}. {sub.get('name', '')}  [{sub.get('id', '')}]{default}", "dim")

        # Signal the dialog to build phase-2 UI; don't emit auth_done yet.
        self._phase = "azure_awaiting_pick"
        self.azure_subs_ready.emit(subs)
        return False  # will return True from phase 2

    async def _azure_select_subscription(self) -> bool:
        from spancloud.providers.azure.login import _save_subscription

        chosen = self._azure_subs[self._azure_sub_idx]
        sub_id = chosen.get("id", "")
        tenant_id = chosen.get("tenantId", "")
        name = chosen.get("name", "")

        self._log(f"Selected: {name}  ({sub_id})", "info")
        _save_subscription(sub_id, tenant_id)

        if hasattr(self._provider, "_auth"):
            auth = self._provider._auth  # type: ignore[attr-defined]
            if hasattr(auth, "set_subscription"):
                auth.set_subscription(sub_id)
            if hasattr(auth, "_tenant_id") and tenant_id:
                auth._tenant_id = tenant_id

        self._log("Saved to ~/.config/spancloud/azure.env", "dim")
        return True

    # ------------------------------------------------------------------
    # OCI
    # ------------------------------------------------------------------
    async def _auth_oci(self) -> bool:
        from spancloud.providers.oci.auth import OCIAuth

        auth = OCIAuth()
        profiles = await asyncio.to_thread(auth.list_profiles)

        if not profiles:
            self._log(
                "No ~/.oci/config found.\n"
                "Run  oci setup config  in a terminal, then retry.",
                "warning",
            )
            return False

        self._log(f"Detected {len(profiles)} OCI profile(s):")
        for p in profiles:
            self._log(f"  • {p}", "dim")

        chosen = self._profile if self._profile in profiles else profiles[0]
        self._log(f"Using profile: {chosen}", "info")

        if hasattr(self._provider, "_auth"):
            self._provider._auth.set_profile(chosen)  # type: ignore[attr-defined]

        import os
        from spancloud.config import get_settings

        env_path = get_settings().ensure_config_dir() / "oci.env"
        env_path.write_text(f"SPANCLOUD_OCI_PROFILE={chosen}\n")
        os.environ["SPANCLOUD_OCI_PROFILE"] = chosen
        self._log("Saved to ~/.config/spancloud/oci.env", "dim")
        return True

    # ------------------------------------------------------------------
    # Alibaba
    # ------------------------------------------------------------------
    async def _auth_alibaba(self) -> bool:
        from spancloud.config import get_settings
        from spancloud.utils import credentials

        raw = self._api_key.strip()
        if ":" not in raw:
            self._log("Enter as  AccessKeyID:AccessKeySecret", "warning")
            return False

        key_id, _, key_secret = raw.partition(":")
        if not key_id or not key_secret:
            self._log("Empty AccessKey ID or Secret.", "error")
            return False

        region = get_settings().alibaba.default_region or "us-west-1"
        self._log(f"Validating (region={region})…", "info")

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
                response = client.describe_regions(ecs_models.DescribeRegionsRequest())
                regions = getattr(response.body, "regions", None)
                count = len(getattr(regions, "region", []) or []) if regions else 0
                return True, f"Found {count} regions"
            except Exception as exc:
                return False, str(exc)

        ok, msg = await asyncio.to_thread(_check)
        if not ok:
            self._log(f"Authentication failed: {msg}", "error")
            return False

        self._log(f"Valid!  {msg}", "success")

        if hasattr(self._provider, "_auth"):
            self._provider._auth.set_credentials(key_id, key_secret)  # type: ignore[attr-defined]

        ok_id = credentials.save("alibaba", "access_key_id", key_id)
        ok_sec = credentials.save("alibaba", "access_key_secret", key_secret)
        if ok_id and ok_sec:
            self._log(f"Saved to {credentials.backend_name()} — future sessions will reuse these keys.", "dim")
        else:
            self._log("Could not persist keys to credential store.", "warning")
        return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _persist_gcp_project(project_id: str) -> None:
    import os
    from spancloud.config import get_settings

    env_path = get_settings().ensure_config_dir() / "gcp.env"
    env_path.write_text(f"SPANCLOUD_GCP_PROJECT_ID={project_id}\n")
    os.environ["SPANCLOUD_GCP_PROJECT_ID"] = project_id


def _persist_aws_profile(profile: str) -> None:
    import os
    from spancloud.config import get_settings

    env_path = get_settings().ensure_config_dir() / "aws.env"
    env_path.write_text(f"SPANCLOUD_AWS_PROFILE={profile}\n")
    os.environ["SPANCLOUD_AWS_PROFILE"] = profile


def _save_credential(
    provider: str, key: str, value: str, log: object
) -> None:
    from spancloud.utils import credentials

    if credentials.save(provider, key, value):
        log(f"Saved to {credentials.backend_name()} — future sessions will reuse this.", "dim")  # type: ignore[operator]
    else:
        log("Could not save to keychain. Set the env var to avoid re-entering next session.", "warning")  # type: ignore[operator]


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class AuthDialog(QDialog):
    """Modal auth dialog — mirrors the TUI AuthScreen."""

    def __init__(
        self,
        provider: BaseProvider,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._provider = provider
        self._worker: _AuthWorker | None = None
        self._azure_subs: list[dict] = []
        self._gcp_projects: list[str] = []

        self.setWindowTitle(f"Connect — {provider.display_name}")
        self.setMinimumWidth(540)
        self.setMinimumHeight(420)
        self.setModal(True)
        self._apply_style()
        self._build()
        self._setup_for_provider()

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{ background: {BG_SURFACE}; }}
            QLabel#dlg-title {{
                color: {ACCENT_BLUE};
                font-size: 14px;
                font-weight: 700;
            }}
            QPlainTextEdit {{
                background: {BG_ELEVATED};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 6px;
                color: {TEXT_PRIMARY};
                font-family: "JetBrains Mono", "Fira Code", monospace;
                font-size: 11px;
                padding: 8px;
            }}
            QLineEdit {{
                background: {BG_ELEVATED};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 5px;
                color: {TEXT_PRIMARY};
                font-size: 12px;
                padding: 6px 10px;
            }}
            QLineEdit:focus {{ border-color: {ACCENT_BLUE}; }}
            QComboBox {{
                background: {BG_ELEVATED};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 5px;
                color: {TEXT_PRIMARY};
                font-size: 12px;
                padding: 5px 8px;
            }}
            QComboBox:focus {{ border-color: {ACCENT_BLUE}; }}
            QComboBox QAbstractItemView {{
                background: #24283b;
                border: 1px solid {BORDER_SUBTLE};
                color: {TEXT_PRIMARY};
                selection-background-color: {ACCENT_BLUE};
                selection-color: #ffffff;
            }}
            QPushButton {{
                background: {BG_ELEVATED};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 5px;
                color: {TEXT_PRIMARY};
                font-size: 12px;
                padding: 6px 20px;
                min-width: 90px;
            }}
            QPushButton:hover {{ border-color: {ACCENT_BLUE}; color: {ACCENT_BLUE}; }}
            QPushButton#btn-connect {{
                background: {ACCENT_BLUE};
                border-color: {ACCENT_BLUE};
                color: #1a1b26;
                font-weight: 600;
            }}
            QPushButton#btn-connect:hover {{
                background: #89b4fa;
                border-color: #89b4fa;
                color: #1a1b26;
            }}
            QPushButton#btn-connect:disabled {{
                background: #3b4261;
                border-color: #3b4261;
                color: {TEXT_MUTED};
            }}
        """)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(10)

        self._title = QLabel(f"Connect: {self._provider.display_name}")
        self._title.setObjectName("dlg-title")
        root.addWidget(self._title)

        # Log area
        self._log_area = QPlainTextEdit()
        self._log_area.setReadOnly(True)
        self._log_area.setMinimumHeight(180)
        root.addWidget(self._log_area, stretch=1)

        # API key / token input (hidden by default)
        self._api_key_input = QLineEdit()
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_input.setPlaceholderText("Enter API key / token…")
        self._api_key_input.hide()
        root.addWidget(self._api_key_input)

        # AWS profile picker (hidden by default)
        self._profile_combo = QComboBox()
        self._profile_combo.hide()
        root.addWidget(self._profile_combo)

        # Azure subscription picker (hidden until phase 2)
        self._sub_combo = QComboBox()
        self._sub_combo.hide()
        root.addWidget(self._sub_combo)

        # GCP project picker (hidden until projects are loaded)
        self._gcp_project_combo = QComboBox()
        self._gcp_project_combo.hide()
        root.addWidget(self._gcp_project_combo)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER_SUBTLE};")
        root.addWidget(sep)

        btn_row = QHBoxLayout()
        self._btn_connect = QPushButton("Connect")
        self._btn_connect.setObjectName("btn-connect")
        self._btn_connect.clicked.connect(self._on_connect)

        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.clicked.connect(self.reject)

        btn_row.addWidget(self._btn_connect)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_cancel)
        root.addLayout(btn_row)

    def _setup_for_provider(self) -> None:
        name = self._provider.name

        if name == "aws":
            from spancloud.providers.aws.auth import AWSAuth

            all_profiles = AWSAuth.list_configured_profiles()
            sso = [p for p in all_profiles if p.get("type") == "sso"]
            keys = [p for p in all_profiles if p.get("type") == "access_keys"]

            if not all_profiles:
                self._log(
                    "No AWS credentials found.\n\n"
                    "Options:\n"
                    "  • aws configure           — store access keys\n"
                    "  • aws configure sso       — set up SSO\n"
                    "  • Set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars",
                    "warning",
                )
                self._btn_connect.setEnabled(False)
                return

            self._log(
                f"AWS authentication\n"
                f"{len(all_profiles)} profile(s) found  "
                f"({len(sso)} SSO, {len(keys)} access key)",
            )

            if len(all_profiles) > 1:
                self._profile_combo.show()
                for p in all_profiles:
                    self._profile_combo.addItem(
                        f"{p['name']}  [{p.get('type', '?')}]", p["name"]
                    )
                self._log("Select a profile, then click Connect.", "dim")
            else:
                p = all_profiles[0]
                self._log(f"Profile: {p['name']}  [{p.get('type', '?')}]", "dim")

        elif name == "gcp":
            self._log(
                "GCP Authentication\n\n"
                "This will open your browser for Google application-default login.\n"
                "Click Connect to begin.",
            )

        elif name == "vultr":
            self._log(
                "Vultr Authentication\n\n"
                "Enter your API key below, then click Connect.\n"
                "Generate a key at: https://my.vultr.com/settings/#settingsapi",
            )
            self._api_key_input.setPlaceholderText("Vultr API key…")
            self._api_key_input.show()
            self._btn_connect.setText("Validate Key")

        elif name == "digitalocean":
            self._log(
                "DigitalOcean Authentication\n\n"
                "Enter your Personal Access Token, then click Connect.\n"
                "Generate at: https://cloud.digitalocean.com/account/api/tokens\n\n"
                "Grant read for listing, plus write for start/stop actions.",
            )
            self._api_key_input.setPlaceholderText("Personal Access Token…")
            self._api_key_input.show()
            self._btn_connect.setText("Validate Token")

        elif name == "azure":
            self._log(
                "Azure Authentication\n\n"
                "This will run  az login  (opens your browser),\n"
                "then let you pick a subscription.\n\n"
                "Click Connect to begin.",
            )

        elif name == "oci":
            self._log(
                "OCI Authentication\n\n"
                "Loads profiles from ~/.oci/config.\n"
                "If none exist, run  oci setup config  in a terminal, then retry.\n\n"
                "Click Connect to begin.",
            )

        elif name == "alibaba":
            self._log(
                "Alibaba Cloud Authentication\n\n"
                "Paste your  AccessKeyID:AccessKeySecret  below, then click Connect.\n"
                "Generate keys at: https://ram.console.aliyun.com/manage/ak\n\n"
                "Use a RAM sub-user, not root keys.",
            )
            self._api_key_input.setPlaceholderText("AccessKeyID:AccessKeySecret")
            self._api_key_input.show()
            self._btn_connect.setText("Validate Keys")

        else:
            self._log(f"No interactive auth available for {name}.", "warning")
            self._btn_connect.setEnabled(False)

    # ------------------------------------------------------------------
    # Slot: Connect button
    # ------------------------------------------------------------------
    def _on_connect(self) -> None:
        # GCP phase 2: user selected a project
        if self._gcp_projects and not self._gcp_project_combo.isHidden():
            project_id = self._gcp_project_combo.currentText().strip()
            worker = _AuthWorker(self._provider)
            self._start_worker(worker)
            worker.start_gcp_phase2(project_id)
            return

        # Azure phase 2: user selected a subscription
        if self._azure_subs and not self._sub_combo.isHidden():
            idx = self._sub_combo.currentIndex()
            worker = _AuthWorker(self._provider)
            self._start_worker(worker)
            worker.start_azure_phase2(self._azure_subs, idx)
            return

        api_key = self._api_key_input.text().strip() if not self._api_key_input.isHidden() else ""
        profile = self._profile_combo.currentData() or "" if not self._profile_combo.isHidden() else ""

        worker = _AuthWorker(self._provider, api_key=api_key, profile=profile)
        self._start_worker(worker)
        worker.start()

    def _start_worker(self, worker: _AuthWorker) -> None:
        self._worker = worker
        worker.log_line.connect(self._on_log_line)
        worker.auth_done.connect(self._on_auth_done)
        worker.azure_subs_ready.connect(self._on_azure_subs_ready)
        worker.gcp_projects_ready.connect(self._on_gcp_projects_ready)
        self._btn_connect.setEnabled(False)
        self._btn_connect.setText("Connecting…")

    # ------------------------------------------------------------------
    # Worker signal handlers (called on GUI thread)
    # ------------------------------------------------------------------
    def _on_log_line(self, text: str, level: str) -> None:
        color = _LOG_COLORS.get(level, TEXT_PRIMARY)
        # Escape HTML special chars
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # Preserve newlines
        safe = safe.replace("\n", "<br>")
        self._log_area.appendHtml(f'<span style="color:{color}">{safe}</span>')

    def _on_auth_done(self, success: bool) -> None:
        if success:
            self._btn_cancel.setText("Close")
            # Give user a moment to read the success message, then close
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1200, self.accept)
        else:
            self._btn_connect.setEnabled(True)
            self._btn_connect.setText("Retry")

    def _on_gcp_projects_ready(self, projects: list[str]) -> None:
        self._gcp_projects = projects
        self._gcp_project_combo.clear()
        for p in projects:
            self._gcp_project_combo.addItem(p)
        self._gcp_project_combo.show()
        self._btn_connect.setEnabled(True)
        self._btn_connect.setText("Select Project")
        self._log("\nSelect a project above, then click Select Project.", "info")

    def _on_azure_subs_ready(self, subs: list[dict]) -> None:
        self._azure_subs = subs
        self._sub_combo.clear()
        for sub in subs:
            default = " ✓" if sub.get("isDefault") else ""
            self._sub_combo.addItem(
                f"{sub.get('name', '')}  [{sub.get('id', '')}]{default}"
            )
        self._sub_combo.show()
        self._api_key_input.hide()
        self._btn_connect.setEnabled(True)
        self._btn_connect.setText("Select Subscription")
        self._log("\nSelect a subscription above, then click Select Subscription.", "info")

    # ------------------------------------------------------------------
    # Internal log helper (for setup messages before worker starts)
    # ------------------------------------------------------------------
    def _log(self, text: str, level: str = "normal") -> None:
        color = _LOG_COLORS.get(level, TEXT_PRIMARY)
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe = safe.replace("\n", "<br>")
        self._log_area.appendHtml(f'<span style="color:{color}">{safe}</span>')
