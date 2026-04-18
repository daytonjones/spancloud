"""Azure Load Balancer resource discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.providers.azure.compute import _parse_resource_group
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.azure.auth import AzureAuth

logger = get_logger(__name__)


class LoadBalancerResources:
    """Handles Azure Load Balancer discovery."""

    def __init__(self, auth: AzureAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_load_balancers(self, region: str | None = None) -> list[Resource]:
        """List all load balancers in the subscription."""
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d Azure Load Balancers", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        from azure.mgmt.network import NetworkManagementClient

        credential = self._auth.get_credential()
        client = NetworkManagementClient(credential, self._auth.subscription_id)

        resources: list[Resource] = []
        for lb in client.load_balancers.list_all():
            if region and lb.location != region:
                continue
            resources.append(self._map_lb(lb))
        return resources

    def _map_lb(self, lb: Any) -> Resource:
        sku = getattr(lb, "sku", None)
        frontends = getattr(lb, "frontend_ip_configurations", []) or []
        backends = getattr(lb, "backend_address_pools", []) or []
        rules = getattr(lb, "load_balancing_rules", []) or []

        return Resource(
            id=lb.id or lb.name,
            name=lb.name,
            resource_type=ResourceType.LOAD_BALANCER,
            provider="azure",
            region=lb.location,
            state=ResourceState.RUNNING,
            tags=dict(lb.tags or {}),
            metadata={
                "sku": str(getattr(sku, "name", "") or ""),
                "tier": str(getattr(sku, "tier", "") or ""),
                "frontend_count": str(len(frontends)),
                "backend_pool_count": str(len(backends)),
                "rule_count": str(len(rules)),
                "resource_group": _parse_resource_group(lb.id or ""),
                "resource_subtype": "load_balancer",
            },
        )
