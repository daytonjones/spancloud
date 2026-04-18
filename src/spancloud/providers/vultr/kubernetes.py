"""Vultr Kubernetes Engine (VKE) resource discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.vultr.auth import VultrAuth

logger = get_logger(__name__)

_VKE_STATE_MAP: dict[str, ResourceState] = {
    "active": ResourceState.RUNNING,
    "pending": ResourceState.PENDING,
    "deleted": ResourceState.TERMINATED,
}


class KubernetesResources:
    """Handles Vultr Kubernetes Engine (VKE) cluster discovery."""

    def __init__(self, auth: VultrAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_clusters(self, region: str | None = None) -> list[Resource]:
        """List all VKE clusters.

        Args:
            region: Optional region filter.

        Returns:
            List of Resource objects (clusters + node pools).
        """
        raw = await self._auth.get_paginated(
            "/kubernetes/clusters", "vke_clusters"
        )

        resources: list[Resource] = []
        for cluster in raw:
            cluster_region = cluster.get("region", "")
            if region and cluster_region != region:
                continue
            resources.append(self._map_cluster(cluster))

            # Also map node pools
            for pool in cluster.get("node_pools", []):
                resources.append(
                    self._map_node_pool(pool, cluster.get("id", ""), cluster_region)
                )

        logger.debug("Found %d VKE resources", len(resources))
        return resources

    def _map_cluster(self, cluster: dict[str, Any]) -> Resource:
        """Map a VKE cluster to a unified Resource."""
        status = cluster.get("status", "")

        return Resource(
            id=cluster.get("id", ""),
            name=cluster.get("label", "") or cluster.get("id", ""),
            resource_type=ResourceType.CONTAINER,
            provider="vultr",
            region=cluster.get("region", ""),
            state=_VKE_STATE_MAP.get(status, ResourceState.UNKNOWN),
            created_at=cluster.get("date_created"),
            tags={},
            metadata={
                "version": cluster.get("version", ""),
                "ip": cluster.get("ip", ""),
                "endpoint": cluster.get("endpoint", ""),
                "node_pool_count": str(len(cluster.get("node_pools", []))),
                "ha_controlplanes": str(cluster.get("ha_controlplanes", False)),
                "firewall_group_id": cluster.get("firewall_group_id", ""),
                "resource_subtype": "vke_cluster",
            },
        )

    def _map_node_pool(
        self, pool: dict[str, Any], cluster_id: str, region: str
    ) -> Resource:
        """Map a VKE node pool to a unified Resource."""
        status = pool.get("status", "")

        return Resource(
            id=pool.get("id", ""),
            name=pool.get("label", "") or pool.get("id", ""),
            resource_type=ResourceType.CONTAINER,
            provider="vultr",
            region=region,
            state=_VKE_STATE_MAP.get(status, ResourceState.UNKNOWN),
            created_at=pool.get("date_created"),
            tags={},
            metadata={
                "cluster_id": cluster_id,
                "plan": pool.get("plan", ""),
                "node_quantity": str(pool.get("node_quantity", "")),
                "min_nodes": str(pool.get("min_nodes", "")),
                "max_nodes": str(pool.get("max_nodes", "")),
                "auto_scaler": str(pool.get("auto_scaler", False)),
                "resource_subtype": "vke_node_pool",
            },
        )
