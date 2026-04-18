"""GCP Cloud SQL instance resource discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from googleapiclient.discovery import build

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.gcp.auth import GCPAuth

logger = get_logger(__name__)

_CLOUDSQL_STATE_MAP: dict[str, ResourceState] = {
    "RUNNABLE": ResourceState.RUNNING,
    "SUSPENDED": ResourceState.STOPPED,
    "PENDING_CREATE": ResourceState.PENDING,
    "MAINTENANCE": ResourceState.PENDING,
    "FAILED": ResourceState.ERROR,
    "UNKNOWN_STATE": ResourceState.UNKNOWN,
}


class CloudSQLResources:
    """Handles GCP Cloud SQL instance discovery via the SQL Admin API."""

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_instances(self, region: str | None = None) -> list[Resource]:
        """List all Cloud SQL instances in the project.

        Args:
            region: Optional region to filter by (e.g., 'us-central1').

        Returns:
            List of Resource objects representing Cloud SQL instances.
        """
        project = self._auth.project_id
        if not project:
            logger.warning("No GCP project ID configured — cannot list Cloud SQL instances")
            return []

        def _fetch() -> list[dict[str, Any]]:
            service = build(
                "sqladmin", "v1",
                credentials=self._auth.credentials,
                cache_discovery=False,
            )
            instances: list[dict[str, Any]] = []
            request = service.instances().list(project=project)
            while request is not None:
                response = request.execute()
                instances.extend(response.get("items", []))
                request = service.instances().list_next(
                    previous_request=request, previous_response=response
                )
            return instances

        raw_instances = await asyncio.to_thread(_fetch)

        resources: list[Resource] = []
        for instance in raw_instances:
            inst_region = instance.get("region", "")
            if region and inst_region != region:
                continue
            resources.append(self._map_instance(instance))

        logger.debug("Found %d Cloud SQL instances", len(resources))
        return resources

    def _map_instance(self, instance: dict[str, Any]) -> Resource:
        """Map a Cloud SQL instance dict to a unified Resource."""
        state_str = instance.get("state", "UNKNOWN_STATE")
        settings = instance.get("settings", {})
        labels = settings.get("userLabels", {})

        # Extract IP addresses
        ip_addresses = [
            addr.get("ipAddress", "")
            for addr in instance.get("ipAddresses", [])
        ]

        return Resource(
            id=instance.get("name", ""),
            name=instance.get("name", ""),
            resource_type=ResourceType.DATABASE,
            provider="gcp",
            region=instance.get("region", ""),
            state=_CLOUDSQL_STATE_MAP.get(state_str, ResourceState.UNKNOWN),
            created_at=None,
            tags=labels,
            metadata={
                "database_version": instance.get("databaseVersion", ""),
                "tier": settings.get("tier", ""),
                "data_disk_size_gb": str(settings.get("dataDiskSizeGb", "")),
                "availability_type": settings.get("availabilityType", ""),
                "ip_addresses": ", ".join(ip_addresses),
                "connection_name": instance.get("connectionName", ""),
                "gce_zone": instance.get("gceZone", ""),
                "instance_type": instance.get("instanceType", ""),
                "resource_subtype": "cloudsql_instance",
            },
        )
