"""Alibaba Cloud OSS (Object Storage Service) + ECS Disk discovery.

OSS uses the standalone `oss2` SDK (not Tea-based).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.alibaba.auth import AlibabaAuth

logger = get_logger(__name__)


class OSSResources:
    """Handles Alibaba OSS bucket discovery."""

    def __init__(self, auth: AlibabaAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_buckets(self, region: str | None = None) -> list[Resource]:
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d OSS buckets", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        import oss2

        self._auth._ensure_credentials()  # noqa: SLF001
        if not self._auth.access_key_id:
            return []

        region_id = region or self._auth.region
        endpoint = f"https://oss-{region_id}.aliyuncs.com"
        auth = oss2.Auth(
            self._auth.access_key_id, self._auth._access_key_secret  # noqa: SLF001
        )
        service = oss2.Service(auth, endpoint)

        resources: list[Resource] = []
        for bucket in oss2.BucketIterator(service):
            resources.append(self._map_bucket(bucket, region_id))
        return resources

    def _map_bucket(self, b: Any, region: str) -> Resource:
        return Resource(
            id=b.name,
            name=b.name,
            resource_type=ResourceType.STORAGE,
            provider="alibaba",
            region=b.location or region,
            state=ResourceState.RUNNING,
            created_at=(
                __import__("datetime").datetime.fromtimestamp(b.creation_date)
                if b.creation_date
                else None
            ),
            metadata={
                "storage_class": getattr(b, "storage_class", "") or "",
                "extranet_endpoint": getattr(b, "extranet_endpoint", "") or "",
                "resource_subtype": "oss_bucket",
            },
        )


class DiskResources:
    """Handles Alibaba ECS Disk discovery (block storage)."""

    def __init__(self, auth: AlibabaAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_disks(self, region: str | None = None) -> list[Resource]:
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d Alibaba disks", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        from alibabacloud_ecs20140526 import models as ecs_models
        from alibabacloud_ecs20140526.client import Client as EcsClient

        region_id = region or self._auth.region
        client = EcsClient(self._auth.ecs_config(region_id))

        resources: list[Resource] = []
        page_number = 1
        while True:
            req = ecs_models.DescribeDisksRequest(
                region_id=region_id,
                page_number=page_number,
                page_size=100,
            )
            response = client.describe_disks(req)
            body = response.body
            disks_holder = getattr(body, "disks", None)
            disk_list = (
                getattr(disks_holder, "disk", []) or [] if disks_holder else []
            )
            if not disk_list:
                break

            for d in disk_list:
                resources.append(self._map_disk(d, region_id))

            total = getattr(body, "total_count", 0) or 0
            if page_number * 100 >= total:
                break
            page_number += 1
        return resources

    def _map_disk(self, d: Any, region: str) -> Resource:
        status = str(getattr(d, "status", "") or "")
        state = (
            ResourceState.RUNNING
            if status == "In_use"
            else ResourceState.STOPPED
            if status == "Available"
            else ResourceState.UNKNOWN
        )
        return Resource(
            id=getattr(d, "disk_id", "") or "",
            name=getattr(d, "disk_name", "") or getattr(d, "disk_id", ""),
            resource_type=ResourceType.STORAGE,
            provider="alibaba",
            region=region,
            state=state,
            metadata={
                "size_gb": str(getattr(d, "size", "") or ""),
                "category": getattr(d, "category", "") or "",
                "disk_type": getattr(d, "type", "") or "",
                "instance_id": getattr(d, "instance_id", "") or "",
                "zone_id": getattr(d, "zone_id", "") or "",
                "resource_subtype": "ecs_disk",
            },
        )
