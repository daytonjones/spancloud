"""Vultr instance (cloud + bare metal) resource discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.vultr.auth import VultrAuth

logger = get_logger(__name__)

_INSTANCE_STATE_MAP: dict[str, ResourceState] = {
    "active": ResourceState.RUNNING,
    "pending": ResourceState.PENDING,
    "suspended": ResourceState.STOPPED,
    "resizing": ResourceState.PENDING,
    "halted": ResourceState.STOPPED,
}


class InstanceResources:
    """Handles Vultr cloud instance discovery."""

    def __init__(self, auth: VultrAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_instances(self, region: str | None = None) -> list[Resource]:
        """List all cloud instances.

        Args:
            region: Optional region filter (e.g., 'ewr', 'lax').

        Returns:
            List of Resource objects representing instances.
        """
        raw = await self._auth.get_paginated("/instances", "instances")

        resources: list[Resource] = []
        for inst in raw:
            inst_region = inst.get("region", "")
            if region and inst_region != region:
                continue
            resources.append(self._map_instance(inst))

        logger.debug("Found %d Vultr instances", len(resources))
        return resources

    def _map_instance(self, inst: dict[str, Any]) -> Resource:
        """Map a Vultr instance to a unified Resource."""
        status = inst.get("status", "unknown")
        power = inst.get("power_status", "")
        tags = inst.get("tags", [])
        tag_dict = {f"tag_{i}": t for i, t in enumerate(tags)} if tags else {}
        label = inst.get("label", "")

        return Resource(
            id=inst.get("id", ""),
            name=label or inst.get("id", ""),
            resource_type=ResourceType.COMPUTE,
            provider="vultr",
            region=inst.get("region", ""),
            state=_INSTANCE_STATE_MAP.get(status, ResourceState.UNKNOWN),
            created_at=inst.get("date_created"),
            tags=tag_dict,
            metadata={
                "plan": inst.get("plan", ""),
                "vcpu_count": str(inst.get("vcpu_count", "")),
                "ram": f"{inst.get('ram', '')} MB",
                "disk": f"{inst.get('disk', '')} GB",
                "os": inst.get("os", ""),
                "main_ip": inst.get("main_ip", ""),
                "v6_main_ip": inst.get("v6_main_ip", ""),
                "power_status": power,
                "server_status": inst.get("server_status", ""),
                "resource_subtype": "instance",
            },
        )


class BareMetalResources:
    """Handles Vultr bare metal instance discovery."""

    def __init__(self, auth: VultrAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_bare_metals(self, region: str | None = None) -> list[Resource]:
        """List all bare metal instances.

        Args:
            region: Optional region filter.

        Returns:
            List of Resource objects representing bare metal servers.
        """
        raw = await self._auth.get_paginated("/bare-metals", "bare_metals")

        resources: list[Resource] = []
        for bm in raw:
            bm_region = bm.get("region", "")
            if region and bm_region != region:
                continue
            resources.append(self._map_bare_metal(bm))

        logger.debug("Found %d Vultr bare metal instances", len(resources))
        return resources

    def _map_bare_metal(self, bm: dict[str, Any]) -> Resource:
        """Map a Vultr bare metal instance to a unified Resource."""
        status = bm.get("status", "unknown")
        tags = bm.get("tags", [])
        tag_dict = {f"tag_{i}": t for i, t in enumerate(tags)} if tags else {}

        return Resource(
            id=bm.get("id", ""),
            name=bm.get("label", "") or bm.get("id", ""),
            resource_type=ResourceType.COMPUTE,
            provider="vultr",
            region=bm.get("region", ""),
            state=_INSTANCE_STATE_MAP.get(status, ResourceState.UNKNOWN),
            created_at=bm.get("date_created"),
            tags=tag_dict,
            metadata={
                "plan": bm.get("plan", ""),
                "cpu_count": str(bm.get("cpu_count", "")),
                "ram": bm.get("ram", ""),
                "disk": bm.get("disk", ""),
                "os": bm.get("os", ""),
                "main_ip": bm.get("main_ip", ""),
                "resource_subtype": "bare_metal",
            },
        )
