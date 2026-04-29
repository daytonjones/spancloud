"""OCI Container Engine for Kubernetes (OKE) discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.providers.oci._retry import OCI_RETRY as retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.oci.auth import OCIAuth

logger = get_logger(__name__)


class OKEResources:
    """Handles OCI OKE cluster discovery."""

    def __init__(self, auth: OCIAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_clusters(self, region: str | None = None) -> list[Resource]:
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d OKE clusters", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        import oci

        config = dict(self._auth.config)
        if region:
            config["region"] = region
        compartment = self._auth.compartment_id
        if not compartment:
            return []

        client = oci.container_engine.ContainerEngineClient(config)
        resources: list[Resource] = []
        page: str | None = None
        while True:
            result = client.list_clusters(
                compartment_id=compartment, page=page
            )
            for c in result.data or []:
                resources.append(self._map_cluster(c, config["region"]))
            page = result.next_page
            if not page:
                break
        return resources

    def _map_cluster(self, c: Any, region: str) -> Resource:
        lifecycle = str(getattr(c, "lifecycle_state", "") or "")
        state = (
            ResourceState.RUNNING
            if lifecycle == "ACTIVE"
            else ResourceState.PENDING
            if lifecycle in ("CREATING", "UPDATING")
            else ResourceState.TERMINATED
            if lifecycle == "DELETED"
            else ResourceState.UNKNOWN
        )
        return Resource(
            id=c.id,
            name=getattr(c, "name", "") or c.id,
            resource_type=ResourceType.CONTAINER,
            provider="oci",
            region=region,
            state=state,
            tags=dict(getattr(c, "freeform_tags", None) or {}),
            metadata={
                "kubernetes_version": getattr(c, "kubernetes_version", "") or "",
                "vcn_id": getattr(c, "vcn_id", "") or "",
                "endpoint": str(getattr(c, "endpoints", "") or ""),
                "compartment_id": getattr(c, "compartment_id", "") or "",
                "resource_subtype": "oke_cluster",
            },
        )
