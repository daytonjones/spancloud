"""Alibaba Cloud ECS (Elastic Compute Service) discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.alibaba.auth import AlibabaAuth

logger = get_logger(__name__)

_INSTANCE_STATE_MAP: dict[str, ResourceState] = {
    "Running": ResourceState.RUNNING,
    "Stopped": ResourceState.STOPPED,
    "Starting": ResourceState.PENDING,
    "Stopping": ResourceState.PENDING,
    "Pending": ResourceState.PENDING,
}


class ECSResources:
    """Handles Alibaba ECS instance discovery."""

    def __init__(self, auth: AlibabaAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_instances(self, region: str | None = None) -> list[Resource]:
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d Alibaba ECS instances", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        from alibabacloud_ecs20140526 import models as ecs_models
        from alibabacloud_ecs20140526.client import Client as EcsClient

        region_id = region or self._auth.region
        client = EcsClient(self._auth.ecs_config(region_id))

        resources: list[Resource] = []
        page_number = 1
        while True:
            req = ecs_models.DescribeInstancesRequest(
                region_id=region_id,
                page_number=page_number,
                page_size=100,
            )
            response = client.describe_instances(req)
            body = response.body
            instances_holder = getattr(body, "instances", None)
            instance_list = (
                getattr(instances_holder, "instance", []) or [] if instances_holder else []
            )
            if not instance_list:
                break

            for inst in instance_list:
                resources.append(self._map_instance(inst, region_id))

            total = getattr(body, "total_count", 0) or 0
            if page_number * 100 >= total:
                break
            page_number += 1
        return resources

    def _map_instance(self, inst: Any, region: str) -> Resource:
        status = str(getattr(inst, "status", "") or "")
        tags_holder = getattr(inst, "tags", None)
        tag_list = getattr(tags_holder, "tag", []) or [] if tags_holder else []
        tags = {
            str(getattr(t, "tag_key", "")): str(getattr(t, "tag_value", ""))
            for t in tag_list
            if getattr(t, "tag_key", None)
        }

        public_ip_holder = getattr(inst, "public_ip_address", None)
        public_ips = (
            getattr(public_ip_holder, "ip_address", []) or []
            if public_ip_holder
            else []
        )
        private_ip_holder = getattr(inst, "vpc_attributes", None)
        private_ips: list[str] = []
        if private_ip_holder:
            private_holder = getattr(
                private_ip_holder, "private_ip_address", None
            )
            private_ips = (
                getattr(private_holder, "ip_address", []) or []
                if private_holder
                else []
            )

        return Resource(
            id=getattr(inst, "instance_id", "") or "",
            name=getattr(inst, "instance_name", "") or getattr(inst, "instance_id", ""),
            resource_type=ResourceType.COMPUTE,
            provider="alibaba",
            region=region,
            state=_INSTANCE_STATE_MAP.get(status, ResourceState.UNKNOWN),
            tags=tags,
            metadata={
                "instance_type": getattr(inst, "instance_type", "") or "",
                "os_name": getattr(inst, "osname", "") or "",
                "image_id": getattr(inst, "image_id", "") or "",
                "vpc_id": (
                    getattr(private_ip_holder, "vpc_id", "") or ""
                    if private_ip_holder
                    else ""
                ),
                "public_ip": public_ips[0] if public_ips else "",
                "private_ip": private_ips[0] if private_ips else "",
                "zone_id": getattr(inst, "zone_id", "") or "",
                "resource_subtype": "ecs_instance",
            },
        )
