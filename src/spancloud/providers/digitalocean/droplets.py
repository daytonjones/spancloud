"""DigitalOcean Droplet (compute) resource discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.digitalocean.auth import DigitalOceanAuth

logger = get_logger(__name__)

_DROPLET_STATE_MAP: dict[str, ResourceState] = {
    "active": ResourceState.RUNNING,
    "new": ResourceState.PENDING,
    "off": ResourceState.STOPPED,
    "archive": ResourceState.TERMINATED,
}


class DropletResources:
    """Handles DigitalOcean Droplet discovery."""

    def __init__(self, auth: DigitalOceanAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_droplets(self, region: str | None = None) -> list[Resource]:
        """List all Droplets in the account.

        Args:
            region: Optional region slug filter (e.g., 'nyc3', 'sfo3').
        """
        raw = await self._auth.get_paginated("/droplets", "droplets")

        resources: list[Resource] = []
        for d in raw:
            region_slug = (d.get("region") or {}).get("slug", "")
            if region and region_slug != region:
                continue
            resources.append(self._map_droplet(d))

        logger.debug("Found %d DigitalOcean Droplets", len(resources))
        return resources

    def _map_droplet(self, d: dict[str, Any]) -> Resource:
        """Map a DO Droplet to a unified Resource."""
        status = d.get("status", "unknown")
        region = d.get("region") or {}
        image = d.get("image") or {}
        size = d.get("size") or {}
        networks = d.get("networks") or {}
        tags = d.get("tags") or []
        tag_dict = {f"tag_{i}": t for i, t in enumerate(tags)} if tags else {}

        # Get IPs
        public_ip = ""
        private_ip = ""
        for v4 in networks.get("v4", []):
            if v4.get("type") == "public":
                public_ip = v4.get("ip_address", "")
            elif v4.get("type") == "private":
                private_ip = v4.get("ip_address", "")

        return Resource(
            id=str(d.get("id", "")),
            name=d.get("name", "") or str(d.get("id", "")),
            resource_type=ResourceType.COMPUTE,
            provider="digitalocean",
            region=region.get("slug", ""),
            state=_DROPLET_STATE_MAP.get(status, ResourceState.UNKNOWN),
            created_at=d.get("created_at"),
            tags=tag_dict,
            metadata={
                "size": size.get("slug", ""),
                "vcpus": str(d.get("vcpus", "")),
                "memory_mb": str(d.get("memory", "")),
                "disk_gb": str(d.get("disk", "")),
                "image": image.get("slug") or image.get("name", ""),
                "os": (image.get("distribution") or ""),
                "public_ip": public_ip,
                "private_ip": private_ip,
                "monthly_cost": str(size.get("price_monthly", "")),
                "resource_subtype": "droplet",
            },
        )
