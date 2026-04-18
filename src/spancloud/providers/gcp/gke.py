"""GCP GKE cluster and node pool resource discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from google.cloud.container_v1 import ClusterManagerClient
from google.cloud.container_v1.types import ListClustersRequest

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.gcp.auth import GCPAuth

logger = get_logger(__name__)

_GKE_CLUSTER_STATE_MAP: dict[str, ResourceState] = {
    "PROVISIONING": ResourceState.PENDING,
    "RUNNING": ResourceState.RUNNING,
    "RECONCILING": ResourceState.PENDING,
    "STOPPING": ResourceState.PENDING,
    "ERROR": ResourceState.ERROR,
    "DEGRADED": ResourceState.ERROR,
    "STATUS_UNSPECIFIED": ResourceState.UNKNOWN,
}

_GKE_NODEPOOL_STATE_MAP: dict[str, ResourceState] = {
    "PROVISIONING": ResourceState.PENDING,
    "RUNNING": ResourceState.RUNNING,
    "RUNNING_WITH_ERROR": ResourceState.ERROR,
    "RECONCILING": ResourceState.PENDING,
    "STOPPING": ResourceState.PENDING,
    "ERROR": ResourceState.ERROR,
    "STATUS_UNSPECIFIED": ResourceState.UNKNOWN,
}


class GKEResources:
    """Handles GKE cluster and node pool discovery."""

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_clusters(self, region: str | None = None) -> list[Resource]:
        """List all GKE clusters in the project.

        Uses the '-' wildcard for location to list clusters across all zones/regions,
        then filters by region if specified.

        Args:
            region: Optional region to filter by (e.g., 'us-central1').

        Returns:
            List of Resource objects representing GKE clusters.
        """
        project = self._auth.project_id
        if not project:
            logger.warning("No GCP project ID configured — cannot list GKE clusters")
            return []

        client = ClusterManagerClient(credentials=self._auth.credentials)

        def _fetch() -> list[Any]:
            # Use '-' as location wildcard to get all clusters
            parent = f"projects/{project}/locations/-"
            request = ListClustersRequest(parent=parent)
            response = client.list_clusters(request=request)
            return list(response.clusters) if response.clusters else []

        clusters = await asyncio.to_thread(_fetch)

        resources: list[Resource] = []
        for cluster in clusters:
            cluster_location = cluster.location or ""
            if region and not cluster_location.startswith(region):
                continue
            resources.append(self._map_cluster(cluster))

        logger.debug("Found %d GKE clusters", len(resources))
        return resources

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_node_pools(self, region: str | None = None) -> list[Resource]:
        """List all node pools across all GKE clusters in the project.

        Args:
            region: Optional region to filter by.

        Returns:
            List of Resource objects representing GKE node pools.
        """
        project = self._auth.project_id
        if not project:
            logger.warning("No GCP project ID configured — cannot list GKE node pools")
            return []

        client = ClusterManagerClient(credentials=self._auth.credentials)

        def _fetch() -> list[dict[str, Any]]:
            parent = f"projects/{project}/locations/-"
            request = ListClustersRequest(parent=parent)
            response = client.list_clusters(request=request)
            pools: list[dict[str, Any]] = []
            for cluster in response.clusters or []:
                for pool in cluster.node_pools or []:
                    pools.append({
                        "pool": pool,
                        "cluster_name": cluster.name,
                        "location": cluster.location or "",
                    })
            return pools

        raw_pools = await asyncio.to_thread(_fetch)

        resources: list[Resource] = []
        for item in raw_pools:
            if region and not item["location"].startswith(region):
                continue
            resources.append(
                self._map_node_pool(item["pool"], item["cluster_name"], item["location"])
            )

        logger.debug("Found %d GKE node pools", len(resources))
        return resources

    def _map_cluster(self, cluster: Any) -> Resource:
        """Map a GKE cluster to a unified Resource."""
        status = cluster.status.name if cluster.status else "STATUS_UNSPECIFIED"
        labels = dict(cluster.resource_labels) if cluster.resource_labels else {}

        node_count = sum(
            (pool.initial_node_count or 0) for pool in (cluster.node_pools or [])
        )

        return Resource(
            id=cluster.name or "",
            name=cluster.name or "",
            resource_type=ResourceType.CONTAINER,
            provider="gcp",
            region=cluster.location or "",
            state=_GKE_CLUSTER_STATE_MAP.get(status, ResourceState.UNKNOWN),
            created_at=None,
            tags=labels,
            metadata={
                "kubernetes_version": cluster.current_master_version or "",
                "node_version": cluster.current_node_version or "",
                "endpoint": cluster.endpoint or "",
                "node_pool_count": str(len(cluster.node_pools or [])),
                "total_node_count": str(node_count),
                "network": (cluster.network or "").rsplit("/", 1)[-1],
                "subnetwork": (cluster.subnetwork or "").rsplit("/", 1)[-1],
                "cluster_ipv4_cidr": cluster.cluster_ipv4_cidr or "",
                "resource_subtype": "gke_cluster",
            },
        )

    def _map_node_pool(self, pool: Any, cluster_name: str, location: str) -> Resource:
        """Map a GKE node pool to a unified Resource."""
        status = pool.status.name if pool.status else "STATUS_UNSPECIFIED"

        autoscaling = pool.autoscaling
        config = pool.config

        return Resource(
            id=f"{cluster_name}/{pool.name}",
            name=pool.name or "",
            resource_type=ResourceType.CONTAINER,
            provider="gcp",
            region=location,
            state=_GKE_NODEPOOL_STATE_MAP.get(status, ResourceState.UNKNOWN),
            created_at=None,
            tags={},
            metadata={
                "cluster": cluster_name,
                "machine_type": config.machine_type if config else "",
                "disk_size_gb": str(config.disk_size_gb) if config else "",
                "disk_type": config.disk_type if config else "",
                "initial_node_count": str(pool.initial_node_count or ""),
                "autoscaling_enabled": str(autoscaling.enabled if autoscaling else False),
                "min_node_count": str(autoscaling.min_node_count if autoscaling else ""),
                "max_node_count": str(autoscaling.max_node_count if autoscaling else ""),
                "version": pool.version or "",
                "resource_subtype": "gke_node_pool",
            },
        )
