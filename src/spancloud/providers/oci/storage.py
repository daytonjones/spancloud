"""OCI storage — Object Storage buckets + Block Volumes."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.oci.auth import OCIAuth

logger = get_logger(__name__)


class ObjectStorageResources:
    """Handles OCI Object Storage buckets."""

    def __init__(self, auth: OCIAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_buckets(self, region: str | None = None) -> list[Resource]:
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d OCI buckets", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        import oci

        config = dict(self._auth.config)
        if region:
            config["region"] = region

        compartment = self._auth.compartment_id
        if not compartment:
            return []

        client = oci.object_storage.ObjectStorageClient(config)
        try:
            namespace = client.get_namespace().data
        except Exception as exc:
            logger.debug("Could not fetch OCI namespace: %s", exc)
            return []

        resources: list[Resource] = []
        page: str | None = None
        while True:
            result = client.list_buckets(
                namespace_name=namespace,
                compartment_id=compartment,
                page=page,
            )
            for b in result.data or []:
                resources.append(self._map_bucket(b, namespace, config["region"]))
            page = result.next_page
            if not page:
                break
        return resources

    def _map_bucket(self, b: Any, namespace: str, region: str) -> Resource:
        return Resource(
            id=f"{namespace}/{b.name}",
            name=b.name,
            resource_type=ResourceType.STORAGE,
            provider="oci",
            region=region,
            state=ResourceState.RUNNING,
            created_at=getattr(b, "time_created", None),
            tags=dict(getattr(b, "freeform_tags", None) or {}),
            metadata={
                "namespace": namespace,
                "compartment_id": getattr(b, "compartment_id", "") or "",
                "etag": getattr(b, "etag", "") or "",
                "resource_subtype": "object_storage_bucket",
            },
        )


class BlockVolumeResources:
    """Handles OCI Block Volumes."""

    def __init__(self, auth: OCIAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_volumes(self, region: str | None = None) -> list[Resource]:
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d OCI block volumes", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        import oci

        config = dict(self._auth.config)
        if region:
            config["region"] = region
        compartment = self._auth.compartment_id
        if not compartment:
            return []

        client = oci.core.BlockstorageClient(config)

        resources: list[Resource] = []
        page: str | None = None
        while True:
            result = client.list_volumes(
                compartment_id=compartment, page=page
            )
            for v in result.data or []:
                resources.append(self._map_volume(v, config["region"]))
            page = result.next_page
            if not page:
                break
        return resources

    def _map_volume(self, v: Any, region: str) -> Resource:
        state = str(v.lifecycle_state)
        state_mapped = (
            ResourceState.RUNNING
            if state == "AVAILABLE"
            else ResourceState.PENDING
            if state in ("PROVISIONING", "RESTORING")
            else ResourceState.TERMINATED
            if state == "TERMINATED"
            else ResourceState.UNKNOWN
        )

        return Resource(
            id=v.id,
            name=getattr(v, "display_name", "") or v.id,
            resource_type=ResourceType.STORAGE,
            provider="oci",
            region=region,
            state=state_mapped,
            created_at=getattr(v, "time_created", None),
            tags=dict(getattr(v, "freeform_tags", None) or {}),
            metadata={
                "size_gb": str(getattr(v, "size_in_gbs", "") or ""),
                "vpus_per_gb": str(getattr(v, "vpus_per_gb", "") or ""),
                "availability_domain": getattr(v, "availability_domain", "") or "",
                "compartment_id": getattr(v, "compartment_id", "") or "",
                "resource_subtype": "block_volume",
            },
        )
