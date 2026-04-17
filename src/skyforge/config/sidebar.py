"""Sidebar configuration — user-selectable resource types per provider.

Manages which resource subtypes appear in the TUI sidebar (max ~10).
Config stored at ~/.config/skyforge/sidebar.yaml.
"""

from __future__ import annotations

import json
from pathlib import Path  # noqa: TC003 — used at runtime
from typing import Any

from skyforge.config import get_settings
from skyforge.utils.logging import get_logger

logger = get_logger(__name__)

_CONFIG_FILE = "sidebar.json"

# Default sidebar items per provider (the original set)
_DEFAULTS: dict[str, list[dict[str, str]]] = {
    "aws": [
        {"name": "ec2", "label": "\U0001f5a5  EC2 Instances", "type": "compute"},
        {"name": "s3", "label": "\U0001f4e6 S3 Buckets", "type": "storage"},
        {"name": "vpc", "label": "\U0001f310 VPC/Network", "type": "network"},
        {"name": "rds", "label": "\U0001f4be RDS Databases", "type": "database"},
        {"name": "lambda", "label": "\u26a1 Lambda", "type": "serverless"},
        {"name": "elb", "label": "\u2696  Load Balancers", "type": "load_balancer"},
        {"name": "eks", "label": "\U0001f4e6 EKS/Containers", "type": "container"},
        {"name": "route53", "label": "\U0001f310 Route53 DNS", "type": "dns"},
        {"name": "iam", "label": "\U0001f512 IAM", "type": "iam"},
    ],
    "gcp": [
        {"name": "gce", "label": "\U0001f5a5  GCE Instances", "type": "compute"},
        {"name": "gcs", "label": "\U0001f4e6 GCS Buckets", "type": "storage"},
        {"name": "vpc", "label": "\U0001f310 VPC/Network", "type": "network"},
        {"name": "cloudsql", "label": "\U0001f4be Cloud SQL", "type": "database"},
        {"name": "functions", "label": "\u26a1 Cloud Functions", "type": "serverless"},
        {"name": "cloudrun", "label": "\u26a1 Cloud Run", "type": "serverless"},
        {"name": "gke", "label": "\U0001f4e6 GKE/Containers", "type": "container"},
        {"name": "lb", "label": "\u2696  Load Balancers", "type": "load_balancer"},
        {"name": "dns", "label": "\U0001f310 Cloud DNS", "type": "dns"},
    ],
    "vultr": [
        {"name": "instances", "label": "\U0001f5a5  Instances", "type": "compute"},
        {"name": "block_storage", "label": "\U0001f4e6 Block Storage", "type": "storage"},
        {"name": "vpc", "label": "\U0001f310 VPCs", "type": "network"},
        {"name": "database", "label": "\U0001f4be Databases", "type": "database"},
        {"name": "kubernetes", "label": "\U0001f4e6 Kubernetes", "type": "container"},
        {"name": "lb", "label": "\u2696  Load Balancers", "type": "load_balancer"},
        {"name": "dns", "label": "\U0001f310 DNS", "type": "dns"},
    ],
    "digitalocean": [
        {"name": "droplets", "label": "\U0001f5a5  Droplets", "type": "compute"},
        {"name": "volumes", "label": "\U0001f4bf Volumes", "type": "storage"},
        {"name": "vpc", "label": "\U0001f310 VPCs", "type": "network"},
        {"name": "database", "label": "\U0001f4be Databases", "type": "database"},
        {"name": "doks", "label": "\U0001f4e6 Kubernetes (DOKS)", "type": "container"},
        {"name": "lb", "label": "\u2696  Load Balancers", "type": "load_balancer"},
        {"name": "dns", "label": "\U0001f310 DNS", "type": "dns"},
    ],
    "azure": [
        {"name": "vms", "label": "\U0001f5a5  Virtual Machines", "type": "compute"},
        {"name": "storage", "label": "\U0001f4e6 Storage Accounts", "type": "storage"},
        {"name": "vnet", "label": "\U0001f310 VNets/NSGs", "type": "network"},
        {"name": "sql", "label": "\U0001f4be SQL + Cosmos", "type": "database"},
        {"name": "appservice", "label": "\u26a1 App Service/Functions", "type": "serverless"},
        {"name": "aks", "label": "\U0001f4e6 AKS", "type": "container"},
        {"name": "lb", "label": "\u2696  Load Balancers", "type": "load_balancer"},
        {"name": "dns", "label": "\U0001f310 Azure DNS", "type": "dns"},
    ],
    "oci": [
        {"name": "instances", "label": "\U0001f5a5  Instances", "type": "compute"},
        {"name": "object_storage", "label": "\U0001f4e6 Object Storage", "type": "storage"},
        {"name": "vcn", "label": "\U0001f310 VCN/Subnets/SLs", "type": "network"},
        {"name": "adb", "label": "\U0001f4be Autonomous DB + DB Systems", "type": "database"},
        {"name": "oke", "label": "\U0001f4e6 OKE", "type": "container"},
        {"name": "lb", "label": "\u2696  Load Balancers", "type": "load_balancer"},
        {"name": "dns", "label": "\U0001f310 DNS Zones", "type": "dns"},
    ],
    "alibaba": [
        {"name": "ecs", "label": "\U0001f5a5  ECS Instances", "type": "compute"},
        {"name": "oss", "label": "\U0001f4e6 OSS + Disks", "type": "storage"},
        {"name": "vpc", "label": "\U0001f310 VPCs/VSwitches/SGs", "type": "network"},
        {"name": "rds", "label": "\U0001f4be RDS", "type": "database"},
        {"name": "ack", "label": "\U0001f4e6 ACK (Kubernetes)", "type": "container"},
        {"name": "slb", "label": "\u2696  SLB / CLB", "type": "load_balancer"},
        {"name": "alidns", "label": "\U0001f310 Alidns", "type": "dns"},
    ],
}

# Extended services available for AWS (from services.py registry)
_AWS_EXTENDED: list[dict[str, str]] = [
    {"name": "ebs_volumes", "label": "\U0001f4bf EBS Volumes", "type": "compute"},
    {"name": "elastic_ips", "label": "\U0001f310 Elastic IPs", "type": "network"},
    {"name": "auto_scaling_groups", "label": "\u2194 Auto Scaling", "type": "compute"},
    {"name": "amis", "label": "\U0001f4e6 AMIs", "type": "compute"},
    {"name": "efs", "label": "\U0001f4c1 EFS", "type": "storage"},
    {"name": "dynamodb", "label": "\U0001f4ca DynamoDB", "type": "database"},
    {"name": "elasticache", "label": "\u26a1 ElastiCache", "type": "database"},
    {"name": "nat_gateways", "label": "\U0001f6aa NAT Gateways", "type": "network"},
    {"name": "cloudfront", "label": "\U0001f310 CloudFront", "type": "network"},
    {"name": "sqs", "label": "\U0001f4e8 SQS Queues", "type": "other"},
    {"name": "sns", "label": "\U0001f514 SNS Topics", "type": "other"},
    {"name": "secrets_manager", "label": "\U0001f512 Secrets Manager", "type": "other"},
    {"name": "ssm_parameters", "label": "\u2699 SSM Parameters", "type": "other"},
    {"name": "ecr", "label": "\U0001f4e6 ECR Repos", "type": "container"},
    {"name": "ecs_clusters", "label": "\U0001f4e6 ECS Clusters", "type": "container"},
    {"name": "api_gateway", "label": "\U0001f517 API Gateway", "type": "serverless"},
    {"name": "step_functions", "label": "\u2699 Step Functions", "type": "serverless"},
]


def _config_path() -> Path:
    """Get the sidebar config file path."""
    return get_settings().ensure_config_dir() / _CONFIG_FILE


def get_sidebar_items(provider: str) -> list[dict[str, str]]:
    """Get the sidebar items for a provider.

    Returns the user's configured items, or defaults if no config exists.

    Args:
        provider: Provider name.

    Returns:
        List of sidebar item dicts with name, label, type.
    """
    config = _load_config()
    return config.get(provider, _DEFAULTS.get(provider, []))


def get_available_services(provider: str) -> list[dict[str, str]]:
    """Get ALL available services for a provider (for the config UI).

    Args:
        provider: Provider name.

    Returns:
        Combined list of default + extended services.
    """
    defaults = _DEFAULTS.get(provider, [])
    if provider == "aws":
        # Merge defaults + extended, dedup by name
        seen = {d["name"] for d in defaults}
        extended = [s for s in _AWS_EXTENDED if s["name"] not in seen]
        return defaults + extended
    return defaults


def set_sidebar_items(provider: str, items: list[dict[str, str]]) -> None:
    """Save sidebar items for a provider.

    Args:
        provider: Provider name.
        items: List of sidebar item dicts.
    """
    config = _load_config()
    config[provider] = items
    _save_config(config)


def reset_sidebar(provider: str | None = None) -> None:
    """Reset sidebar to defaults.

    Args:
        provider: Provider to reset, or None for all.
    """
    if provider:
        config = _load_config()
        config.pop(provider, None)
        _save_config(config)
    else:
        path = _config_path()
        if path.exists():
            path.unlink()


# ---------------------------------------------------------------------------
# Provider enable/disable
# ---------------------------------------------------------------------------

# Default: implemented providers enabled, stubs disabled
_DEFAULT_ENABLED = {
    "aws", "gcp", "vultr", "digitalocean", "azure", "oci", "alibaba",
}


def get_enabled_providers() -> set[str]:
    """Get the set of enabled provider names.

    Returns:
        Set of provider name strings that should show as tabs.
    """
    config = _load_config()
    enabled = config.get("_enabled_providers")
    if enabled is not None:
        return set(enabled)
    return set(_DEFAULT_ENABLED)


def set_enabled_providers(providers: set[str]) -> None:
    """Save which providers are enabled.

    Args:
        providers: Set of provider names to enable.
    """
    config = _load_config()
    config["_enabled_providers"] = sorted(providers)
    _save_config(config)


def is_provider_enabled(provider_name: str) -> bool:
    """Check if a specific provider is enabled.

    Args:
        provider_name: Provider name to check.

    Returns:
        True if the provider should show as a tab.
    """
    return provider_name in get_enabled_providers()


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------


def _load_config() -> dict[str, Any]:
    """Load sidebar config from disk."""
    path = _config_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not load sidebar config: %s", exc)
    return {}


def _save_config(config: dict[str, Any]) -> None:
    """Save sidebar config to disk."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2))
