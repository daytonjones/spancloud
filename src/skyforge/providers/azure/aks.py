"""Azure Kubernetes Service (AKS) resource discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.providers.azure.compute import _parse_resource_group
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.azure.auth import AzureAuth

logger = get_logger(__name__)


class AKSResources:
    """Handles AKS cluster discovery."""

    def __init__(self, auth: AzureAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_clusters(self, region: str | None = None) -> list[Resource]:
        """List all AKS clusters in the subscription."""
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d Azure AKS clusters", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        from azure.mgmt.containerservice import ContainerServiceClient

        credential = self._auth.get_credential()
        client = ContainerServiceClient(credential, self._auth.subscription_id)

        resources: list[Resource] = []
        for cluster in client.managed_clusters.list():
            if region and cluster.location != region:
                continue
            resources.append(self._map_cluster(cluster))
        return resources

    def _map_cluster(self, cluster: Any) -> Resource:
        provisioning = str(getattr(cluster, "provisioning_state", "") or "")
        power = getattr(cluster, "power_state", None)
        power_code = str(getattr(power, "code", "") or "")
        node_pools = getattr(cluster, "agent_pool_profiles", []) or []
        total_nodes = sum(getattr(p, "count", 0) or 0 for p in node_pools)

        state = (
            ResourceState.RUNNING
            if power_code == "Running" or provisioning.endswith("Succeeded")
            else ResourceState.STOPPED
            if power_code == "Stopped"
            else ResourceState.PENDING
        )

        return Resource(
            id=cluster.id or cluster.name,
            name=cluster.name,
            resource_type=ResourceType.CONTAINER,
            provider="azure",
            region=cluster.location,
            state=state,
            tags=dict(cluster.tags or {}),
            metadata={
                "kubernetes_version": getattr(cluster, "kubernetes_version", "")
                or "",
                "node_pool_count": str(len(node_pools)),
                "node_count": str(total_nodes),
                "dns_prefix": getattr(cluster, "dns_prefix", "") or "",
                "fqdn": getattr(cluster, "fqdn", "") or "",
                "power_state": power_code,
                "provisioning_state": provisioning,
                "resource_group": _parse_resource_group(cluster.id or ""),
                "resource_subtype": "aks_cluster",
            },
        )
