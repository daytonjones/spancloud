"""spancloud permissions — show required IAM/access permissions per provider."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

console = Console()

_PERMISSIONS: dict[str, list[tuple[str, str]]] = {
    "aws": [
        ("ReadOnlyAccess (managed policy)", "Full read-only coverage — simplest option"),
        ("AmazonEC2ReadOnlyAccess",         "Compute (EC2), VPC, security groups, load balancers"),
        ("AmazonS3ReadOnlyAccess",          "Storage (S3)"),
        ("AmazonRDSReadOnlyAccess",         "Databases (RDS/Aurora)"),
        ("AWSLambdaReadOnlyAccess",         "Serverless (Lambda)"),
        ("AmazonEKSReadPolicy",             "Containers (EKS)"),
        ("CloudWatchReadOnlyAccess",        "Metrics and CloudWatch alarms"),
        ("AmazonRoute53ReadOnlyAccess",     "DNS (Route 53)"),
        ("IAMReadOnlyAccess",               "IAM users, roles, policies"),
        ("AWSBillingReadOnlyAccess",        "Cost data (Cost Explorer)"),
    ],
    "gcp": [
        ("roles/viewer",                                        "Full read-only coverage — simplest option"),
        ("roles/compute.viewer",                                "Compute Engine (VMs)"),
        ("roles/storage.objectViewer",                          "Cloud Storage"),
        ("roles/cloudsql.viewer",                               "Cloud SQL"),
        ("roles/container.viewer",                              "Google Kubernetes Engine"),
        ("roles/run.viewer",                                    "Cloud Run"),
        ("roles/cloudfunctions.viewer",                         "Cloud Functions"),
        ("roles/dns.reader",                                    "Cloud DNS"),
        ("roles/monitoring.viewer",                             "Cloud Monitoring"),
        ("roles/resourcemanager.projectViewer",                 "Project and org listing"),
        ("roles/billing.viewer",                                "Cloud Billing"),
        ("roles/bigquery.dataViewer + roles/bigquery.jobUser",  "Cost data (BigQuery billing export)"),
    ],
    "azure": [
        ("Reader (subscription scope)",              "All resource discovery — simplest option"),
        ("Cost Management Reader (subscription)",    "Cost and billing data"),
    ],
    "digitalocean": [
        ("Personal Access Token — read scope",  "All resource discovery"),
        ("Billing team role (organisation)",    "Cost and billing data — Member accounts return 403"),
    ],
    "vultr": [
        ("API key — Read: Servers, Bare Metal, Block/Object Storage", "Resource discovery"),
        ("API key — Read: Billing",                                   "Cost data"),
    ],
    "oci": [
        ("read all-resources in tenancy",   "Full read-only coverage — simplest option"),
        ("read instances in tenancy",       "Compute instances"),
        ("read buckets in tenancy",         "Object Storage"),
        ("read volumes in tenancy",         "Block Volumes"),
        ("read autonomous-databases in tenancy", "Autonomous Databases"),
        ("read clusters in tenancy",        "Kubernetes (OKE)"),
        ("read load-balancers in tenancy",  "Load Balancers"),
        ("read dns in tenancy",             "DNS Zones"),
        ("read usage-reports in tenancy",   "Cost data"),
    ],
}

_NOTES: dict[str, str] = {
    "gcp": (
        "Grant roles in GCP Console → IAM & Admin → IAM.\n"
        "Cost data also requires BigQuery billing export to be configured:\n"
        "  GCP Console → Billing → Billing export → BigQuery export → Enable"
    ),
    "azure": (
        "Assign roles in Azure Portal → Subscriptions → [subscription] → "
        "Access control (IAM) → Add role assignment."
    ),
    "oci": (
        "Apply policies in OCI Console → Identity & Security → Policies.\n"
        "Example policy statement:\n"
        "  Allow group SpancloudUsers to read all-resources in tenancy"
    ),
}

_ALL = sorted(_PERMISSIONS.keys())


def show_permissions(
    provider: str | None = typer.Argument(
        None,
        help=f"Provider name ({', '.join(_ALL)}). Omit to show all.",
    ),
) -> None:
    """Show the IAM / API permissions required for each cloud provider."""
    providers = [provider] if provider else _ALL

    for name in providers:
        if name not in _PERMISSIONS:
            console.print(f"[red]Unknown provider:[/red] '{name}'. "
                          f"Choose from: {', '.join(_ALL)}")
            raise typer.Exit(code=1)

        console.print()
        console.rule(f"[bold cyan]{name.upper()}[/bold cyan]")

        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        table.add_column("Permission / Role", style="cyan", no_wrap=False)
        table.add_column("Covers", style="white")

        for role, description in _PERMISSIONS[name]:
            table.add_row(role, description)

        console.print(table)

        if name in _NOTES:
            console.print(f"\n[dim]{_NOTES[name]}[/dim]")

    console.print()
