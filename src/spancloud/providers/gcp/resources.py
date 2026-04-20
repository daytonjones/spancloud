"""GCP resource discovery and mapping to the unified Resource model."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from google.cloud import compute_v1, storage

from spancloud.core.exceptions import ResourceNotFoundError
from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.providers.gcp._retry import GCP_RETRY

if TYPE_CHECKING:
    from spancloud.providers.gcp.auth import GCPAuth

logger = get_logger(__name__)

# Map GCP instance statuses to Spancloud ResourceState.
_GCE_STATE_MAP: dict[str, ResourceState] = {
    "PROVISIONING": ResourceState.PENDING,
    "STAGING": ResourceState.PENDING,
    "RUNNING": ResourceState.RUNNING,
    "STOPPING": ResourceState.PENDING,
    "SUSPENDING": ResourceState.PENDING,
    "SUSPENDED": ResourceState.STOPPED,
    "REPAIRING": ResourceState.PENDING,
    "TERMINATED": ResourceState.STOPPED,
}


class ComputeResources:
    """Handles GCP Compute Engine instance discovery."""

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    @GCP_RETRY
    async def list_instances(self, region: str | None = None) -> list[Resource]:
        """List Compute Engine instances.

        Uses aggregated list to get instances across all zones, or filters
        by zone prefix if region is specified.

        Args:
            region: Optional region to filter by (e.g., 'us-central1').

        Returns:
            List of Resource objects representing GCE instances.
        """
        project = self._auth.project_id
        if not project:
            logger.warning("No GCP project ID configured — cannot list instances")
            return []

        client = compute_v1.InstancesClient(credentials=self._auth.credentials)

        def _fetch() -> list[dict[str, Any]]:
            instances: list[dict[str, Any]] = []
            request = compute_v1.AggregatedListInstancesRequest(project=project)
            for zone, scoped_list in client.aggregated_list(request=request):
                if scoped_list.instances:
                    for inst in scoped_list.instances:
                        if region and not zone.endswith(region) and region not in zone:
                            continue
                        instances.append({"instance": inst, "zone": zone})
            return instances

        raw_instances = await asyncio.to_thread(_fetch)
        resources = [self._map_instance(item["instance"], item["zone"]) for item in raw_instances]

        logger.debug("Found %d GCE instances", len(resources))
        return resources

    @GCP_RETRY
    async def get_instance(
        self, instance_id: str, zone: str, region: str | None = None
    ) -> Resource:
        """Fetch a single Compute Engine instance.

        Args:
            instance_id: The instance name or numeric ID.
            zone: The zone where the instance lives (e.g., 'us-central1-a').
            region: Ignored (zone is required for GCE).

        Returns:
            A Resource representing the instance.

        Raises:
            ResourceNotFoundError: If the instance doesn't exist.
        """
        project = self._auth.project_id
        client = compute_v1.InstancesClient(credentials=self._auth.credentials)

        try:
            instance = await asyncio.to_thread(
                client.get, project=project, zone=zone, instance=instance_id
            )
        except Exception as exc:
            if "404" in str(exc) or "not found" in str(exc).lower():
                raise ResourceNotFoundError("gcp", "compute", instance_id) from exc
            raise

        return self._map_instance(instance, zone)

    def _map_instance(self, instance: Any, zone: str) -> Resource:
        """Map a GCE Instance object to a unified Resource."""
        labels = dict(instance.labels) if instance.labels else {}
        status = instance.status if instance.status else "UNKNOWN"

        # Extract zone short name from full path
        zone_name = zone.split("/")[-1] if "/" in zone else zone

        # Get network interfaces for IP info
        network_ips: dict[str, str] = {}
        if instance.network_interfaces:
            iface = instance.network_interfaces[0]
            network_ips["private_ip"] = iface.network_i_p or ""
            if iface.access_configs:
                network_ips["public_ip"] = iface.access_configs[0].nat_i_p or ""

        return Resource(
            id=str(instance.id),
            name=instance.name or str(instance.id),
            resource_type=ResourceType.COMPUTE,
            provider="gcp",
            region=zone_name,
            state=_GCE_STATE_MAP.get(status, ResourceState.UNKNOWN),
            created_at=None,  # GCE creation timestamp requires parsing
            tags=labels,
            metadata={
                "machine_type": (instance.machine_type or "").rsplit("/", 1)[-1],
                "zone": zone_name,
                **network_ips,
            },
        )


class StorageResources:
    """Handles GCP Cloud Storage bucket discovery."""

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    @GCP_RETRY
    async def list_buckets(self) -> list[Resource]:
        """List all Cloud Storage buckets in the project.

        Returns:
            List of Resource objects representing GCS buckets.
        """
        project = self._auth.project_id
        if not project:
            logger.warning("No GCP project ID configured — cannot list buckets")
            return []

        client = storage.Client(
            project=project,
            credentials=self._auth.credentials,
        )

        buckets = await asyncio.to_thread(lambda: list(client.list_buckets()))

        resources: list[Resource] = []
        for bucket in buckets:
            resources.append(
                Resource(
                    id=bucket.name,
                    name=bucket.name,
                    resource_type=ResourceType.STORAGE,
                    provider="gcp",
                    region=bucket.location or "global",
                    state=ResourceState.RUNNING,
                    created_at=bucket.time_created,
                    tags=dict(bucket.labels) if bucket.labels else {},
                    metadata={
                        "storage_class": bucket.storage_class or "",
                        "location_type": bucket.location_type or "",
                    },
                )
            )

        logger.debug("Found %d GCS buckets", len(resources))
        return resources
