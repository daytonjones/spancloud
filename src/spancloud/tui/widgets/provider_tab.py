"""Provider tab — resource-type sidebar + resource table + detail + analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import DataTable, Input, ListItem, ListView, Select, Static

from spancloud.core.resource import Resource, ResourceType
from spancloud.utils.logging import get_logger

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from spancloud.core.provider import BaseProvider

logger = get_logger(__name__)

_ANALYSIS_ITEMS = ["cost", "audit", "unused", "relationships", "alerts", "metrics"]

_MOCK_COST_TUI: dict[str, tuple[str, str, str, str]] = {
    "aws":          ("$4,821.40", "+$312.90", "$4,508.50", "EC2 Instances, S3 Storage, RDS, Lambda"),
    "gcp":          ("$2,340.10", "+$187.20", "$2,152.90", "Compute Engine, Cloud Storage, Cloud SQL, Functions"),
    "azure":        ("$3,102.75", "+$241.30", "$2,861.45", "Virtual Machines, Blob Storage, Azure SQL, App Service"),
    "digitalocean": ("$890.50",   "+$62.10",  "$828.40",   "Droplets, Spaces, Managed DBs, Kubernetes"),
    "vultr":        ("$412.20",   "+$28.80",  "$383.40",   "Cloud Compute, Block Storage, Managed DBs"),
    "oci":          ("$1,230.60", "+$94.50",  "$1,136.10", "Compute Instances, Object Storage, Autonomous DB"),
    "alibaba":      ("$1,875.30", "+$143.70", "$1,731.60", "ECS Instances, OSS Storage, ApsaraDB RDS"),
}
_MOCK_FINDINGS_TUI: dict[str, list[tuple[str, str]]] = {
    "aws":          [("HIGH",   "S3 bucket 'dev-scratch-bucket' has public read ACL"),
                     ("MEDIUM", "IAM user 'alice@example.com' has no MFA enabled"),
                     ("LOW",    "EC2 instance 'dev-sandbox' uses default security group")],
    "gcp":          [("MEDIUM", "Cloud Storage bucket 'demo-staging-data' is publicly accessible"),
                     ("LOW",    "GKE cluster 'prod-gke' has legacy ABAC enabled")],
    "azure":        [("HIGH",   "Storage account 'devstgacct' allows public blob access"),
                     ("MEDIUM", "VM 'dev-vm-01' has no disk encryption")],
    "digitalocean": [("LOW",    "Droplet 'staging-droplet' has no firewall rule assigned")],
    "vultr":        [("MEDIUM", "Instance 'staging-01' uses SSH password authentication")],
    "oci":          [("LOW",    "Object storage bucket 'archive-storage' has no lifecycle policy")],
    "alibaba":      [("MEDIUM", "ECS instance 'worker-ecs-01' security group allows 0.0.0.0/0 on port 22")],
}
_MOCK_UNUSED_TUI: dict[str, list[tuple[str, str, str, str]]] = {
    "aws":          [("COMPUTE",  "dev-sandbox",         "Stopped 47 days",   "$14.40/mo"),
                     ("STORAGE",  "dev-scratch-bucket",  "No access 90+ days","$2.10/mo"),
                     ("DATABASE", "analytics-pg",        "Stopped 62 days",   "$48.20/mo")],
    "gcp":          [("COMPUTE",  "worker-01",           "Stopped 31 days",   "$38.50/mo")],
    "azure":        [("COMPUTE",  "dev-vm-01",           "Stopped 28 days",   "$31.20/mo")],
    "digitalocean": [("COMPUTE",  "staging-droplet",     "Stopped 19 days",   "$12.00/mo"),
                     ("STORAGE",  "staging-data-volume", "Unattached 14 days","$5.00/mo")],
    "vultr":        [("COMPUTE",  "staging-01",          "Stopped 22 days",   "$6.00/mo")],
    "oci":          [],
    "alibaba":      [],
}
_MOCK_RELS_TUI: dict[str, list[tuple[str, str, str, str, str]]] = {
    "aws":          [("ALB",     "prod-alb",       "routes to",   "EC2",      "web-prod-01"),
                     ("ALB",     "prod-alb",       "routes to",   "EC2",      "api-prod-01"),
                     ("EC2",     "web-prod-01",    "writes to",   "S3",       "prod-assets-bucket"),
                     ("EC2",     "api-prod-01",    "connects to", "RDS",      "prod-postgres"),
                     ("Lambda",  "api-handler",    "connects to", "RDS",      "prod-mysql"),
                     ("EKS",     "prod-cluster",   "runs in",     "VPC",      "prod-vpc")],
    "gcp":          [("GKE",     "prod-gke",       "runs in",     "VPC",      "default"),
                     ("VM",      "api-01",         "connects to", "CloudSQL", "prod-postgres"),
                     ("Function","api-handler",    "connects to", "CloudSQL", "prod-postgres")],
    "azure":        [("VM",      "web-vm-01",      "reads from",  "Storage",  "prodstgacct"),
                     ("VM",      "api-vm-01",      "connects to", "SQL",      "prod-sql")],
    "digitalocean": [("Droplet", "web-droplet-01", "attached to", "Volume",   "prod-data-volume")],
    "vultr":        [("VM",      "web-01",         "attached to", "Block",    "prod-block-storage")],
    "oci":          [("VM",      "web-instance-01","runs in",     "VCN",      "prod-vcn")],
    "alibaba":      [("ECS",     "web-ecs-01",     "connects to", "RDS",      "prod-rds")],
}


def _mock_analysis_tui(name: str, key: str) -> str:
    if key == "cost":
        total, delta, last, svcs = _MOCK_COST_TUI.get(
            name, ("—", "—", "—", "no data")
        )
        lines = [
            f"[bold]Cost Summary[/bold]  [dim]Demo data · current month[/dim]\n",
            f"  [cyan]Total (MTD)[/cyan]       [bold green]{total}[/bold green]",
            f"  [cyan]vs last month[/cyan]     [yellow]{delta}[/yellow]",
            f"  [cyan]Last month[/cyan]        {last}\n",
            f"  [dim]Top services:[/dim]  {svcs}",
        ]
        return "\n".join(lines)

    if key == "audit":
        findings = _MOCK_FINDINGS_TUI.get(name, [])
        if not findings:
            return "[bold green]No security issues found (demo data)[/bold green]"
        sev_color = {"HIGH": "bold red", "CRITICAL": "bold red", "MEDIUM": "yellow", "LOW": "dim"}
        lines = [f"[bold]Security Audit[/bold]  [dim]Demo data · {len(findings)} finding(s)[/dim]\n"]
        for sev, msg in findings:
            color = sev_color.get(sev, "white")
            lines.append(f"  [{color}][{sev}][/{color}]  {msg}")
        return "\n".join(lines)

    if key == "unused":
        items = _MOCK_UNUSED_TUI.get(name, [])
        if not items:
            return "[bold green]No idle resources detected (demo data)[/bold green]"
        lines = [f"[bold]Unused Resources[/bold]  [dim]Demo data · {len(items)} item(s)[/dim]\n"]
        for rtype, rname, age, cost in items:
            lines.append(f"  [bold]{rtype}[/bold]  {rname}")
            lines.append(f"    {age}  [yellow]{cost}[/yellow]")
            lines.append("")
        return "\n".join(lines)

    if key == "relationships":
        edges = _MOCK_RELS_TUI.get(name, [])
        if not edges:
            return "[dim]No relationships to display (demo data)[/dim]"
        from collections import defaultdict
        by_src: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
        for ft, fn, edge, tt, tn in edges:
            by_src[f"{ft}:{fn}"].append((edge, tt, tn))
        lines = [f"[bold]Resource Relationships[/bold]  [dim]Demo data · {len(edges)} connection(s)[/dim]\n"]
        for src, rels in by_src.items():
            lines.append(f"  [bold]{src}[/bold]")
            for edge, tt, tn in rels:
                lines.append(f"    [cyan]{edge}[/cyan] → [{tt}] {tn}")
            lines.append("")
        return "\n".join(lines)

    if key == "alerts":
        return "[bold]Monitoring Alerts[/bold]  [dim]Demo data[/dim]\n\n  [green]✓ No active alerts — all systems nominal[/green]"

    return f"[yellow]Analysis not available in demo mode.[/yellow]"

_RT_ICONS: dict[str, str] = {
    "compute": "\U0001f5a5  compute",
    "storage": "\U0001f4e6 storage",
    "network": "\U0001f310 network",
    "database": "\U0001f4be database",
    "serverless": "\u26a1 serverless",
    "load_balancer": "\u2696  load balancer",
    "container": "\U0001f4e6 container",
    "dns": "\U0001f310 dns",
    "iam": "\U0001f512 iam",
    "other": "\U0001f4cb other",
}

_ANALYSIS_LABELS: dict[str, str] = {
    "cost": "\U0001f4b0 cost summary",
    "audit": "\U0001f6e1  security audit",
    "unused": "\U0001f5d1  unused resources",
    "relationships": "\U0001f517 relationships",
    "alerts": "\U0001f514 monitoring alerts",
    "metrics": "\U0001f4ca metrics",
}

_STATE_STYLES: dict[str, str] = {
    "running": "bold green",
    "stopped": "bold red",
    "pending": "bold yellow",
    "terminated": "dim red",
    "error": "bold red reverse",
    "unknown": "dim",
}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class ResourceTypeSelected(Message):
    def __init__(self, resource_type: ResourceType, provider: BaseProvider) -> None:
        self.resource_type = resource_type
        self.provider = provider
        super().__init__()


class AnalysisSelected(Message):
    def __init__(self, analysis_type: str, provider: BaseProvider) -> None:
        self.analysis_type = analysis_type
        self.provider = provider
        super().__init__()


class ExtendedScanSelected(Message):
    """Emitted when the user wants to scan extended/all services."""

    def __init__(self, provider: BaseProvider) -> None:
        self.provider = provider
        super().__init__()


class ProfileChanged(Message):
    def __init__(self, profile_name: str, provider: BaseProvider) -> None:
        self.profile_name = profile_name
        self.provider = provider
        super().__init__()


class ProjectChanged(Message):
    """Emitted when the GCP project picker changes selection."""

    def __init__(self, project_id: str, provider: BaseProvider) -> None:
        self.project_id = project_id
        self.provider = provider
        super().__init__()


class SubscriptionChanged(Message):
    """Emitted when the Azure subscription picker changes selection."""

    def __init__(self, subscription_id: str, provider: BaseProvider) -> None:
        self.subscription_id = subscription_id
        self.provider = provider
        super().__init__()


class SettingsRequested(Message):
    """Emitted when sidebar settings is clicked."""

    def __init__(self, provider: BaseProvider) -> None:
        self.provider = provider
        super().__init__()


class RegionChanged(Message):
    def __init__(self, region: str, provider: BaseProvider) -> None:
        self.region = region  # "" means all/default
        self.provider = provider
        super().__init__()


# Common regions per provider
_AWS_REGIONS = [
    ("All Regions", ""),
    ("us-east-1", "us-east-1"),
    ("us-east-2", "us-east-2"),
    ("us-west-1", "us-west-1"),
    ("us-west-2", "us-west-2"),
    ("eu-west-1", "eu-west-1"),
    ("eu-west-2", "eu-west-2"),
    ("eu-central-1", "eu-central-1"),
    ("ap-southeast-1", "ap-southeast-1"),
    ("ap-southeast-2", "ap-southeast-2"),
    ("ap-northeast-1", "ap-northeast-1"),
]

_GCP_REGIONS = [
    ("All Regions", ""),
    ("us-central1", "us-central1"),
    ("us-east1", "us-east1"),
    ("us-west1", "us-west1"),
    ("europe-west1", "europe-west1"),
    ("europe-west2", "europe-west2"),
    ("asia-east1", "asia-east1"),
    ("asia-southeast1", "asia-southeast1"),
]

_VULTR_REGIONS = [
    ("All Regions", ""),
    ("ewr", "ewr"),
    ("ord", "ord"),
    ("dfw", "dfw"),
    ("lax", "lax"),
    ("atl", "atl"),
    ("sea", "sea"),
    ("mia", "mia"),
    ("ams", "ams"),
    ("fra", "fra"),
    ("sgp", "sgp"),
    ("nrt", "nrt"),
    ("syd", "syd"),
]

_DO_REGIONS = [
    ("All Regions", ""),
    ("nyc1", "nyc1"),
    ("nyc3", "nyc3"),
    ("sfo2", "sfo2"),
    ("sfo3", "sfo3"),
    ("ams3", "ams3"),
    ("sgp1", "sgp1"),
    ("lon1", "lon1"),
    ("fra1", "fra1"),
    ("tor1", "tor1"),
    ("blr1", "blr1"),
    ("syd1", "syd1"),
]

_AZURE_REGIONS = [
    ("All Regions", ""),
    ("eastus", "eastus"),
    ("eastus2", "eastus2"),
    ("westus", "westus"),
    ("westus2", "westus2"),
    ("westus3", "westus3"),
    ("centralus", "centralus"),
    ("northeurope", "northeurope"),
    ("westeurope", "westeurope"),
    ("uksouth", "uksouth"),
    ("southeastasia", "southeastasia"),
    ("japaneast", "japaneast"),
    ("australiaeast", "australiaeast"),
]

_OCI_REGIONS = [
    ("All Regions", ""),
    ("us-ashburn-1", "us-ashburn-1"),
    ("us-phoenix-1", "us-phoenix-1"),
    ("us-chicago-1", "us-chicago-1"),
    ("us-sanjose-1", "us-sanjose-1"),
    ("eu-frankfurt-1", "eu-frankfurt-1"),
    ("eu-amsterdam-1", "eu-amsterdam-1"),
    ("uk-london-1", "uk-london-1"),
    ("ap-tokyo-1", "ap-tokyo-1"),
    ("ap-singapore-1", "ap-singapore-1"),
    ("ap-sydney-1", "ap-sydney-1"),
    ("ca-toronto-1", "ca-toronto-1"),
]

_ALIBABA_REGIONS = [
    ("All Regions", ""),
    ("cn-hangzhou", "cn-hangzhou"),
    ("cn-shanghai", "cn-shanghai"),
    ("cn-beijing", "cn-beijing"),
    ("cn-shenzhen", "cn-shenzhen"),
    ("cn-hongkong", "cn-hongkong"),
    ("us-west-1", "us-west-1"),
    ("us-east-1", "us-east-1"),
    ("eu-central-1", "eu-central-1"),
    ("eu-west-1", "eu-west-1"),
    ("ap-southeast-1", "ap-southeast-1"),
    ("ap-northeast-1", "ap-northeast-1"),
    ("ap-south-1", "ap-south-1"),
]


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


class ResourceTypeSidebar(Vertical):
    """Sidebar listing resource types and analysis tools."""

    def __init__(self, provider: BaseProvider) -> None:
        super().__init__()
        self._provider = provider
        self._gcp_selectors_loaded: bool = False
        self._gcp_all_projects: list[dict] = []  # full list for org-based filtering

    def compose(self) -> ComposeResult:
        yield Static(
            f"[bold]{self._provider.display_name}[/bold]",
            classes="sidebar-header",
        )
        yield Static(
            "[dim]checking...[/dim]",
            classes="auth-status",
            id=f"auth-{self._provider.name}",
        )

        # AWS profile switcher
        if self._provider.name == "aws":
            from spancloud.providers.aws.auth import AWSAuth

            profiles = AWSAuth.list_configured_profiles()
            if len(profiles) > 1:
                options = [(p["name"], p["name"]) for p in profiles]
                yield Select(
                    options,
                    prompt="Profile",
                    id=f"profile-select-{self._provider.name}",
                    allow_blank=False,
                )

        # GCP selectors — org (hidden until 2+ orgs found) + project
        if self._provider.name == "gcp":
            yield Select(
                [("", "")],
                prompt="\U0001f3e2 Org",
                id=f"org-select-{self._provider.name}",
                allow_blank=False,
                disabled=True,
                classes="hidden",
            )
            yield Select(
                [("loading...", "")],
                prompt="\U0001f5c2 Project",
                id=f"project-select-{self._provider.name}",
                allow_blank=False,
                disabled=True,
            )

        # OCI profile picker — populated from ~/.oci/config at compose time
        if self._provider.name == "oci":
            try:
                from spancloud.providers.oci.auth import OCIAuth
                oci_profiles = [(p, p) for p in OCIAuth().list_profiles()]
            except Exception:
                oci_profiles = []
            if len(oci_profiles) > 1:
                yield Select(
                    oci_profiles,
                    prompt="\U0001f464 Profile",
                    id=f"profile-select-{self._provider.name}",
                    allow_blank=False,
                )

        # Azure subscription picker — populated after auth
        if self._provider.name == "azure":
            yield Select(
                [("loading...", "")],
                prompt="\U0001f4b3 Subscription",
                id=f"subscription-select-{self._provider.name}",
                allow_blank=False,
                disabled=True,
            )

        # Region selector
        region_options = {
            "aws": _AWS_REGIONS,
            "gcp": _GCP_REGIONS,
            "vultr": _VULTR_REGIONS,
            "digitalocean": _DO_REGIONS,
            "azure": _AZURE_REGIONS,
            "oci": _OCI_REGIONS,
            "alibaba": _ALIBABA_REGIONS,
        }.get(self._provider.name)

        if region_options:
            yield Select(
                region_options,
                prompt="\U0001f30d Region",
                value="",
                id=f"region-select-{self._provider.name}",
                allow_blank=False,
            )

        # Build sidebar from user config
        from spancloud.config.sidebar import get_sidebar_items

        sidebar_items = get_sidebar_items(self._provider.name)

        items: list[ListItem] = [
            ListItem(
                Static("  \U0001f4cb [bold]all resources[/bold]"),
                id=f"rt-{self._provider.name}-all",
                name="all",
            ),
        ]

        for svc in sidebar_items:
            items.append(
                ListItem(
                    Static(f"  {svc['label']}"),
                    id=f"rt-{self._provider.name}-{svc['name']}",
                    name=svc["name"],
                )
            )

        # Extended services (AWS only — scan via generic scanner)
        if self._provider.name == "aws":
            items.append(
                ListItem(
                    Static("  [bold magenta]\U0001f50d browse extended...[/bold magenta]"),
                    id=f"rt-{self._provider.name}-extended",
                    name="_extended",
                )
            )

        # Separator + analysis
        items.append(
            ListItem(
                Static("  [dim]────────────────[/dim]"),
                id=f"rt-{self._provider.name}-sep",
                name="_separator",
            )
        )
        # Skip alerts and metrics for Vultr (no monitoring API)
        for key in _ANALYSIS_ITEMS:
            if key in ("alerts", "metrics") and self._provider.name == "vultr":
                continue
            items.append(
                ListItem(
                    Static(f"  [cyan]{_ANALYSIS_LABELS[key]}[/cyan]"),
                    id=f"rt-{self._provider.name}-{key}",
                    name=key,
                )
            )

        # Settings
        items.append(
            ListItem(
                Static("  [dim]\u2699 sidebar settings[/dim]"),
                id=f"rt-{self._provider.name}-settings",
                name="_settings",
            )
        )

        yield ListView(
            *items,
            id=f"type-list-{self._provider.name}",
        )

    def on_mount(self) -> None:
        self.run_worker(
            self._check_auth(), name=f"tab-auth-{self._provider.name}"
        )

    async def _check_auth(self) -> None:
        status = self.query_one(f"#auth-{self._provider.name}", Static)
        try:
            success = await self._provider.authenticate()
            if success:
                profile = ""
                auth = getattr(self._provider, "_auth", None)
                # active_profile (AWS) or profile property (OCI)
                profile_val = (
                    getattr(auth, "active_profile", None)
                    or getattr(auth, "profile", None)
                    or ""
                )
                if profile_val:
                    profile = f" ({profile_val})"
                    try:
                        select = self.query_one(
                            f"#profile-select-{self._provider.name}", Select
                        )
                        select.value = profile_val
                    except Exception:
                        pass
                status.update(f"[green]authenticated[/green]{profile}")

                # GCP: populate selectors once — skip if already loaded to avoid 429s
                if self._provider.name == "gcp" and not self._gcp_selectors_loaded:
                    self._gcp_selectors_loaded = True
                    await self._populate_gcp_selectors()
                # Azure: populate subscription picker
                if self._provider.name == "azure":
                    await self._populate_azure_subscriptions()
                # OCI: reflect active profile in picker
                if self._provider.name == "oci":
                    active_profile = getattr(
                        getattr(self._provider, "_auth", None), "profile", ""
                    )
                    if active_profile:
                        import contextlib
                        with contextlib.suppress(Exception):
                            sel = self.query_one(
                                f"#profile-select-{self._provider.name}", Select
                            )
                            sel.value = active_profile
            else:
                status.update("[red]not authenticated[/red]")
        except Exception:
            status.update("[red]auth error[/red]")

    async def _populate_gcp_selectors(self) -> None:
        """Fetch GCP orgs + projects and fill the pickers (called once after auth)."""
        import contextlib
        auth = getattr(self._provider, "_auth", None)
        if auth is None:
            return

        # Fetch orgs and projects concurrently
        import asyncio
        orgs, projects = await asyncio.gather(
            self._safe_fetch(auth.list_accessible_organizations()),
            self._safe_fetch(auth.list_accessible_projects()),
        )

        active_project = getattr(auth, "project_id", "") or ""

        # --- Org selector (show only when 2+ orgs) ---
        if len(orgs) >= 2:
            try:
                org_select = self.query_one(f"#org-select-{self._provider.name}", Select)
                org_options = [
                    (o.get("display_name", o["id"]), o["id"]) for o in orgs
                ]
                org_options.insert(0, ("All Organizations", ""))
                org_select.set_options(org_options)
                org_select.disabled = False
                org_select.remove_class("hidden")
            except Exception:
                pass

        # --- Project selector ---
        try:
            proj_select = self.query_one(f"#project-select-{self._provider.name}", Select)
        except Exception:
            return

        if not projects:
            proj_select.set_options([(active_project or "(none)", active_project)])
            proj_select.disabled = True
            return

        self._gcp_all_projects = projects  # cache for org filtering

        options = [
            (
                f"{p['project_id']}" + (f"  — {p['name']}" if p["name"] != p["project_id"] else ""),
                p["project_id"],
            )
            for p in projects
        ]
        if active_project and not any(v == active_project for _, v in options):
            options.insert(0, (active_project, active_project))

        proj_select.set_options(options)
        proj_select.disabled = False
        if active_project:
            with contextlib.suppress(Exception):
                proj_select.value = active_project

    @staticmethod
    async def _safe_fetch(coro: object) -> list:  # type: ignore[type-arg]
        """Await a coroutine, returning [] on any error."""
        import asyncio
        try:
            result = await coro  # type: ignore[misc]
            return result if isinstance(result, list) else []
        except Exception:
            return []

    async def _populate_azure_subscriptions(self) -> None:
        """Fetch Azure subscriptions and fill the picker."""
        import contextlib
        try:
            select = self.query_one(
                f"#subscription-select-{self._provider.name}", Select
            )
        except Exception:
            return
        try:
            auth = getattr(self._provider, "_auth", None)
            subs = await auth.list_subscriptions() if auth else []
        except Exception:
            subs = []
        if not subs:
            select.set_options([("(no subscriptions found)", "")])
            select.disabled = True
            return
        active = getattr(getattr(self._provider, "_auth", None), "subscription_id", "") or ""
        options = [(s.get("display_name", s["id"]), s["id"]) for s in subs]
        if active and not any(v == active for _, v in options):
            options.insert(0, (active, active))
        select.set_options(options)
        select.disabled = len(options) <= 1
        if active:
            with contextlib.suppress(Exception):
                select.value = active

    def _filter_projects_by_org(self, org_id: str) -> None:
        """Filter the project Select to only show projects from the given org."""
        import contextlib
        if not self._gcp_all_projects:
            return
        try:
            proj_select = self.query_one(f"#project-select-{self._provider.name}", Select)
        except Exception:
            return
        filtered = [
            p for p in self._gcp_all_projects
            if not org_id or p.get("org_id", "") == org_id
        ] or self._gcp_all_projects
        options = [
            (
                f"{p['project_id']}" + (f"  — {p['name']}" if p["name"] != p["project_id"] else ""),
                p["project_id"],
            )
            for p in filtered
        ]
        proj_select.set_options(options)
        with contextlib.suppress(Exception):
            proj_select.value = options[0][1]

    def on_select_changed(self, event: Select.Changed) -> None:
        if not event.value or event.value == Select.BLANK:
            return
        select_id = event.select.id or ""
        if select_id.startswith("profile-select-"):
            self.post_message(ProfileChanged(str(event.value), self._provider))
        elif select_id.startswith("org-select-"):
            self._filter_projects_by_org(str(event.value))
        elif select_id.startswith("project-select-"):
            self.post_message(ProjectChanged(str(event.value), self._provider))
        elif select_id.startswith("subscription-select-"):
            self.post_message(SubscriptionChanged(str(event.value), self._provider))
        elif select_id.startswith("region-select-"):
            self.post_message(RegionChanged(str(event.value), self._provider))

    # Map sidebar config names to ResourceType enum values
    _NAME_TO_TYPE: dict[str, str] = {
        # AWS
        "ec2": "compute", "s3": "storage", "vpc": "network",
        "rds": "database", "lambda": "serverless", "elb": "load_balancer",
        "eks": "container", "route53": "dns", "iam": "iam",
        # GCP
        "gce": "compute", "gcs": "storage", "cloudsql": "database",
        "functions": "serverless", "cloudrun": "serverless",
        "gke": "container", "lb": "load_balancer", "dns": "dns",
        # Vultr
        "instances": "compute", "block_storage": "storage",
        "database": "database", "kubernetes": "container",
        # DigitalOcean
        "droplets": "compute", "volumes": "storage",
        "doks": "container",
        # Azure
        "vms": "compute", "storage": "storage", "vnet": "network",
        "sql": "database", "appservice": "serverless", "aks": "container",
        # OCI
        "object_storage": "storage", "vcn": "network",
        "adb": "database", "oke": "container",
        # Alibaba (note: "rds" already defined above for AWS — same mapping)
        "ecs": "compute", "oss": "storage",
        "ack": "container",
        "slb": "load_balancer", "alidns": "dns",
    }

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_name = event.item.name or ""
        if item_name in ("_separator",):
            return
        if item_name == "_settings":
            self.post_message(SettingsRequested(self._provider))
            return
        if item_name in _ANALYSIS_ITEMS:
            self.post_message(AnalysisSelected(item_name, self._provider))
        elif item_name == "_extended":
            self.post_message(ExtendedScanSelected(self._provider))
        elif item_name == "all":
            self.post_message(ResourceTypeSelected(None, self._provider))
        else:
            # Map config name → ResourceType
            type_val = self._NAME_TO_TYPE.get(item_name, item_name)
            try:
                rt = ResourceType(type_val)
                self.post_message(ResourceTypeSelected(rt, self._provider))
            except ValueError:
                # Might be an extended service name — scan it directly
                self.post_message(ExtendedScanSelected(self._provider))


# ---------------------------------------------------------------------------
# Resource table with search, detail panel, row coloring
# ---------------------------------------------------------------------------


class ResourceContentArea(Vertical):
    """Right pane: search bar + resource table + detail panel."""

    BINDINGS = [
        Binding("/", "toggle_search", "Search", show=True),
        Binding("e", "export_resources", "Export", show=True),
        Binding("escape", "close_detail", "Close detail", show=False),
    ]

    def __init__(self, provider: BaseProvider) -> None:
        super().__init__()
        self._provider = provider
        self._resources: list[Resource] = []
        self._filtered: list[Resource] = []
        self._active_region: str = ""  # "" = all/default
        self._active_resource_type: ResourceType | None = None  # track last loaded type
        self._has_loaded: bool = False  # whether we've loaded at least once
        self._resource_map: dict[str, Resource] = {}

    def compose(self) -> ComposeResult:
        yield Input(
            placeholder="\U0001f50d Search resources (name, type, region)...",
            id="search-input",
        )
        yield Static("", id="status-bar")
        yield DataTable(id="resource-table")
        yield VerticalScroll(
            Static("[dim]Click a resource row to see details.[/dim]", id="detail-content"),
            id="detail-panel",
        )

    def on_mount(self) -> None:
        # Set up table
        table = self.query_one("#resource-table", DataTable)
        table.add_columns("Name", "Type", "Subtype", "Region", "State", "Info")
        table.cursor_type = "row"
        table.zebra_stripes = True

        # Start with search hidden, detail hidden
        self.query_one("#search-input", Input).display = False
        self.query_one("#detail-panel").display = False
        self._update_status("Ready — select a resource type from the sidebar")

    def action_toggle_search(self) -> None:
        """Toggle the search input."""
        search = self.query_one("#search-input", Input)
        search.display = not search.display
        if search.display:
            search.focus()
            search.value = ""
        else:
            self._apply_filter("")

    def action_close_detail(self) -> None:
        """Close the detail panel."""
        self.query_one("#detail-panel").display = False

    def action_export_resources(self) -> None:
        """Export currently loaded resources to a file."""
        if not self._resources:
            self.app.notify("No resources to export.", severity="warning")
            return

        from spancloud.tui.screens.export import ExportScreen

        self.app.push_screen(ExportScreen(self._resources))

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter resources as user types."""
        if event.input.id == "search-input":
            self._apply_filter(event.value)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Show detail panel on Enter/double-click."""
        key = str(event.row_key.value) if event.row_key else ""
        resource = self._resource_map.get(key)
        if resource:
            self._show_detail(resource)

    def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        """Show detail panel on single click / cursor move."""
        key = str(event.row_key.value) if event.row_key else ""
        resource = self._resource_map.get(key)
        if resource:
            self._show_detail(resource)

    def _show_detail(self, resource: Resource) -> None:
        """Populate and show the detail panel for a resource."""
        panel = self.query_one("#detail-panel")
        content = self.query_one("#detail-content", Static)

        lines = [
            f"[bold]{resource.display_name}[/bold]  "
            f"[dim]({resource.provider}:{resource.resource_type.value})[/dim]",
            "",
            f"  [bold]ID:[/bold]       {resource.id}",
            f"  [bold]Name:[/bold]     {resource.name}",
            f"  [bold]Type:[/bold]     {resource.resource_type.value}",
            f"  [bold]Region:[/bold]   {resource.region or '—'}",
        ]

        state_style = _STATE_STYLES.get(resource.state.value, "")
        lines.append(
            f"  [bold]State:[/bold]    [{state_style}]{resource.state.value}[/{state_style}]"
        )

        if resource.created_at:
            lines.append(f"  [bold]Created:[/bold]  {resource.created_at}")

        if resource.tags:
            lines.append("\n  [bold]Tags:[/bold]")
            for k, v in sorted(resource.tags.items()):
                lines.append(f"    {k} = {v}")

        if resource.metadata:
            lines.append("\n  [bold]Metadata:[/bold]")
            for k, v in sorted(resource.metadata.items()):
                if v:
                    lines.append(f"    {k} = {v}")

        # Hint for storage resources
        subtype = resource.metadata.get("resource_subtype", "")
        if resource.resource_type.value == "storage" or subtype in (
            "s3_bucket", "gcs_bucket", "block_storage", "object_storage",
        ):
            lines.append(
                "\n  [dim italic]Use CLI for full storage details: "
                "spancloud s3 info / gcs info / vultr block-info[/dim italic]"
            )

        content.update("\n".join(lines))
        panel.display = True

    def reload(self) -> None:
        """Reload the current view with the same resource type."""
        if self._has_loaded:
            self.load_resources(self._active_resource_type)

    @work(exclusive=True)
    async def load_extended(self) -> None:
        """Scan extended AWS services via the generic scanner."""
        import time

        start_time = time.monotonic()
        table = self.query_one("#resource-table", DataTable)
        table.clear()
        table.loading = True
        self._resources = []
        self._filtered = []
        self._resource_map = {}
        self.query_one("#detail-panel").display = False
        self._update_status("Scanning extended services...")
        self._has_loaded = True

        try:
            if (
                not await self._provider.is_authenticated()
                and not await self._provider.authenticate()
            ):
                self._update_status(
                    "[red]Not authenticated — click provider "
                    "on Overview to log in[/red]"
                )
                return

            from spancloud.providers.aws.services import AWSServiceScanner

            scanner = AWSServiceScanner(self._provider._auth)
            all_resources = await scanner.scan_all(
                region=self._active_region or None
            )

            self._resources = sorted(
                all_resources, key=lambda x: (x.resource_type.value, x.name)
            )
            self._filtered = list(self._resources)
            self._populate_table(self._filtered)

            elapsed = time.monotonic() - start_time
            self._update_status(
                f"{len(self._resources):,} extended resource(s) scanned | "
                f"in {elapsed:.1f}s | "
                f"[dim]click row for details | / to search[/dim]"
            )
        except Exception as exc:
            logger.error("Extended scan failed: %s", exc)
            self._update_status(f"[red]Error: {exc}[/red]")
        finally:
            table.loading = False

    @work(exclusive=True)
    async def load_resources(self, resource_type: ResourceType | None) -> None:
        """Fetch and display resources."""
        import time

        start_time = time.monotonic()
        self._active_resource_type = resource_type
        self._has_loaded = True
        table = self.query_one("#resource-table", DataTable)
        table.clear()
        table.loading = True
        self._resources = []
        self._filtered = []
        self._resource_map = {}
        self.query_one("#detail-panel").display = False
        self._update_status("Loading...")

        # Clear search
        search = self.query_one("#search-input", Input)
        if search.display:
            search.value = ""

        try:
            # Always try authenticate — picks up keys set via auth modal
            if (
                not await self._provider.is_authenticated()
                and not await self._provider.authenticate()
            ):
                self._update_status(
                    "[red]Not authenticated — click provider "
                    "on Overview to log in[/red]"
                )
                return

            all_resources: list[Resource] = []
            types_to_fetch = (
                [resource_type] if resource_type
                else list(self._provider.supported_resource_types)
            )

            region = self._active_region or None

            # Fetch all types in parallel for speed
            import asyncio

            async def _fetch_type(rt: ResourceType) -> list[Resource]:
                try:
                    self._update_status(
                        f"Loading {rt.value}... "
                        f"({types_to_fetch.index(rt) + 1}"
                        f"/{len(types_to_fetch)})"
                    )
                    return await self._provider.list_resources(
                        rt, region=region
                    )
                except Exception as exc:
                    from spancloud.utils.error_formatter import friendly_error, is_permanent_api_error
                    logger.warning(
                        "Failed to list %s from %s: %s",
                        rt.value, self._provider.name, exc,
                    )
                    if is_permanent_api_error(exc):
                        self.app.notify(
                            friendly_error(exc),
                            title=f"GCP API not enabled ({rt.value})",
                            severity="warning",
                            timeout=12,
                        )
                    return []

            results = await asyncio.gather(
                *[_fetch_type(rt) for rt in types_to_fetch]
            )
            for result in results:
                all_resources.extend(result)

            self._resources = sorted(
                all_resources, key=lambda x: (x.resource_type.value, x.name)
            )
            self._filtered = list(self._resources)
            self._populate_table(self._filtered)

            # Build status line
            elapsed = time.monotonic() - start_time
            parts: list[str] = [f"in {elapsed:.1f}s"]
            if hasattr(self._provider, "_auth") and hasattr(
                self._provider._auth, "active_profile"
            ):
                parts.append(
                    f"profile: {self._provider._auth.active_profile}"
                )
            if self._active_region:
                parts.append(f"region: {self._active_region}")
            extra = " | ".join(parts)

            self._update_status(
                f"{len(self._resources):,} resource(s) loaded | {extra} | "
                f"[dim]click row for details | / to search[/dim]"
            )

        except Exception as exc:
            logger.error("Failed to load resources: %s", exc)
            self._update_status(f"[red]Error: {exc}[/red]")
        finally:
            table.loading = False

    def _populate_table(self, resources: list[Resource]) -> None:
        """Fill the table with resource data, with state coloring."""
        table = self.query_one("#resource-table", DataTable)
        table.clear()
        self._resource_map = {}

        for idx, r in enumerate(resources):
            subtype = r.metadata.get("resource_subtype", "")
            info_parts: list[str] = []
            for key in ("machine_type", "engine", "runtime", "tier", "record_type", "plan"):
                val = r.metadata.get(key, "")
                if val:
                    info_parts.append(val)
                    break
            if not info_parts and r.tags:
                tag_str = ", ".join(
                    f"{k}={v}" for k, v in list(r.tags.items())[:2]
                )
                info_parts.append(tag_str)

            # State with color
            style = _STATE_STYLES.get(r.state.value, "")
            state_text = Text(r.state.value, style=style)

            # Use index as tiebreaker to guarantee uniqueness
            row_key = f"{r.provider}:{r.resource_type.value}:{r.id}:{idx}"
            self._resource_map[row_key] = r

            table.add_row(
                r.display_name,
                r.resource_type.value,
                subtype,
                r.region or "—",
                state_text,
                " ".join(info_parts) if info_parts else "—",
                key=row_key,
            )

    def _apply_filter(self, query: str) -> None:
        """Filter the table by search query."""
        if not query:
            self._filtered = list(self._resources)
        else:
            q = query.lower()
            self._filtered = [
                r for r in self._resources
                if q in r.name.lower()
                or q in r.resource_type.value.lower()
                or q in r.region.lower()
                or q in r.metadata.get("resource_subtype", "").lower()
                or q in r.state.value.lower()
                or any(q in v.lower() for v in r.metadata.values())
                or any(q in f"{k}{v}".lower() for k, v in r.tags.items())
            ]

        self._populate_table(self._filtered)
        self._update_status(
            f"{len(self._filtered):,} of {len(self._resources):,} resource(s)"
            + (f" matching '{query}'" if query else "")
            + " | [dim]click row for details | / to search[/dim]"
        )

    def _update_status(self, text: str) -> None:
        """Update the status bar text."""
        self.query_one("#status-bar", Static).update(text)


# ---------------------------------------------------------------------------
# Analysis panel (unchanged from before)
# ---------------------------------------------------------------------------


class AnalysisPanel(VerticalScroll):
    """Panel for displaying analysis results."""

    def __init__(self, provider: BaseProvider) -> None:
        super().__init__()
        self._provider = provider
        self._last_analysis_type: str = ""

    def reload(self) -> None:
        """Re-run the last analysis."""
        if self._last_analysis_type:
            self.run_analysis(self._last_analysis_type)

    def compose(self) -> ComposeResult:
        yield Static(
            "[dim]Select an analysis type from the sidebar.[/dim]",
            id="analysis-content",
        )

    # Braille spinner — same glyph set Textual's LoadingIndicator uses.
    _SPINNER_FRAMES = "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f"

    @work(exclusive=True)
    async def run_analysis(self, analysis_type: str) -> None:
        import time

        self._last_analysis_type = analysis_type
        content = self.query_one("#analysis-content", Static)

        start = time.monotonic()
        spinner_state = {"idx": 0}

        def _tick() -> None:
            elapsed = time.monotonic() - start
            frame = self._SPINNER_FRAMES[
                spinner_state["idx"] % len(self._SPINNER_FRAMES)
            ]
            spinner_state["idx"] += 1
            # Nudge the user after ~10s that slow providers (Vultr, large Azure
            # subscriptions) can legitimately take a while.
            hint = (
                "  [dim italic]slow providers may take a bit...[/dim italic]"
                if elapsed > 10
                else ""
            )
            content.update(
                f"[bold cyan]{frame} Running {analysis_type}...[/bold cyan]  "
                f"[dim]({elapsed:.0f}s)[/dim]{hint}"
            )

        _tick()  # render the first frame immediately
        ticker = self.set_interval(0.1, _tick)

        try:
            if not await self._provider.is_authenticated():
                await self._provider.authenticate()
            result_text = await self._fetch_analysis(analysis_type)
        except Exception as exc:
            result_text = f"[red]Error: {exc}[/red]"
            logger.error("Analysis failed: %s", exc)
        finally:
            ticker.stop()

        content.update(result_text)

    async def _fetch_analysis(self, analysis_type: str) -> str:
        name = self._provider.name
        if not hasattr(self._provider, "_auth") and analysis_type != "metrics":
            return _mock_analysis_tui(name, analysis_type)
        if analysis_type == "cost":
            return await self._run_cost(name)
        elif analysis_type == "audit":
            return await self._run_audit(name)
        elif analysis_type == "unused":
            return await self._run_unused(name)
        elif analysis_type == "relationships":
            return await self._run_relationships(name)
        elif analysis_type == "alerts":
            return await self._run_alerts(name)
        elif analysis_type == "metrics":
            return await self._run_metrics(name)
        return f"[yellow]Unknown analysis: {analysis_type}[/yellow]"

    async def _run_cost(self, provider_name: str) -> str:
        if provider_name == "aws":
            from spancloud.providers.aws.cost import AWSCostAnalyzer
            analyzer = AWSCostAnalyzer(self._provider._auth)
        elif provider_name == "gcp":
            from spancloud.providers.gcp.cost import GCPCostAnalyzer
            analyzer = GCPCostAnalyzer(self._provider._auth)
        elif provider_name == "vultr":
            from spancloud.providers.vultr.cost import VultrCostAnalyzer
            analyzer = VultrCostAnalyzer(self._provider._auth)
        elif provider_name == "digitalocean":
            from spancloud.providers.digitalocean.cost import (
                DigitalOceanCostAnalyzer,
            )
            analyzer = DigitalOceanCostAnalyzer(self._provider._auth)
        elif provider_name == "azure":
            from spancloud.providers.azure.cost import AzureCostAnalyzer
            analyzer = AzureCostAnalyzer(self._provider._auth)
        elif provider_name == "oci":
            from spancloud.providers.oci.cost import OCICostAnalyzer
            analyzer = OCICostAnalyzer(self._provider._auth)
        elif provider_name == "alibaba":
            from spancloud.providers.alibaba.cost import AlibabaCostAnalyzer
            analyzer = AlibabaCostAnalyzer(self._provider._auth)
        else:
            return f"[yellow]Cost not available for {provider_name}[/yellow]"

        summary = await analyzer.get_cost_summary()
        profile_str = ""
        if hasattr(self._provider, "_auth") and hasattr(
            self._provider._auth, "active_profile"
        ):
            profile_str = f"  Profile: {self._provider._auth.active_profile}"

        lines = [
            f"[bold]Cost Summary[/bold]  ({summary.period_start} to {summary.period_end})",
            f"Account: {summary.account_id}{profile_str}",
            f"\n[bold green]Total: ${summary.total_cost:,.2f} {summary.currency}[/bold green]\n",
        ]
        if summary.notes:
            lines.append(f"[yellow]{summary.notes}[/yellow]\n")
        if summary.by_service:
            lines.append("[bold]By Service:[/bold]")
            for svc in summary.by_service[:15]:
                pct = (
                    f"{(svc.cost / summary.total_cost * 100):.1f}%"
                    if summary.total_cost > 0 else "—"
                )
                lines.append(f"  ${svc.cost:>12,.2f}  {pct:>6}  {svc.service}")
        if summary.daily_costs:
            recent = summary.daily_costs[-7:]
            max_cost = max(d.cost for d in recent) if recent else 1
            bar_width = 25

            lines.append("\n[bold]Daily Trend (last 7 days):[/bold]")
            for day in recent:
                bar_len = (
                    int(float(day.cost / max_cost) * bar_width)
                    if max_cost > 0 else 0
                )
                bar = "[green]" + "\u2588" * bar_len + "[/green]"
                lines.append(f"  {day.date}  ${day.cost:>10,.2f}  {bar}")

            # Sparkline
            spark_chars = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
            vals = [float(d.cost) for d in recent]
            vmin, vmax = min(vals), max(vals)
            spread = vmax - vmin if vmax != vmin else 1
            spark = "".join(
                spark_chars[min(int((v - vmin) / spread * 7), 7)]
                for v in vals
            )
            lines.append(f"\n  [cyan]{spark}[/cyan]  [dim]7-day trend[/dim]")

        return "\n".join(lines)

    async def _run_audit(self, provider_name: str) -> str:
        if provider_name == "aws":
            from spancloud.providers.aws.security import AWSSecurityAuditor
            auditor = AWSSecurityAuditor(self._provider._auth)
        elif provider_name == "gcp":
            from spancloud.providers.gcp.security import GCPSecurityAuditor
            auditor = GCPSecurityAuditor(self._provider._auth)
        elif provider_name == "vultr":
            from spancloud.providers.vultr.security import VultrSecurityAuditor
            auditor = VultrSecurityAuditor(self._provider._auth)
        elif provider_name == "digitalocean":
            from spancloud.providers.digitalocean.security import (
                DigitalOceanSecurityAuditor,
            )
            auditor = DigitalOceanSecurityAuditor(self._provider._auth)
        elif provider_name == "azure":
            from spancloud.providers.azure.security import AzureSecurityAuditor
            auditor = AzureSecurityAuditor(self._provider._auth)
        elif provider_name == "oci":
            from spancloud.providers.oci.security import OCISecurityAuditor
            auditor = OCISecurityAuditor(self._provider._auth)
        elif provider_name == "alibaba":
            from spancloud.providers.alibaba.security import (
                AlibabaSecurityAuditor,
            )
            auditor = AlibabaSecurityAuditor(self._provider._auth)
        else:
            return f"[yellow]Audit not available for {provider_name}[/yellow]"

        result = await auditor.run_audit()
        if not result.findings:
            return "[bold green]No security issues found![/bold green]"

        severity_colors = {
            "critical": "bold red", "high": "red", "medium": "yellow",
            "low": "dim yellow", "info": "dim",
        }
        lines = [f"[bold]Security Audit[/bold]  —  {result.summary}\n"]
        for f in sorted(result.findings, key=lambda x: x.severity.value):
            color = severity_colors.get(f.severity.value, "white")
            lines.append(
                f"[{color}]{f.severity.value.upper():>8}[/{color}]  "
                f"{f.resource_type}/{f.resource_id}"
            )
            lines.append(f"           {f.title}")
            lines.append(f"           [dim]{f.recommendation}[/dim]\n")
        return "\n".join(lines)

    async def _run_unused(self, provider_name: str) -> str:
        if provider_name == "aws":
            from spancloud.providers.aws.unused import AWSUnusedDetector
            detector = AWSUnusedDetector(self._provider._auth)
        elif provider_name == "gcp":
            from spancloud.providers.gcp.unused import GCPUnusedDetector
            detector = GCPUnusedDetector(self._provider._auth)
        elif provider_name == "vultr":
            from spancloud.providers.vultr.unused import VultrUnusedDetector
            detector = VultrUnusedDetector(self._provider._auth)
        elif provider_name == "digitalocean":
            from spancloud.providers.digitalocean.unused import (
                DigitalOceanUnusedDetector,
            )
            detector = DigitalOceanUnusedDetector(self._provider._auth)
        elif provider_name == "azure":
            from spancloud.providers.azure.unused import AzureUnusedDetector
            detector = AzureUnusedDetector(self._provider._auth)
        elif provider_name == "oci":
            from spancloud.providers.oci.unused import OCIUnusedDetector
            detector = OCIUnusedDetector(self._provider._auth)
        elif provider_name == "alibaba":
            from spancloud.providers.alibaba.unused import (
                AlibabaUnusedDetector,
            )
            detector = AlibabaUnusedDetector(self._provider._auth)
        else:
            return f"[yellow]Unused detection not available for {provider_name}[/yellow]"

        report = await detector.scan()
        if not report.resources:
            return "[bold green]No unused resources found![/bold green]"

        total_savings = report.total_estimated_monthly_savings
        unestimated = report.unestimated_count
        lines = [
            f"[bold]Unused Resources[/bold]  —  {report.total_count:,} item(s)",
        ]
        if total_savings > 0:
            banner = (
                f"[bold green]Potential monthly savings: "
                f"${total_savings:,.2f}/mo[/bold green]"
            )
            if unestimated:
                banner += (
                    f"  [dim]({unestimated:,} without a $ estimate — "
                    "actual savings may be higher)[/dim]"
                )
            lines.append(banner)
        elif unestimated:
            lines.append(
                f"[dim]{unestimated:,} item(s) flagged without a $ estimate."
                "[/dim]"
            )
        lines.append("")

        for r in report.resources:
            lines.append(f"  [bold]{r.resource_type}[/bold]  {r.resource_name}")
            lines.append(f"    {r.reason}")
            if r.estimated_monthly_savings:
                lines.append(f"    [green]Savings: {r.estimated_monthly_savings}[/green]")
            lines.append("")
        return "\n".join(lines)

    async def _run_relationships(self, provider_name: str) -> str:
        if provider_name == "aws":
            from spancloud.providers.aws.relationships import AWSRelationshipMapper
            mapper = AWSRelationshipMapper(self._provider._auth)
        elif provider_name == "gcp":
            from spancloud.providers.gcp.relationships import GCPRelationshipMapper
            mapper = GCPRelationshipMapper(self._provider._auth)
        elif provider_name == "vultr":
            from spancloud.providers.vultr.relationships import VultrRelationshipMapper
            mapper = VultrRelationshipMapper(self._provider._auth)
        elif provider_name == "digitalocean":
            from spancloud.providers.digitalocean.relationships import (
                DigitalOceanRelationshipMapper,
            )
            mapper = DigitalOceanRelationshipMapper(self._provider._auth)
        elif provider_name == "azure":
            from spancloud.providers.azure.relationships import (
                AzureRelationshipMapper,
            )
            mapper = AzureRelationshipMapper(self._provider._auth)
        elif provider_name == "oci":
            from spancloud.providers.oci.relationships import (
                OCIRelationshipMapper,
            )
            mapper = OCIRelationshipMapper(self._provider._auth)
        elif provider_name == "alibaba":
            from spancloud.providers.alibaba.relationships import (
                AlibabaRelationshipMapper,
            )
            mapper = AlibabaRelationshipMapper(self._provider._auth)
        else:
            return f"[yellow]Relationships not available for {provider_name}[/yellow]"

        rel_map = await mapper.map_relationships()
        if not rel_map.relationships:
            return "[yellow]No relationships found.[/yellow]"

        by_source: dict[str, list] = {}
        for r in rel_map.relationships:
            key = f"{r.source_type}/{r.source_name or r.source_id}"
            by_source.setdefault(key, []).append(r)

        lines = [
            f"[bold]Resource Relationships[/bold]  —  "
            f"{len(rel_map.relationships):,} connection(s)\n",
        ]
        for source, rels in sorted(by_source.items()):
            lines.append(f"  [bold]{source}[/bold]")
            for r in rels:
                target = r.target_name or r.target_id
                lines.append(
                    f"    [cyan]{r.relationship.value}[/cyan] → "
                    f"{target} ({r.target_type})"
                )
            lines.append("")
        return "\n".join(lines)

    async def _run_alerts(self, provider_name: str) -> str:
        if provider_name == "aws":
            from spancloud.providers.aws.cloudwatch import CloudWatchAnalyzer

            analyzer = CloudWatchAnalyzer(self._provider._auth)
            alarms = await analyzer.list_alarms()

            if not alarms:
                return "[green]No CloudWatch alarms found.[/green]"

            state_colors = {
                "ALARM": "bold red",
                "OK": "green",
                "INSUFFICIENT_DATA": "yellow",
            }
            lines = [f"[bold]CloudWatch Alarms[/bold]  —  {len(alarms):,}\n"]
            for a in alarms:
                color = state_colors.get(a.state, "white")
                resource = ", ".join(
                    f"{k}={v}" for k, v in a.dimensions.items()
                ) or "—"
                lines.append(
                    f"  [{color}]{a.state:>18}[/{color}]  {a.name}"
                )
                if a.metric_name:
                    lines.append(
                        f"                      "
                        f"{a.namespace}/{a.metric_name}  {a.threshold}"
                    )
                lines.append(f"                      [dim]{resource}[/dim]\n")
            return "\n".join(lines)

        elif provider_name in (
            "gcp", "digitalocean", "azure", "oci", "alibaba"
        ):
            if provider_name == "gcp":
                from spancloud.providers.gcp.monitoring import (
                    CloudMonitoringAnalyzer,
                )

                analyzer = CloudMonitoringAnalyzer(self._provider._auth)
                title = "Alert Policies"
            elif provider_name == "digitalocean":
                from spancloud.providers.digitalocean.monitoring import (
                    DigitalOceanMonitoringAnalyzer,
                )

                analyzer = DigitalOceanMonitoringAnalyzer(self._provider._auth)
                title = "DigitalOcean Alert Policies"
            elif provider_name == "azure":
                from spancloud.providers.azure.monitoring import (
                    AzureMonitoringAnalyzer,
                )

                analyzer = AzureMonitoringAnalyzer(self._provider._auth)
                title = "Azure Metric Alerts"
            elif provider_name == "oci":
                from spancloud.providers.oci.monitoring import (
                    OCIMonitoringAnalyzer,
                )

                analyzer = OCIMonitoringAnalyzer(self._provider._auth)
                title = "OCI Monitoring Alarms"
            else:  # alibaba
                from spancloud.providers.alibaba.monitoring import (
                    AlibabaMonitoringAnalyzer,
                )

                analyzer = AlibabaMonitoringAnalyzer(self._provider._auth)
                title = "Alibaba CloudMonitor Alarms"

            alerts = await analyzer.list_alert_policies()

            if not alerts:
                return "[green]No alert policies found.[/green]"

            lines = [f"[bold]{title}[/bold]  —  {len(alerts):,}\n"]
            for a in alerts:
                enabled_color = "green" if a.enabled else "dim"
                lines.append(
                    f"  [{enabled_color}]{'ON' if a.enabled else 'OFF':>3}"
                    f"[/{enabled_color}]  {a.display_name or a.name}"
                )
                lines.append(
                    f"       conditions: {a.conditions_count}  "
                    f"channels: {a.notification_channels}  "
                    f"combiner: {a.combiner or '—'}\n"
                )
            return "\n".join(lines)

        return (
            "[yellow]Monitoring alerts not available for this provider."
            "[/yellow]\n[dim]Vultr has no public alerts API.[/dim]"
        )

    async def _run_metrics(self, provider_name: str) -> str:
        """Fetch and display resource metrics for compute instances."""
        # List compute resources first to get IDs
        try:
            if not await self._provider.is_authenticated():
                return "[red]Not authenticated[/red]"

            resources = await self._provider.list_resources(ResourceType.COMPUTE)
        except Exception as exc:
            return f"[red]Error listing compute resources: {exc}[/red]"

        if not resources:
            return "[yellow]No compute resources found.[/yellow]"

        # Check if provider supports metrics
        if not hasattr(self._provider, "get_instance_metrics"):
            return f"[yellow]Metrics not yet available for {provider_name}.[/yellow]"

        # Fetch metrics for up to 5 instances
        sample = resources[:5]
        lines = [
            f"[bold]Instance Metrics[/bold]  (showing {len(sample)} of {len(resources)} instances)\n"
        ]

        for resource in sample:
            lines.append(
                f"  [bold]{resource.display_name}[/bold]  [dim]{resource.region or '—'}[/dim]"
            )
            try:
                result = await self._provider.get_instance_metrics(
                    resource.id, region=resource.region, hours=1
                )
                if result and result.metrics:
                    for metric_name, points in result.metrics.items():
                        if not points:
                            continue
                        vals = [p.value for p in points[-12:]]  # last 12 points
                        if not vals:
                            continue
                        latest = vals[-1]
                        avg = sum(vals) / len(vals)
                        # Sparkline
                        spark_chars = "▁▂▃▄▅▆▇█"
                        vmin, vmax = min(vals), max(vals)
                        spread = vmax - vmin if vmax != vmin else 1
                        spark = "".join(
                            spark_chars[min(int((v - vmin) / spread * 7), 7)]
                            for v in vals
                        )
                        lines.append(
                            f"    [cyan]{metric_name:>20}[/cyan]  "
                            f"latest: {latest:>7.2f}  avg: {avg:>7.2f}  [dim]{spark}[/dim]"
                        )
                else:
                    lines.append("    [dim]No metrics available[/dim]")
            except Exception as exc:
                lines.append(f"    [red]Error: {exc}[/red]")
            lines.append("")

        if len(resources) > 5:
            lines.append(
                "[dim]  Use CLI for all instances: spancloud monitor metrics <id>[/dim]"
            )

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main provider tab
# ---------------------------------------------------------------------------


class ProviderTab(Horizontal):
    """Provider tab: sidebar + content area (table/search/detail) + analysis."""

    def __init__(self, provider: BaseProvider) -> None:
        super().__init__()
        self._provider = provider

    def compose(self) -> ComposeResult:
        yield ResourceTypeSidebar(self._provider)
        yield ResourceContentArea(self._provider)
        yield AnalysisPanel(self._provider)

    def on_mount(self) -> None:
        self.query_one(AnalysisPanel).display = False

    def on_resource_type_selected(self, event: ResourceTypeSelected) -> None:
        self.query_one(ResourceContentArea).display = True
        self.query_one(AnalysisPanel).display = False
        content = self.query_one(ResourceContentArea)
        content.load_resources(event.resource_type)

    def on_extended_scan_selected(self, event: ExtendedScanSelected) -> None:
        self.query_one(ResourceContentArea).display = True
        self.query_one(AnalysisPanel).display = False
        content = self.query_one(ResourceContentArea)
        content.load_extended()

    def on_analysis_selected(self, event: AnalysisSelected) -> None:
        self.query_one(ResourceContentArea).display = False
        self.query_one(AnalysisPanel).display = True
        panel = self.query_one(AnalysisPanel)
        panel.run_analysis(event.analysis_type)

    def _reload_active_pane(self) -> None:
        """Reload whichever pane (resources or analysis) is currently visible."""
        content = self.query_one(ResourceContentArea)
        analysis = self.query_one(AnalysisPanel)
        if content.display:
            content.reload()
        elif analysis.display:
            analysis.reload()

    def on_profile_changed(self, event: ProfileChanged) -> None:
        auth = getattr(event.provider, "_auth", None)
        if not hasattr(auth, "set_profile"):
            return
        auth.set_profile(event.profile_name)
        self.app.notify(f"Switched to profile: {event.profile_name}", timeout=2)
        self.run_worker(
            self._verify_after_profile_switch(event.profile_name),
            name=f"profile-switch-{event.provider.name}",
        )

    async def _verify_after_profile_switch(self, profile_name: str) -> None:
        """Verify credentials for the newly selected profile and react accordingly.

        - Success (any type): update sidebar status, persist the choice, reload.
        - Failure + SSO profile: show the auth modal so the user can run sso login.
        - Failure + access key profile: show a helpful error notification.
        """
        import os

        from spancloud.config import get_settings
        from spancloud.providers.aws.auth import AWSAuth

        sidebar = self.query_one(ResourceTypeSidebar)
        status = sidebar.query_one(f"#auth-{self._provider.name}", Static)
        status.update("[cyan]verifying...[/cyan]")

        success = await self._provider.authenticate()

        if success:
            active = getattr(
                getattr(self._provider, "_auth", None), "active_profile", profile_name
            )
            status.update(f"[green]authenticated[/green] ({active})")
            # Persist so the next startup reopens with this profile
            env_path = get_settings().ensure_config_dir() / "aws.env"
            env_path.write_text(f"SPANCLOUD_AWS_PROFILE={profile_name}\n")
            os.environ["SPANCLOUD_AWS_PROFILE"] = profile_name
            self._reload_active_pane()
            return

        # Auth failed — look up the profile type to decide how to respond
        profiles = AWSAuth.list_configured_profiles()
        profile_info = next((p for p in profiles if p["name"] == profile_name), {})

        if profile_info.get("type") == "sso":
            status.update("[yellow]SSO login required[/yellow]")
            self.app.notify(
                f"Profile '{profile_name}' needs SSO login — opening auth dialog",
                timeout=4,
            )

            from spancloud.tui.screens.auth import AuthScreen

            def _after_auth(ok: bool | None) -> None:
                if ok:
                    status.update(f"[green]authenticated[/green] ({profile_name})")
                    self._reload_active_pane()
                else:
                    status.update("[red]not authenticated[/red]")

            self.app.push_screen(AuthScreen(self._provider), _after_auth)
        else:
            status.update("[red]not authenticated[/red]")
            self.app.notify(
                f"Profile '{profile_name}': credentials are invalid or expired — "
                "run 'aws configure' to update them.",
                severity="error",
                timeout=6,
            )

    def on_project_changed(self, event: ProjectChanged) -> None:
        auth = getattr(event.provider, "_auth", None)
        if auth is None or not hasattr(auth, "set_project"):
            return
        if event.project_id == getattr(auth, "project_id", ""):
            return
        auth.set_project(event.project_id)
        # Update the status label directly — don't re-run _check_auth() as that
        # re-populates the Select, which re-fires Changed, causing a loop.
        try:
            sidebar = self.query_one(ResourceTypeSidebar)
            status = sidebar.query_one(f"#auth-{event.provider.name}", Static)
            status.update(f"[green]authenticated[/green] ({event.project_id})")
        except Exception:
            pass
        self.app.notify(f"Switched to project: {event.project_id}", timeout=3)
        self._reload_active_pane()

    def on_subscription_changed(self, event: SubscriptionChanged) -> None:
        auth = getattr(event.provider, "_auth", None)
        if auth is None or not hasattr(auth, "set_subscription"):
            return
        if event.subscription_id == getattr(auth, "subscription_id", ""):
            return
        auth.set_subscription(event.subscription_id)
        self.app.notify(
            f"Switched to subscription: {event.subscription_id[:8]}…", timeout=3
        )
        self._reload_active_pane()

    def on_region_changed(self, event: RegionChanged) -> None:
        content = self.query_one(ResourceContentArea)
        content._active_region = event.region
        region_label = event.region or "All Regions"
        self.app.notify(f"Region: {region_label}", timeout=2)
        self._reload_active_pane()

    def on_settings_requested(self, event: SettingsRequested) -> None:
        from spancloud.tui.screens.settings import SidebarSettingsScreen

        self.app.push_screen(
            SidebarSettingsScreen(event.provider),
            callback=lambda changed: (
                self.app.notify("Sidebar updated — restart TUI to apply", timeout=5)
                if changed else None
            ),
        )
