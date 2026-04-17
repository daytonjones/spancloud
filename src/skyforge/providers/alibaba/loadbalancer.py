"""Alibaba Server Load Balancer (SLB / CLB) discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.alibaba.auth import AlibabaAuth

logger = get_logger(__name__)


class SLBResources:
    """Handles Alibaba SLB (Classic Load Balancer) discovery."""

    def __init__(self, auth: AlibabaAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_load_balancers(
        self, region: str | None = None
    ) -> list[Resource]:
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d Alibaba SLBs", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        from alibabacloud_slb20140515 import models as slb_models
        from alibabacloud_slb20140515.client import Client as SlbClient

        region_id = region or self._auth.region
        client = SlbClient(self._auth.slb_config(region_id))

        try:
            response = client.describe_load_balancers(
                slb_models.DescribeLoadBalancersRequest(region_id=region_id)
            )
        except Exception as exc:
            logger.debug("SLB list failed: %s", exc)
            return []

        body = response.body
        holder = getattr(body, "load_balancers", None)
        lb_list = (
            getattr(holder, "load_balancer", []) or [] if holder else []
        )

        resources: list[Resource] = []
        for lb in lb_list:
            resources.append(self._map_lb(lb, region_id))
        return resources

    def _map_lb(self, lb: Any, region: str) -> Resource:
        status = str(getattr(lb, "load_balancer_status", "") or "")
        state = (
            ResourceState.RUNNING
            if status == "active"
            else ResourceState.STOPPED
            if status == "inactive"
            else ResourceState.UNKNOWN
        )
        return Resource(
            id=getattr(lb, "load_balancer_id", "") or "",
            name=getattr(lb, "load_balancer_name", "")
            or getattr(lb, "load_balancer_id", ""),
            resource_type=ResourceType.LOAD_BALANCER,
            provider="alibaba",
            region=region,
            state=state,
            metadata={
                "address": getattr(lb, "address", "") or "",
                "address_type": getattr(lb, "address_type", "") or "",
                "network_type": getattr(lb, "network_type", "") or "",
                "vpc_id": getattr(lb, "vpc_id", "") or "",
                "vswitch_id": getattr(lb, "v_switch_id", "") or "",
                "load_balancer_spec": getattr(lb, "load_balancer_spec", "") or "",
                "resource_subtype": "slb",
            },
        )
