"""OCI Compute (Instances) resource discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.providers.oci._retry import OCI_RETRY as retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.oci.auth import OCIAuth

logger = get_logger(__name__)

_INSTANCE_STATE_MAP: dict[str, ResourceState] = {
    "RUNNING": ResourceState.RUNNING,
    "STOPPED": ResourceState.STOPPED,
    "STARTING": ResourceState.PENDING,
    "STOPPING": ResourceState.PENDING,
    "PROVISIONING": ResourceState.PENDING,
    "TERMINATED": ResourceState.TERMINATED,
    "TERMINATING": ResourceState.PENDING,
}


class InstanceResources:
    """Handles OCI Compute instance discovery."""

    def __init__(self, auth: OCIAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_instances(self, region: str | None = None) -> list[Resource]:
        """List compute instances in the default compartment."""
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d OCI instances", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        import oci

        config = dict(self._auth.config)
        if region:
            config["region"] = region

        client = oci.core.ComputeClient(config)
        compartment = self._auth.compartment_id
        if not compartment:
            return []

        resources: list[Resource] = []
        page: str | None = None
        while True:
            result = client.list_instances(
                compartment_id=compartment, page=page
            )
            for inst in result.data or []:
                resources.append(self._map_instance(inst, config["region"]))
            page = result.next_page
            if not page:
                break
        return resources

    def _map_instance(self, inst: Any, region: str) -> Resource:
        tags = dict(getattr(inst, "freeform_tags", None) or {})
        metadata = {
            "shape": getattr(inst, "shape", "") or "",
            "availability_domain": getattr(inst, "availability_domain", "") or "",
            "compartment_id": getattr(inst, "compartment_id", "") or "",
            "fault_domain": getattr(inst, "fault_domain", "") or "",
            "image_id": getattr(inst, "image_id", "") or "",
            "resource_subtype": "compute_instance",
        }
        shape_cfg = getattr(inst, "shape_config", None)
        if shape_cfg:
            metadata["ocpus"] = str(getattr(shape_cfg, "ocpus", "") or "")
            metadata["memory_gb"] = str(
                getattr(shape_cfg, "memory_in_gbs", "") or ""
            )

        return Resource(
            id=inst.id,
            name=getattr(inst, "display_name", "") or inst.id,
            resource_type=ResourceType.COMPUTE,
            provider="oci",
            region=region,
            state=_INSTANCE_STATE_MAP.get(
                str(inst.lifecycle_state), ResourceState.UNKNOWN
            ),
            created_at=getattr(inst, "time_created", None),
            tags=tags,
            metadata=metadata,
        )
