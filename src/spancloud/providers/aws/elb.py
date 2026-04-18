"""AWS Elastic Load Balancer resource discovery (ALB, NLB, Classic)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.aws.auth import AWSAuth

logger = get_logger(__name__)

_ELB_STATE_MAP: dict[str, ResourceState] = {
    "active": ResourceState.RUNNING,
    "provisioning": ResourceState.PENDING,
    "active_impaired": ResourceState.ERROR,
    "failed": ResourceState.ERROR,
}


class ELBResources:
    """Handles ELBv2 (ALB/NLB) and Classic load balancer discovery."""

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_load_balancers(self, region: str | None = None) -> list[Resource]:
        """List all load balancers (ALB, NLB, and Classic) in the given region.

        Args:
            region: AWS region.

        Returns:
            List of Resource objects representing load balancers.
        """
        v2_resources = await self._list_v2(region)
        classic_resources = await self._list_classic(region)
        all_resources = v2_resources + classic_resources

        logger.debug(
            "Found %d load balancers in %s (%d v2, %d classic)",
            len(all_resources),
            region or "default region",
            len(v2_resources),
            len(classic_resources),
        )
        return all_resources

    async def _list_v2(self, region: str | None = None) -> list[Resource]:
        """List ALB and NLB load balancers (ELBv2 API)."""
        client = self._auth.client("elbv2", region=region)
        paginator = client.get_paginator("describe_load_balancers")

        pages = await asyncio.to_thread(lambda: list(paginator.paginate()))

        resources: list[Resource] = []
        for page in pages:
            for lb in page.get("LoadBalancers", []):
                resources.append(self._map_v2(lb, region or ""))

        return resources

    async def _list_classic(self, region: str | None = None) -> list[Resource]:
        """List Classic load balancers (ELB API)."""
        client = self._auth.client("elb", region=region)
        try:
            response = await asyncio.to_thread(client.describe_load_balancers)
        except Exception as exc:
            logger.debug("Classic ELB listing failed (may not be in use): %s", exc)
            return []

        resources: list[Resource] = []
        for lb in response.get("LoadBalancerDescriptions", []):
            resources.append(self._map_classic(lb, region or ""))

        return resources

    def _map_v2(self, lb: dict[str, Any], region: str) -> Resource:
        """Map an ELBv2 load balancer to a unified Resource."""
        state_code = lb.get("State", {}).get("Code", "unknown")
        lb_type = lb.get("Type", "application")
        azs = [az.get("ZoneName", "") for az in lb.get("AvailabilityZones", [])]

        return Resource(
            id=lb.get("LoadBalancerName", lb.get("LoadBalancerArn", "")),
            name=lb.get("LoadBalancerName", ""),
            resource_type=ResourceType.LOAD_BALANCER,
            provider="aws",
            region=region,
            state=_ELB_STATE_MAP.get(state_code, ResourceState.UNKNOWN),
            created_at=lb.get("CreatedTime"),
            metadata={
                "type": lb_type,
                "scheme": lb.get("Scheme", ""),
                "dns_name": lb.get("DNSName", ""),
                "vpc_id": lb.get("VpcId", ""),
                "availability_zones": ", ".join(azs),
                "ip_address_type": lb.get("IpAddressType", ""),
                "resource_subtype": f"elbv2_{lb_type}",
            },
        )

    def _map_classic(self, lb: dict[str, Any], region: str) -> Resource:
        """Map a Classic load balancer to a unified Resource."""
        azs = lb.get("AvailabilityZones", [])
        listeners = lb.get("ListenerDescriptions", [])

        return Resource(
            id=lb["LoadBalancerName"],
            name=lb["LoadBalancerName"],
            resource_type=ResourceType.LOAD_BALANCER,
            provider="aws",
            region=region,
            state=ResourceState.RUNNING,
            created_at=lb.get("CreatedTime"),
            metadata={
                "type": "classic",
                "scheme": lb.get("Scheme", ""),
                "dns_name": lb.get("DNSName", ""),
                "vpc_id": lb.get("VPCId", ""),
                "availability_zones": ", ".join(azs),
                "listener_count": str(len(listeners)),
                "resource_subtype": "elb_classic",
            },
        )
