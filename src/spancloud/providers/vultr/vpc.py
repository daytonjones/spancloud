"""Vultr VPC and firewall group resource discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.vultr.auth import VultrAuth

logger = get_logger(__name__)


class VPCResources:
    """Handles Vultr VPC discovery — tries VPC 2.0 then falls back to VPC 1.0."""

    def __init__(self, auth: VultrAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_vpcs(self, region: str | None = None) -> list[Resource]:
        """List VPC networks (VPC 2.0 + VPC 1.0 fallback).

        Args:
            region: Optional region filter.

        Returns:
            List of Resource objects representing VPCs.
        """
        resources: list[Resource] = []

        # VPC 2.0
        try:
            raw2 = await self._auth.get_paginated("/vpc2", "vpc2_networks")
            for vpc in raw2:
                if region and vpc.get("region") != region:
                    continue
                resources.append(self._map_vpc2(vpc))
        except Exception as exc:
            logger.debug("VPC 2.0 listing failed: %s", exc)

        # VPC 1.0 — older accounts may only have these
        try:
            raw1 = await self._auth.get_paginated("/vpcs", "vpcs")
            seen = {r.id for r in resources}
            for vpc in raw1:
                if region and vpc.get("region") != region:
                    continue
                r = self._map_vpc1(vpc)
                if r.id not in seen:
                    resources.append(r)
        except Exception as exc:
            logger.debug("VPC 1.0 listing failed: %s", exc)

        logger.debug("Found %d Vultr VPCs", len(resources))
        return resources

    def _map_vpc2(self, vpc: dict[str, Any]) -> Resource:
        """Map a Vultr VPC 2.0 network to a unified Resource."""
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
                "resource_subtype": "vpc2",
            },
        )

    def _map_vpc1(self, vpc: dict[str, Any]) -> Resource:
        """Map a Vultr VPC 1.0 network to a unified Resource."""
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
                "ip_block": vpc.get("v4_subnet", ""),
                "prefix_length": str(vpc.get("v4_subnet_mask", "")),
                "resource_subtype": "vpc1",
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
