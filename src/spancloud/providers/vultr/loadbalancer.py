"""Vultr load balancer resource discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.vultr.auth import VultrAuth

logger = get_logger(__name__)


class LoadBalancerResources:
    """Handles Vultr load balancer discovery."""

    def __init__(self, auth: VultrAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_load_balancers(
        self, region: str | None = None
    ) -> list[Resource]:
        """List all load balancers.

        Args:
            region: Optional region filter.

        Returns:
            List of Resource objects representing load balancers.
        """
        raw = await self._auth.get_paginated("/load-balancers", "load_balancers")

        resources: list[Resource] = []
        for lb in raw:
            lb_region = lb.get("region", "")
            if region and lb_region != region:
                continue
            resources.append(self._map_lb(lb))

        logger.debug("Found %d Vultr load balancers", len(resources))
        return resources

    def _map_lb(self, lb: dict[str, Any]) -> Resource:
        """Map a Vultr load balancer to a unified Resource."""
        status = lb.get("status", "")
        instances = lb.get("instances", [])

        # Forwarding rules summary
        rules = lb.get("forwarding_rules", [])
        rule_summary = ", ".join(
            f"{r.get('frontend_port', '')}→{r.get('backend_port', '')}"
            for r in rules[:3]
        )

        health = lb.get("health_check", {})

        return Resource(
            id=lb.get("id", ""),
            name=lb.get("label", "") or lb.get("id", ""),
            resource_type=ResourceType.LOAD_BALANCER,
            provider="vultr",
            region=lb.get("region", ""),
            state=ResourceState.RUNNING if status == "active" else ResourceState.PENDING,
            created_at=lb.get("date_created"),
            tags={},
            metadata={
                "ipv4": lb.get("ipv4", ""),
                "ipv6": lb.get("ipv6", ""),
                "instance_count": str(len(instances)),
                "forwarding_rules": rule_summary,
                "health_check_protocol": health.get("protocol", ""),
                "health_check_port": str(health.get("port", "")),
                "ssl_redirect": str(lb.get("ssl_redirect", False)),
                "resource_subtype": "load_balancer",
            },
        )
