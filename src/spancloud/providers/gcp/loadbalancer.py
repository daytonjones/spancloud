"""GCP Cloud Load Balancing resource discovery.

GCP load balancers are composed of multiple resources (forwarding rules, target proxies,
URL maps, backend services). We surface forwarding rules as the primary load balancer
resource since they represent the entry point, with backend service details in metadata.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from google.cloud import compute_v1

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.providers.gcp._retry import GCP_RETRY

if TYPE_CHECKING:
    from spancloud.providers.gcp.auth import GCPAuth

logger = get_logger(__name__)


class LoadBalancerResources:
    """Handles GCP load balancer discovery via forwarding rules."""

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    @GCP_RETRY
    async def list_load_balancers(self, region: str | None = None) -> list[Resource]:
        """List all load balancers (forwarding rules) in the project.

        Combines global and regional forwarding rules for a complete view.

        Args:
            region: Optional region to filter by. Global rules are always included.

        Returns:
            List of Resource objects representing load balancers.
        """
        global_rules = await self._list_global_forwarding_rules()
        regional_rules = await self._list_regional_forwarding_rules(region)

        all_rules = global_rules + regional_rules
        logger.debug(
            "Found %d load balancers (%d global, %d regional)",
            len(all_rules),
            len(global_rules),
            len(regional_rules),
        )
        return all_rules

    async def _list_global_forwarding_rules(self) -> list[Resource]:
        """List global forwarding rules (external HTTP(S), SSL proxy, TCP proxy)."""
        project = self._auth.project_id
        if not project:
            return []

        client = compute_v1.GlobalForwardingRulesClient(credentials=self._auth.credentials)

        def _fetch() -> list[Any]:
            return list(client.list(project=project))

        rules = await asyncio.to_thread(_fetch)
        return [self._map_forwarding_rule(rule, "global") for rule in rules]

    async def _list_regional_forwarding_rules(self, region: str | None = None) -> list[Resource]:
        """List regional forwarding rules (internal, network LB, etc.)."""
        project = self._auth.project_id
        if not project:
            return []

        client = compute_v1.ForwardingRulesClient(credentials=self._auth.credentials)

        def _fetch() -> list[dict[str, Any]]:
            rules: list[dict[str, Any]] = []
            request = compute_v1.AggregatedListForwardingRulesRequest(project=project)
            for region_key, scoped_list in client.aggregated_list(request=request):
                if scoped_list.forwarding_rules:
                    for rule in scoped_list.forwarding_rules:
                        region_name = region_key.split("/")[-1] if "/" in region_key else region_key
                        if region and region != region_name:
                            continue
                        rules.append({"rule": rule, "region": region_name})
            return rules

        raw_rules = await asyncio.to_thread(_fetch)
        return [
            self._map_forwarding_rule(item["rule"], item["region"])
            for item in raw_rules
        ]

    def _map_forwarding_rule(self, rule: Any, region: str) -> Resource:
        """Map a GCP forwarding rule to a unified Resource."""
        # Extract target name from full URL
        target = (rule.target or "").rsplit("/", 1)[-1]
        backend_svc = rule.backend_service or ""
        backend_service = backend_svc.rsplit("/", 1)[-1] if backend_svc else ""

        # Determine the LB type from load_balancing_scheme
        scheme = rule.load_balancing_scheme or ""
        lb_type = self._classify_lb_type(scheme, rule)

        # Port info
        ports = list(rule.ports) if rule.ports else []
        port_range = rule.port_range or ""

        return Resource(
            id=str(rule.id) if rule.id else rule.name or "",
            name=rule.name or "",
            resource_type=ResourceType.LOAD_BALANCER,
            provider="gcp",
            region=region,
            state=ResourceState.RUNNING,
            created_at=None,
            tags=dict(rule.labels) if rule.labels else {},
            metadata={
                "ip_address": (
                    rule.I_p_address
                    if hasattr(rule, "I_p_address")
                    else (rule.ip_address or "")
                ),
                "ip_protocol": (
                    rule.I_p_protocol
                    if hasattr(rule, "I_p_protocol")
                    else (rule.ip_protocol or "")
                ),
                "port_range": port_range,
                "ports": ", ".join(ports[:5]),
                "target": target,
                "backend_service": backend_service,
                "load_balancing_scheme": scheme,
                "lb_type": lb_type,
                "network_tier": rule.network_tier or "",
                "resource_subtype": "forwarding_rule",
            },
        )

    def _classify_lb_type(self, scheme: str, rule: Any) -> str:
        """Classify the load balancer type from the forwarding rule properties."""
        target = rule.target or ""

        if "EXTERNAL" in scheme:
            if "targetHttpProxies" in target or "targetHttpsProxies" in target:
                return "external_http"
            if "targetSslProxies" in target:
                return "external_ssl_proxy"
            if "targetTcpProxies" in target:
                return "external_tcp_proxy"
            return "external_network"
        if "INTERNAL" in scheme:
            if "targetHttpProxies" in target or "targetHttpsProxies" in target:
                return "internal_http"
            return "internal_tcp_udp"

        return "unknown"
