"""Vultr VPC and firewall group resource discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.vultr.auth import VultrAuth

logger = get_logger(__name__)


class VPCResources:
    """Handles Vultr VPC 2.0 discovery."""

    def __init__(self, auth: VultrAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_vpcs(self, region: str | None = None) -> list[Resource]:
        """List all VPC 2.0 networks.

        Args:
            region: Optional region filter.

        Returns:
            List of Resource objects representing VPCs.
        """
        raw = await self._auth.get_paginated("/vpcs2", "vpcs")

        resources: list[Resource] = []
        for vpc in raw:
            vpc_region = vpc.get("region", "")
            if region and vpc_region != region:
                continue
            resources.append(self._map_vpc(vpc))

        logger.debug("Found %d Vultr VPCs", len(resources))
        return resources

    def _map_vpc(self, vpc: dict[str, Any]) -> Resource:
        """Map a Vultr VPC to a unified Resource."""
        return Resource(
            id=vpc.get("id", ""),
            name=vpc.get("description", "") or vpc.get("id", ""),
            resource_type=ResourceType.NETWORK,
            provider="vultr",
            region=vpc.get("region", ""),
            state=ResourceState.RUNNING,
            created_at=vpc.get("date_created"),
            tags={},
            metadata={
                "ip_block": vpc.get("ip_block", ""),
                "prefix_length": str(vpc.get("prefix_length", "")),
                "resource_subtype": "vpc",
            },
        )


class FirewallResources:
    """Handles Vultr firewall group discovery."""

    def __init__(self, auth: VultrAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_firewall_groups(
        self, region: str | None = None
    ) -> list[Resource]:
        """List all firewall groups.

        Args:
            region: Ignored (firewall groups are global), accepted for interface consistency.

        Returns:
            List of Resource objects representing firewall groups.
        """
        raw = await self._auth.get_paginated("/firewalls", "firewall_groups")

        resources: list[Resource] = []
        for fw in raw:
            resources.append(self._map_firewall(fw))

        logger.debug("Found %d Vultr firewall groups", len(resources))
        return resources

    def _map_firewall(self, fw: dict[str, Any]) -> Resource:
        """Map a Vultr firewall group to a unified Resource."""
        return Resource(
            id=fw.get("id", ""),
            name=fw.get("description", "") or fw.get("id", ""),
            resource_type=ResourceType.NETWORK,
            provider="vultr",
            region="global",
            state=ResourceState.RUNNING,
            created_at=fw.get("date_created"),
            tags={},
            metadata={
                "rule_count": str(fw.get("rule_count", 0)),
                "instance_count": str(fw.get("instance_count", 0)),
                "max_rule_count": str(fw.get("max_rule_count", "")),
                "resource_subtype": "firewall_group",
            },
        )
