"""Region / profile / project selector controls for the provider nav sidebar."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from spancloud.gui.theme import (
    ACCENT_BLUE,
    BG_ELEVATED,
    BORDER_SUBTLE,
    TEXT_MUTED,
    TEXT_PRIMARY,
)

# ---------------------------------------------------------------------------
# Region lists — mirrors the TUI
# ---------------------------------------------------------------------------
_REGIONS: dict[str, list[tuple[str, str]]] = {
    "aws": [
        ("All Regions", ""),
        ("us-east-1 (N. Virginia)", "us-east-1"),
        ("us-east-2 (Ohio)", "us-east-2"),
        ("us-west-1 (N. California)", "us-west-1"),
        ("us-west-2 (Oregon)", "us-west-2"),
        ("eu-west-1 (Ireland)", "eu-west-1"),
        ("eu-west-2 (London)", "eu-west-2"),
        ("eu-central-1 (Frankfurt)", "eu-central-1"),
        ("ap-southeast-1 (Singapore)", "ap-southeast-1"),
        ("ap-southeast-2 (Sydney)", "ap-southeast-2"),
        ("ap-northeast-1 (Tokyo)", "ap-northeast-1"),
    ],
    "gcp": [
        ("All Regions", ""),
        ("us-central1 (Iowa)", "us-central1"),
        ("us-east1 (S. Carolina)", "us-east1"),
        ("us-west1 (Oregon)", "us-west1"),
        ("europe-west1 (Belgium)", "europe-west1"),
        ("europe-west2 (London)", "europe-west2"),
        ("asia-east1 (Taiwan)", "asia-east1"),
        ("asia-southeast1 (Singapore)", "asia-southeast1"),
    ],
    "azure": [
        ("All Regions", ""),
        ("eastus (East US)", "eastus"),
        ("eastus2 (East US 2)", "eastus2"),
        ("westus (West US)", "westus"),
        ("westus2 (West US 2)", "westus2"),
        ("westus3 (West US 3)", "westus3"),
        ("centralus (Central US)", "centralus"),
        ("northeurope (North Europe)", "northeurope"),
        ("westeurope (West Europe)", "westeurope"),
        ("uksouth (UK South)", "uksouth"),
        ("southeastasia (SE Asia)", "southeastasia"),
        ("japaneast (Japan East)", "japaneast"),
        ("australiaeast (Australia East)", "australiaeast"),
    ],
    "digitalocean": [
        ("All Regions", ""),
        ("nyc1 (New York 1)", "nyc1"),
        ("nyc3 (New York 3)", "nyc3"),
        ("sfo2 (San Francisco 2)", "sfo2"),
        ("sfo3 (San Francisco 3)", "sfo3"),
        ("ams3 (Amsterdam 3)", "ams3"),
        ("sgp1 (Singapore 1)", "sgp1"),
        ("lon1 (London 1)", "lon1"),
        ("fra1 (Frankfurt 1)", "fra1"),
        ("tor1 (Toronto 1)", "tor1"),
        ("blr1 (Bangalore 1)", "blr1"),
        ("syd1 (Sydney 1)", "syd1"),
    ],
    "vultr": [
        ("All Regions", ""),
        ("ewr (New Jersey)", "ewr"),
        ("ord (Chicago)", "ord"),
        ("dfw (Dallas)", "dfw"),
        ("lax (Los Angeles)", "lax"),
        ("atl (Atlanta)", "atl"),
        ("sea (Seattle)", "sea"),
        ("mia (Miami)", "mia"),
        ("ams (Amsterdam)", "ams"),
        ("fra (Frankfurt)", "fra"),
        ("sgp (Singapore)", "sgp"),
        ("nrt (Tokyo)", "nrt"),
        ("syd (Sydney)", "syd"),
    ],
    "oci": [
        ("All Regions", ""),
        ("us-ashburn-1 (Ashburn)", "us-ashburn-1"),
        ("us-phoenix-1 (Phoenix)", "us-phoenix-1"),
        ("us-chicago-1 (Chicago)", "us-chicago-1"),
        ("eu-frankfurt-1 (Frankfurt)", "eu-frankfurt-1"),
        ("eu-amsterdam-1 (Amsterdam)", "eu-amsterdam-1"),
        ("uk-london-1 (London)", "uk-london-1"),
        ("ap-tokyo-1 (Tokyo)", "ap-tokyo-1"),
        ("ap-singapore-1 (Singapore)", "ap-singapore-1"),
        ("ap-sydney-1 (Sydney)", "ap-sydney-1"),
        ("ca-toronto-1 (Toronto)", "ca-toronto-1"),
    ],
    "alibaba": [
        ("All Regions", ""),
        ("cn-hangzhou (Hangzhou)", "cn-hangzhou"),
        ("cn-shanghai (Shanghai)", "cn-shanghai"),
        ("cn-beijing (Beijing)", "cn-beijing"),
        ("cn-shenzhen (Shenzhen)", "cn-shenzhen"),
        ("cn-hongkong (Hong Kong)", "cn-hongkong"),
        ("us-west-1 (Silicon Valley)", "us-west-1"),
        ("us-east-1 (Virginia)", "us-east-1"),
        ("eu-central-1 (Frankfurt)", "eu-central-1"),
        ("ap-southeast-1 (Singapore)", "ap-southeast-1"),
        ("ap-northeast-1 (Tokyo)", "ap-northeast-1"),
    ],
}

_COMBO_STYLE = f"""
    QComboBox {{
        background: {BG_ELEVATED};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 5px;
        color: {TEXT_PRIMARY};
        font-size: 11px;
        padding: 4px 8px;
        min-height: 24px;
    }}
    QComboBox:hover {{
        border: 1px solid {ACCENT_BLUE};
    }}
    QComboBox:focus {{
        border: 1px solid {ACCENT_BLUE};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox::down-arrow {{
        image: none;
        border-left: 4px solid transparent;
        border-right: 4px solid transparent;
        border-top: 5px solid {TEXT_MUTED};
        width: 0;
        height: 0;
        margin-right: 6px;
    }}
    QComboBox QAbstractItemView {{
        background: #24283b;
        border: 1px solid {BORDER_SUBTLE};
        color: {TEXT_PRIMARY};
        selection-background-color: {ACCENT_BLUE};
        selection-color: #ffffff;
        outline: none;
        font-size: 11px;
    }}
    QComboBox QAbstractItemView::item {{
        padding: 5px 10px;
        min-height: 22px;
    }}
"""

_LABEL_STYLE = f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 600; letter-spacing: 1px;"


def _load_aws_profiles() -> list[tuple[str, str]]:
    """Return real AWS profiles from ~/.aws/config."""
    try:
        from spancloud.providers.aws.auth import AWSAuth
        profiles = AWSAuth.list_configured_profiles()
        if profiles:
            return [(p["name"], p["name"]) for p in profiles]
    except Exception:
        pass
    return [("default", "default")]


class ProviderControls(QWidget):
    """Compact selector bar shown at the top of the provider inner sidebar."""

    region_changed       = Signal(str)   # region slug, "" = all
    profile_changed      = Signal(str)   # AWS profile name
    organization_changed = Signal(str)   # GCP organization ID, "" = all
    project_changed      = Signal(str)   # GCP project ID
    subscription_changed = Signal(str)   # Azure subscription ID

    def __init__(self, provider_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._provider_name = provider_name
        self._all_gcp_projects: list[dict] = []
        self._build()

    def _build(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 8, 10, 4)
        v.setSpacing(6)

        regions = _REGIONS.get(self._provider_name)

        # AWS-specific: profile picker populated from real ~/.aws/config
        if self._provider_name == "aws":
            v.addWidget(self._label("AWS PROFILE"))
            self._profile_combo = self._make_combo(
                _load_aws_profiles(), "profile_changed"
            )
            v.addWidget(self._profile_combo)

        # Azure-specific: subscription picker — starts with current sub, filled after auth
        if self._provider_name == "azure":
            v.addWidget(self._label("SUBSCRIPTION"))
            self._subscription_combo = QComboBox()
            self._subscription_combo.setStyleSheet(_COMBO_STYLE)
            self._subscription_combo.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            self._subscription_combo.setEnabled(False)
            self._subscription_combo.addItem("loading…", "")
            self._subscription_combo.currentIndexChanged.connect(
                lambda idx, c=self._subscription_combo: self.subscription_changed.emit(
                    c.itemData(idx) or ""
                )
            )
            v.addWidget(self._subscription_combo)

        # GCP-specific: org picker (hidden until ≥2 orgs known) + project picker
        if self._provider_name == "gcp":
            self._org_label = self._label("GCP ORGANIZATION")
            self._org_label.hide()
            v.addWidget(self._org_label)

            self._org_combo = QComboBox()
            self._org_combo.setStyleSheet(_COMBO_STYLE)
            self._org_combo.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            self._org_combo.hide()
            self._org_combo.currentIndexChanged.connect(
                lambda idx, c=self._org_combo: self._on_org_changed(c.itemData(idx) or "")
            )
            v.addWidget(self._org_combo)

            v.addWidget(self._label("GCP PROJECT"))
            self._project_combo = QComboBox()
            self._project_combo.setStyleSheet(_COMBO_STYLE)
            self._project_combo.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            self._project_combo.setEnabled(False)
            self._project_combo.addItem("loading…", "")
            self._project_combo.currentIndexChanged.connect(
                lambda idx, c=self._project_combo: self.project_changed.emit(
                    c.itemData(idx) or ""
                )
            )
            v.addWidget(self._project_combo)

        # Region picker (all providers)
        if regions:
            v.addWidget(self._label("REGION"))
            self._region_combo = self._make_combo(regions, "region_changed")
            v.addWidget(self._region_combo)

        # Separator line
        if regions or self._provider_name in ("aws", "gcp", "azure"):
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"color: {BORDER_SUBTLE}; margin-top: 4px;")
            v.addWidget(sep)

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(_LABEL_STYLE)
        return lbl

    def _make_combo(
        self, options: list[tuple[str, str]], signal_name: str
    ) -> QComboBox:
        combo = QComboBox()
        combo.setStyleSheet(_COMBO_STYLE)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for label, value in options:
            combo.addItem(label, userData=value)

        signal: Signal = getattr(self, signal_name)
        combo.currentIndexChanged.connect(
            lambda idx, c=combo, s=signal: s.emit(c.itemData(idx) or "")
        )
        return combo

    def populate_gcp_organizations(self, orgs: list[dict]) -> None:
        """Show the org picker only when ≥2 organizations are found.

        Called by the parent view after auth succeeds and orgs are fetched.
        """
        if not hasattr(self, "_org_combo"):
            return
        if len(orgs) < 2:
            return  # single org or personal account — keep picker hidden
        combo = self._org_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("All Organizations", "")
        for org in orgs:
            combo.addItem(org["display_name"], org["id"])
        combo.blockSignals(False)
        self._org_label.show()
        self._org_combo.show()

    def populate_gcp_projects(
        self, projects: list[dict], active_project: str = ""
    ) -> None:
        """Fill the GCP project combo from the resource-manager API response.

        Called by the parent view after auth succeeds and projects are fetched.
        Stores the full list for org-based filtering.
        """
        if not hasattr(self, "_project_combo"):
            return
        self._all_gcp_projects = projects
        self._fill_project_combo(projects, active_project)

    def _fill_project_combo(self, projects: list[dict], active_project: str = "") -> None:
        combo = self._project_combo
        combo.blockSignals(True)
        combo.clear()
        if not projects:
            active = active_project or "(none)"
            combo.addItem(active, active)
        else:
            for p in projects:
                pid = p["project_id"]
                label = pid if p["name"] == pid else f"{pid}  — {p['name']}"
                combo.addItem(label, pid)
            if active_project and not any(
                combo.itemData(i) == active_project for i in range(combo.count())
            ):
                combo.insertItem(0, active_project, active_project)
        combo.setEnabled(True)
        if active_project:
            for i in range(combo.count()):
                if combo.itemData(i) == active_project:
                    combo.setCurrentIndex(i)
                    break
        combo.blockSignals(False)

    def _on_org_changed(self, org_id: str) -> None:
        self.organization_changed.emit(org_id)
        active = (self._project_combo.currentData() or "") if hasattr(self, "_project_combo") else ""
        filtered = [
            p for p in self._all_gcp_projects
            if not org_id or p.get("org_id", "") == org_id
        ]
        self._fill_project_combo(filtered, active)

    def populate_azure_subscriptions(
        self, subscriptions: list[dict], active_id: str = ""
    ) -> None:
        """Fill the Azure subscription combo. Called after auth succeeds."""
        if not hasattr(self, "_subscription_combo"):
            return
        combo = self._subscription_combo
        combo.blockSignals(True)
        combo.clear()
        if not subscriptions:
            label = active_id or "(none)"
            combo.addItem(label, active_id)
        else:
            for s in subscriptions:
                sid = s.get("id", "")
                name = s.get("display_name", sid)
                combo.addItem(f"{name}  ({sid[:8]}…)", sid)
            if active_id and not any(
                combo.itemData(i) == active_id for i in range(combo.count())
            ):
                combo.insertItem(0, active_id, active_id)
        combo.setEnabled(len(subscriptions) > 1)
        if active_id:
            for i in range(combo.count()):
                if combo.itemData(i) == active_id:
                    combo.setCurrentIndex(i)
                    break
        combo.blockSignals(False)

    def set_active_profile(self, profile: str) -> None:
        """Select the given AWS profile in the combo (called after auth check)."""
        if not hasattr(self, "_profile_combo"):
            return
        combo = self._profile_combo
        for i in range(combo.count()):
            if combo.itemData(i) == profile:
                combo.blockSignals(True)
                combo.setCurrentIndex(i)
                combo.blockSignals(False)
                return

    def current_region(self) -> str:
        if hasattr(self, "_region_combo"):
            return self._region_combo.currentData() or ""
        return ""

    def current_profile(self) -> str:
        if hasattr(self, "_profile_combo"):
            return self._profile_combo.currentData() or ""
        return ""

    def current_organization(self) -> str:
        if hasattr(self, "_org_combo"):
            return self._org_combo.currentData() or ""
        return ""

    def current_project(self) -> str:
        if hasattr(self, "_project_combo"):
            return self._project_combo.currentData() or ""
        return ""

    def current_subscription(self) -> str:
        if hasattr(self, "_subscription_combo"):
            return self._subscription_combo.currentData() or ""
        return ""
