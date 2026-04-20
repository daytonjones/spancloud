"""GCP VPC network, subnet, and firewall rule resource discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from google.cloud import compute_v1

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.providers.gcp._retry import GCP_RETRY

if TYPE_CHECKING:
    from spancloud.providers.gcp.auth import GCPAuth

logger = get_logger(__name__)


class NetworkResources:
    """Handles GCP VPC network discovery."""

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    @GCP_RETRY
    async def list_networks(self, region: str | None = None) -> list[Resource]:
        """List all VPC networks in the project.

        Args:
            region: Ignored for networks (they are global), but accepted for interface consistency.

        Returns:
            List of Resource objects representing VPC networks.
        """
        project = self._auth.project_id
        if not project:
            logger.warning("No GCP project ID configured — cannot list networks")
            return []

        client = compute_v1.NetworksClient(credentials=self._auth.credentials)

        def _fetch() -> list[Any]:
            return list(client.list(project=project))

        networks = await asyncio.to_thread(_fetch)

        resources: list[Resource] = []
        for network in networks:
            resources.append(self._map_network(network))

        logger.debug("Found %d VPC networks", len(resources))
        return resources

    def _map_network(self, network: Any) -> Resource:
        """Map a GCP VPC network to a unified Resource."""
        labels = {}
        # Networks don't have labels in the API, but peering info is useful
        peerings = network.peerings or []
        subnet_mode = "auto" if network.auto_create_subnetworks else "custom"

        return Resource(
            id=str(network.id),
            name=network.name or str(network.id),
            resource_type=ResourceType.NETWORK,
            provider="gcp",
            region="global",
            state=ResourceState.RUNNING,
            created_at=None,
            tags=labels,
            metadata={
                "subnet_mode": subnet_mode,
                "mtu": str(network.mtu or ""),
                "routing_mode": (
                    network.routing_config.routing_mode if network.routing_config else ""
                ),
                "peering_count": str(len(peerings)),
                "resource_subtype": "vpc",
            },
        )


class SubnetResources:
    """Handles GCP subnet discovery."""

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    @GCP_RETRY
    async def list_subnets(self, region: str | None = None) -> list[Resource]:
        """List all subnets in the project.

        Uses aggregated list to get subnets across all regions, or filters
        by region if specified.

        Args:
            region: Optional region to filter by (e.g., 'us-central1').

        Returns:
            List of Resource objects representing subnets.
        """
        project = self._auth.project_id
        if not project:
            logger.warning("No GCP project ID configured — cannot list subnets")
            return []

        client = compute_v1.SubnetworksClient(credentials=self._auth.credentials)

        def _fetch() -> list[dict[str, Any]]:
            subnets: list[dict[str, Any]] = []
            request = compute_v1.AggregatedListSubnetworksRequest(project=project)
            for region_key, scoped_list in client.aggregated_list(request=request):
                if scoped_list.subnetworks:
                    for subnet in scoped_list.subnetworks:
                        region_name = region_key.split("/")[-1] if "/" in region_key else region_key
                        if region and region != region_name:
                            continue
                        subnets.append({"subnet": subnet, "region": region_name})
            return subnets

        raw_subnets = await asyncio.to_thread(_fetch)

        resources: list[Resource] = []
        for item in raw_subnets:
            resources.append(self._map_subnet(item["subnet"], item["region"]))

        logger.debug("Found %d subnets", len(resources))
        return resources

    def _map_subnet(self, subnet: Any, region: str) -> Resource:
        """Map a GCP subnet to a unified Resource."""
        # Extract network name from full URL
        network_name = (subnet.network or "").rsplit("/", 1)[-1]

        return Resource(
            id=str(subnet.id),
            name=subnet.name or str(subnet.id),
            resource_type=ResourceType.NETWORK,
            provider="gcp",
            region=region,
            state=ResourceState.RUNNING,
            created_at=None,
            tags={},
            metadata={
                "network": network_name,
                "ip_cidr_range": subnet.ip_cidr_range or "",
                "purpose": subnet.purpose or "",
                "private_ip_google_access": str(getattr(subnet, "private_ip_google_access", False)),
                "stack_type": subnet.stack_type or "",
                "resource_subtype": "subnet",
            },
        )


class FirewallResources:
    """Handles GCP firewall rule discovery."""

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    @GCP_RETRY
    async def list_firewalls(self, region: str | None = None) -> list[Resource]:
        """List all firewall rules in the project.

        Args:
            region: Ignored for firewalls (they are global), but accepted for interface consistency.

        Returns:
            List of Resource objects representing firewall rules.
        """
        project = self._auth.project_id
        if not project:
            logger.warning("No GCP project ID configured — cannot list firewalls")
            return []

        client = compute_v1.FirewallsClient(credentials=self._auth.credentials)

        def _fetch() -> list[Any]:
            return list(client.list(project=project))

        firewalls = await asyncio.to_thread(_fetch)

        resources: list[Resource] = []
        for fw in firewalls:
            resources.append(self._map_firewall(fw))

        logger.debug("Found %d firewall rules", len(resources))
        return resources

    def _map_firewall(self, fw: Any) -> Resource:
        """Map a GCP firewall rule to a unified Resource."""
        network_name = (fw.network or "").rsplit("/", 1)[-1]

        # Summarize allowed/denied rules
        allowed = fw.allowed or []
        denied = fw.denied or []
        direction = fw.direction or "INGRESS"

        # Count source/target ranges
        source_ranges = list(fw.source_ranges) if fw.source_ranges else []
        target_tags = list(fw.target_tags) if fw.target_tags else []

        state = ResourceState.RUNNING if not fw.disabled else ResourceState.STOPPED

        return Resource(
            id=str(fw.id),
            name=fw.name or str(fw.id),
            resource_type=ResourceType.NETWORK,
            provider="gcp",
            region="global",
            state=state,
            created_at=None,
            tags={},
            metadata={
                "network": network_name,
                "direction": direction,
                "priority": str(fw.priority or ""),
                "action": "allow" if allowed else "deny" if denied else "unknown",
                "allowed_rules": str(len(allowed)),
                "denied_rules": str(len(denied)),
                "source_ranges": ", ".join(source_ranges[:5]),
                "target_tags": ", ".join(target_tags[:5]),
                "disabled": str(fw.disabled or False),
                "resource_subtype": "firewall",
            },
        )
