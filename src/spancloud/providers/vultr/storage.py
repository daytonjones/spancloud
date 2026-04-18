"""Vultr block storage and object storage resource discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.vultr.auth import VultrAuth

logger = get_logger(__name__)


class BlockStorageResources:
    """Handles Vultr block storage discovery."""

    def __init__(self, auth: VultrAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_blocks(self, region: str | None = None) -> list[Resource]:
        """List all block storage volumes.

        Args:
            region: Optional region filter.

        Returns:
            List of Resource objects representing block storage volumes.
        """
        raw = await self._auth.get_paginated("/blocks", "blocks")

        resources: list[Resource] = []
        for block in raw:
            block_region = block.get("region", "")
            if region and block_region != region:
                continue
            resources.append(self._map_block(block))

        logger.debug("Found %d Vultr block storage volumes", len(resources))
        return resources

    def _map_block(self, block: dict[str, Any]) -> Resource:
        """Map a Vultr block storage volume to a unified Resource."""
        status = block.get("status", "")
        attached = block.get("attached_to_instance", "")

        return Resource(
            id=block.get("id", ""),
            name=block.get("label", "") or block.get("id", ""),
            resource_type=ResourceType.STORAGE,
            provider="vultr",
            region=block.get("region", ""),
            state=ResourceState.RUNNING if status == "active" else ResourceState.PENDING,
            created_at=block.get("date_created"),
            tags={},
            metadata={
                "size_gb": str(block.get("size_gb", "")),
                "block_type": block.get("block_type", ""),
                "mount_id": block.get("mount_id", ""),
                "attached_to": attached,
                "cost": str(block.get("cost", "")),
                "resource_subtype": "block_storage",
            },
        )


class ObjectStorageResources:
    """Handles Vultr object storage discovery."""

    def __init__(self, auth: VultrAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_object_stores(self, region: str | None = None) -> list[Resource]:
        """List all object storage subscriptions.

        Args:
            region: Optional region filter.

        Returns:
            List of Resource objects representing object storage clusters.
        """
        raw = await self._auth.get_paginated("/object-storage", "object_storages")

        resources: list[Resource] = []
        for obj in raw:
            obj_region = obj.get("region", "")
            if region and obj_region != region:
                continue
            resources.append(self._map_object_storage(obj))

        logger.debug("Found %d Vultr object storage subscriptions", len(resources))
        return resources

    def _map_object_storage(self, obj: dict[str, Any]) -> Resource:
        """Map a Vultr object storage to a unified Resource."""
        status = obj.get("status", "")

        return Resource(
            id=str(obj.get("id", "")),
            name=obj.get("label", "") or str(obj.get("id", "")),
            resource_type=ResourceType.STORAGE,
            provider="vultr",
            region=obj.get("region", ""),
            state=ResourceState.RUNNING if status == "active" else ResourceState.PENDING,
            created_at=obj.get("date_created"),
            tags={},
            metadata={
                "cluster_id": str(obj.get("cluster_id", "")),
                "s3_hostname": obj.get("s3_hostname", ""),
                "s3_access_key": obj.get("s3_access_key", ""),
                "resource_subtype": "object_storage",
            },
        )
