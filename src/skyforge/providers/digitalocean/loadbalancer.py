"""DigitalOcean load balancer resource discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.digitalocean.auth import DigitalOceanAuth

logger = get_logger(__name__)

_LB_STATE_MAP: dict[str, ResourceState] = {
    "active": ResourceState.RUNNING,
    "new": ResourceState.PENDING,
    "errored": ResourceState.ERROR,
}


class LoadBalancerResources:
    """Handles DO load balancer discovery."""

    def __init__(self, auth: DigitalOceanAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_load_balancers(
        self, region: str | None = None
    ) -> list[Resource]:
        """List all load balancers."""
        raw = await self._auth.get_paginated("/load_balancers", "load_balancers")

        resources: list[Resource] = []
        for lb in raw:
            lb_region = (lb.get("region") or {}).get("slug", "")
            if region and lb_region != region:
                continue
            resources.append(self._map_lb(lb))

        logger.debug("Found %d DO load balancers", len(resources))
        return resources

    def _map_lb(self, lb: dict[str, Any]) -> Resource:
        status = lb.get("status", "")
        region = lb.get("region") or {}
        forwarding = lb.get("forwarding_rules") or []
        health = lb.get("health_check") or {}
        droplet_ids = lb.get("droplet_ids") or []

        return Resource(
            id=lb.get("id", ""),
            name=lb.get("name", "") or lb.get("id", ""),
            resource_type=ResourceType.LOAD_BALANCER,
            provider="digitalocean",
            region=region.get("slug", ""),
            state=_LB_STATE_MAP.get(status, ResourceState.UNKNOWN),
            created_at=lb.get("created_at"),
            metadata={
                "ip": lb.get("ip", ""),
                "algorithm": lb.get("algorithm", ""),
                "size": lb.get("size_unit") or lb.get("size", ""),
                "forwarding_rules": str(len(forwarding)),
                "droplet_count": str(len(droplet_ids)),
                "health_check_protocol": health.get("protocol", ""),
                "health_check_port": str(health.get("port", "")),
                "redirect_http_to_https": str(
                    lb.get("redirect_http_to_https", False)
                ),
                "resource_subtype": "load_balancer",
            },
        )
