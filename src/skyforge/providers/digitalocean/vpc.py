"""DigitalOcean VPC and firewall resource discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.digitalocean.auth import DigitalOceanAuth

logger = get_logger(__name__)


class VPCResources:
    """Handles DO VPC discovery."""

    def __init__(self, auth: DigitalOceanAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_vpcs(self, region: str | None = None) -> list[Resource]:
        """List all VPCs."""
        raw = await self._auth.get_paginated("/vpcs", "vpcs")

        resources: list[Resource] = []
        for vpc in raw:
            vpc_region = vpc.get("region", "")
            if region and vpc_region != region:
                continue
            resources.append(self._map_vpc(vpc))

        logger.debug("Found %d DO VPCs", len(resources))
        return resources

    def _map_vpc(self, vpc: dict[str, Any]) -> Resource:
        return Resource(
            id=vpc.get("id", ""),
            name=vpc.get("name", "") or vpc.get("id", ""),
            resource_type=ResourceType.NETWORK,
            provider="digitalocean",
            region=vpc.get("region", ""),
            state=ResourceState.RUNNING,
            created_at=vpc.get("created_at"),
            metadata={
                "description": vpc.get("description", ""),
                "ip_range": vpc.get("ip_range", ""),
                "default": str(vpc.get("default", False)),
                "resource_subtype": "vpc",
            },
        )


class FirewallResources:
    """Handles DO firewall (cloud firewall) discovery."""

    def __init__(self, auth: DigitalOceanAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_firewalls(self, region: str | None = None) -> list[Resource]:
        """List all cloud firewalls."""
        raw = await self._auth.get_paginated("/firewalls", "firewalls")

        resources: list[Resource] = []
        for fw in raw:
            resources.append(self._map_firewall(fw))

        logger.debug("Found %d DO firewalls", len(resources))
        return resources

    def _map_firewall(self, fw: dict[str, Any]) -> Resource:
        inbound = fw.get("inbound_rules") or []
        outbound = fw.get("outbound_rules") or []
        droplet_ids = fw.get("droplet_ids") or []

        return Resource(
            id=fw.get("id", ""),
            name=fw.get("name", "") or fw.get("id", ""),
            resource_type=ResourceType.NETWORK,
            provider="digitalocean",
            region="global",
            state=ResourceState.RUNNING,
            created_at=fw.get("created_at"),
            metadata={
                "status": fw.get("status", ""),
                "inbound_rules": str(len(inbound)),
                "outbound_rules": str(len(outbound)),
                "droplet_count": str(len(droplet_ids)),
                "resource_subtype": "firewall",
            },
        )
