"""Alibaba Cloud VPC + VSwitch + Security Group discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.alibaba.auth import AlibabaAuth

logger = get_logger(__name__)


class NetworkResources:
    """Handles Alibaba VPC / VSwitch / Security Group discovery."""

    def __init__(self, auth: AlibabaAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_all(self, region: str | None = None) -> list[Resource]:
        vpcs, vswitches, sgs = await asyncio.gather(
            asyncio.to_thread(self._sync_list_vpcs, region),
            asyncio.to_thread(self._sync_list_vswitches, region),
            asyncio.to_thread(self._sync_list_security_groups, region),
        )
        combined = vpcs + vswitches + sgs
        logger.debug("Found %d Alibaba network resources", len(combined))
        return combined

    def _sync_list_vpcs(self, region: str | None) -> list[Resource]:
        from alibabacloud_vpc20160428 import models as vpc_models
        from alibabacloud_vpc20160428.client import Client as VpcClient

        region_id = region or self._auth.region
        client = VpcClient(self._auth.vpc_config(region_id))

        resources: list[Resource] = []
        page_number = 1
        while True:
            req = vpc_models.DescribeVpcsRequest(
                region_id=region_id,
                page_number=page_number,
                page_size=50,
            )
            response = client.describe_vpcs(req)
            body = response.body
            vpcs_holder = getattr(body, "vpcs", None)
            vpc_list = getattr(vpcs_holder, "vpc", []) or [] if vpcs_holder else []
            if not vpc_list:
                break
            for v in vpc_list:
                resources.append(self._map_vpc(v, region_id))
            total = getattr(body, "total_count", 0) or 0
            if page_number * 50 >= total:
                break
            page_number += 1
        return resources

    def _map_vpc(self, v: Any, region: str) -> Resource:
        return Resource(
            id=getattr(v, "vpc_id", "") or "",
            name=getattr(v, "vpc_name", "") or getattr(v, "vpc_id", ""),
            resource_type=ResourceType.NETWORK,
            provider="alibaba",
            region=region,
            state=ResourceState.RUNNING,
            metadata={
                "cidr_block": getattr(v, "cidr_block", "") or "",
                "is_default": str(getattr(v, "is_default", "") or ""),
                "resource_subtype": "vpc",
            },
        )

    def _sync_list_vswitches(self, region: str | None) -> list[Resource]:
        from alibabacloud_vpc20160428 import models as vpc_models
        from alibabacloud_vpc20160428.client import Client as VpcClient

        region_id = region or self._auth.region
        client = VpcClient(self._auth.vpc_config(region_id))

        resources: list[Resource] = []
        page_number = 1
        while True:
            req = vpc_models.DescribeVSwitchesRequest(
                region_id=region_id,
                page_number=page_number,
                page_size=50,
            )
            response = client.describe_vswitches(req)
            body = response.body
            holder = getattr(body, "v_switches", None)
            sw_list = getattr(holder, "v_switch", []) or [] if holder else []
            if not sw_list:
                break
            for s in sw_list:
                resources.append(self._map_vswitch(s, region_id))
            total = getattr(body, "total_count", 0) or 0
            if page_number * 50 >= total:
                break
            page_number += 1
        return resources

    def _map_vswitch(self, s: Any, region: str) -> Resource:
        return Resource(
            id=getattr(s, "v_switch_id", "") or "",
            name=getattr(s, "v_switch_name", "") or getattr(s, "v_switch_id", ""),
            resource_type=ResourceType.NETWORK,
            provider="alibaba",
            region=region,
            state=ResourceState.RUNNING,
            metadata={
                "cidr": getattr(s, "cidr_block", "") or "",
                "vpc_id": getattr(s, "vpc_id", "") or "",
                "zone_id": getattr(s, "zone_id", "") or "",
                "resource_subtype": "vswitch",
            },
        )

    def _sync_list_security_groups(self, region: str | None) -> list[Resource]:
        from alibabacloud_ecs20140526 import models as ecs_models
        from alibabacloud_ecs20140526.client import Client as EcsClient

        region_id = region or self._auth.region
        client = EcsClient(self._auth.ecs_config(region_id))

        resources: list[Resource] = []
        page_number = 1
        while True:
            req = ecs_models.DescribeSecurityGroupsRequest(
                region_id=region_id,
                page_number=page_number,
                page_size=50,
            )
            response = client.describe_security_groups(req)
            body = response.body
            holder = getattr(body, "security_groups", None)
            sg_list = (
                getattr(holder, "security_group", []) or [] if holder else []
            )
            if not sg_list:
                break
            for sg in sg_list:
                resources.append(self._map_sg(sg, region_id))
            total = getattr(body, "total_count", 0) or 0
            if page_number * 50 >= total:
                break
            page_number += 1
        return resources

    def _map_sg(self, sg: Any, region: str) -> Resource:
        return Resource(
            id=getattr(sg, "security_group_id", "") or "",
            name=getattr(sg, "security_group_name", "")
            or getattr(sg, "security_group_id", ""),
            resource_type=ResourceType.NETWORK,
            provider="alibaba",
            region=region,
            state=ResourceState.RUNNING,
            metadata={
                "vpc_id": getattr(sg, "vpc_id", "") or "",
                "security_group_type": getattr(sg, "security_group_type", "") or "",
                "resource_subtype": "security_group",
            },
        )
