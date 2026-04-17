"""DigitalOcean Kubernetes (DOKS) resource discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.digitalocean.auth import DigitalOceanAuth

logger = get_logger(__name__)

_DOKS_STATE_MAP: dict[str, ResourceState] = {
    "running": ResourceState.RUNNING,
    "provisioning": ResourceState.PENDING,
    "degraded": ResourceState.ERROR,
    "deleted": ResourceState.TERMINATED,
    "error": ResourceState.ERROR,
}


class KubernetesResources:
    """Handles DOKS cluster + node pool discovery."""

    def __init__(self, auth: DigitalOceanAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_clusters(self, region: str | None = None) -> list[Resource]:
        """List all DOKS clusters and their node pools."""
        raw = await self._auth.get_paginated(
            "/kubernetes/clusters", "kubernetes_clusters"
        )

        resources: list[Resource] = []
        for cluster in raw:
            cluster_region = cluster.get("region", "")
            if region and cluster_region != region:
                continue
            resources.append(self._map_cluster(cluster))

            # Also map node pools
            for pool in cluster.get("node_pools") or []:
                resources.append(
                    self._map_pool(pool, cluster.get("id", ""), cluster_region)
                )

        logger.debug("Found %d DOKS resources", len(resources))
        return resources

    def _map_cluster(self, cluster: dict[str, Any]) -> Resource:
        status = (cluster.get("status") or {}).get("state", "")
        tags = cluster.get("tags") or []
        tag_dict = {f"tag_{i}": t for i, t in enumerate(tags)} if tags else {}

        return Resource(
            id=cluster.get("id", ""),
            name=cluster.get("name", "") or cluster.get("id", ""),
            resource_type=ResourceType.CONTAINER,
            provider="digitalocean",
            region=cluster.get("region", ""),
            state=_DOKS_STATE_MAP.get(status, ResourceState.UNKNOWN),
            created_at=cluster.get("created_at"),
            tags=tag_dict,
            metadata={
                "version": cluster.get("version", ""),
                "endpoint": cluster.get("endpoint", ""),
                "ipv4": cluster.get("ipv4", ""),
                "node_pool_count": str(len(cluster.get("node_pools") or [])),
                "auto_upgrade": str(cluster.get("auto_upgrade", False)),
                "ha": str(cluster.get("ha", False)),
                "resource_subtype": "doks_cluster",
            },
        )

    def _map_pool(
        self, pool: dict[str, Any], cluster_id: str, region: str
    ) -> Resource:
        return Resource(
            id=pool.get("id", ""),
            name=pool.get("name", "") or pool.get("id", ""),
            resource_type=ResourceType.CONTAINER,
            provider="digitalocean",
            region=region,
            state=ResourceState.RUNNING,
            tags={},
            metadata={
                "cluster_id": cluster_id,
                "size": pool.get("size", ""),
                "count": str(pool.get("count", "")),
                "auto_scale": str(pool.get("auto_scale", False)),
                "min_nodes": str(pool.get("min_nodes", "")),
                "max_nodes": str(pool.get("max_nodes", "")),
                "resource_subtype": "doks_node_pool",
            },
        )
