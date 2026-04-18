"""Vultr storage detail information.

Retrieves detailed info for block storage and object storage,
matching the s3_details / gcs_details pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.vultr.auth import VultrAuth

logger = get_logger(__name__)


class BlockStorageDetails(BaseModel):
    """Detailed info for a Vultr block storage volume."""

    id: str
    label: str = ""
    region: str = ""
    size_gb: int = 0
    status: str = ""
    block_type: str = ""
    mount_id: str = ""
    attached_to: str = ""
    cost: str = ""
    date_created: str = ""


class ObjectStorageDetails(BaseModel):
    """Detailed info for a Vultr object storage subscription."""

    id: str
    label: str = ""
    region: str = ""
    status: str = ""
    cluster_id: str = ""
    s3_hostname: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    date_created: str = ""


class VultrStorageDetailAnalyzer:
    """Retrieves detailed Vultr storage information."""

    def __init__(self, auth: VultrAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def get_block_details(self, block_id: str) -> BlockStorageDetails:
        """Get details for a block storage volume.

        Args:
            block_id: Block storage ID.

        Returns:
            BlockStorageDetails with full info.
        """
        data = await self._auth.get(f"/blocks/{block_id}")
        block = data.get("block", {})

        return BlockStorageDetails(
            id=block.get("id", block_id),
            label=block.get("label", ""),
            region=block.get("region", ""),
            size_gb=block.get("size_gb", 0),
            status=block.get("status", ""),
            block_type=block.get("block_type", ""),
            mount_id=block.get("mount_id", ""),
            attached_to=block.get("attached_to_instance", ""),
            cost=str(block.get("cost", "")),
            date_created=block.get("date_created", ""),
        )

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def get_object_details(self, obj_id: str) -> ObjectStorageDetails:
        """Get details for an object storage subscription.

        Args:
            obj_id: Object storage ID.

        Returns:
            ObjectStorageDetails with full info.
        """
        data = await self._auth.get(f"/object-storage/{obj_id}")
        obj = data.get("object_storage", {})

        return ObjectStorageDetails(
            id=str(obj.get("id", obj_id)),
            label=obj.get("label", ""),
            region=obj.get("region", ""),
            status=obj.get("status", ""),
            cluster_id=str(obj.get("cluster_id", "")),
            s3_hostname=obj.get("s3_hostname", ""),
            s3_access_key=obj.get("s3_access_key", ""),
            s3_secret_key=obj.get("s3_secret_key", ""),
            date_created=obj.get("date_created", ""),
        )
