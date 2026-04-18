"""Alibaba relationship mapper — instance → VSwitch/VPC/SG, disk → instance."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from spancloud.analysis.models import (
    RelationshipMap,
    RelationshipType,
    ResourceRelationship,
)
from spancloud.utils.logging import get_logger

if TYPE_CHECKING:
    from spancloud.providers.alibaba.auth import AlibabaAuth

logger = get_logger(__name__)


class AlibabaRelationshipMapper:
    """Builds a relationship graph for Alibaba resources."""

    def __init__(self, auth: AlibabaAuth) -> None:
        self._auth = auth

    async def map_relationships(
        self, region: str | None = None
    ) -> RelationshipMap:
        results = await asyncio.gather(
            asyncio.to_thread(self._instance_to_network, region),
            asyncio.to_thread(self._disk_to_instance, region),
        )
        rels: list[ResourceRelationship] = []
        for group in results:
            rels.extend(group)
        return RelationshipMap(provider="alibaba", relationships=rels)

    def _instance_to_network(
        self, region: str | None
    ) -> list[ResourceRelationship]:
        from alibabacloud_ecs20140526 import models as ecs_models
        from alibabacloud_ecs20140526.client import Client as EcsClient

        rels: list[ResourceRelationship] = []
        region_id = region or self._auth.region
        try:
            client = EcsClient(self._auth.ecs_config(region_id))
            page = 1
            while True:
                req = ecs_models.DescribeInstancesRequest(
                    region_id=region_id,
                    page_number=page,
                    page_size=100,
                )
                response = client.describe_instances(req)
                body = response.body
                holder = getattr(body, "instances", None)
                insts = getattr(holder, "instance", []) or [] if holder else []
                if not insts:
                    break
                for inst in insts:
                    inst_id = getattr(inst, "instance_id", "") or ""
                    inst_name = getattr(inst, "instance_name", "") or inst_id

                    vpc_attrs = getattr(inst, "vpc_attributes", None)
                    vpc_id = getattr(vpc_attrs, "vpc_id", "") if vpc_attrs else ""
                    vswitch_id = (
                        getattr(vpc_attrs, "v_switch_id", "") if vpc_attrs else ""
                    )
                    if vswitch_id:
                        rels.append(
                            ResourceRelationship(
                                source_id=inst_id,
                                source_type="ecs_instance",
                                source_name=inst_name,
                                target_id=vswitch_id,
                                target_type="vswitch",
                                target_name=vswitch_id,
                                relationship=RelationshipType.IN_SUBNET,
                                provider="alibaba",
                                region=region_id,
                            )
                        )
                    if vpc_id:
                        rels.append(
                            ResourceRelationship(
                                source_id=inst_id,
                                source_type="ecs_instance",
                                source_name=inst_name,
                                target_id=vpc_id,
                                target_type="vpc",
                                target_name=vpc_id,
                                relationship=RelationshipType.IN_VPC,
                                provider="alibaba",
                                region=region_id,
                            )
                        )

                    sg_holder = getattr(inst, "security_group_ids", None)
                    sg_ids = (
                        getattr(sg_holder, "security_group_id", []) or []
                        if sg_holder
                        else []
                    )
                    for sg_id in sg_ids:
                        rels.append(
                            ResourceRelationship(
                                source_id=inst_id,
                                source_type="ecs_instance",
                                source_name=inst_name,
                                target_id=sg_id,
                                target_type="security_group",
                                target_name=sg_id,
                                relationship=RelationshipType.SECURED_BY,
                                provider="alibaba",
                                region=region_id,
                            )
                        )

                total = getattr(body, "total_count", 0) or 0
                if page * 100 >= total:
                    break
                page += 1
        except Exception as exc:
            logger.debug("ECS relationship scan skipped: %s", exc)
        return rels

    def _disk_to_instance(
        self, region: str | None
    ) -> list[ResourceRelationship]:
        from alibabacloud_ecs20140526 import models as ecs_models
        from alibabacloud_ecs20140526.client import Client as EcsClient

        rels: list[ResourceRelationship] = []
        region_id = region or self._auth.region
        try:
            client = EcsClient(self._auth.ecs_config(region_id))
            page = 1
            while True:
                req = ecs_models.DescribeDisksRequest(
                    region_id=region_id,
                    page_number=page,
                    page_size=100,
                )
                response = client.describe_disks(req)
                body = response.body
                holder = getattr(body, "disks", None)
                disks = getattr(holder, "disk", []) or [] if holder else []
                if not disks:
                    break
                for d in disks:
                    inst_id = getattr(d, "instance_id", "") or ""
                    if not inst_id:
                        continue
                    disk_id = getattr(d, "disk_id", "") or ""
                    rels.append(
                        ResourceRelationship(
                            source_id=disk_id,
                            source_type="ecs_disk",
                            source_name=(
                                getattr(d, "disk_name", "") or disk_id
                            ),
                            target_id=inst_id,
                            target_type="ecs_instance",
                            target_name=inst_id,
                            relationship=RelationshipType.ATTACHED_TO,
                            provider="alibaba",
                            region=region_id,
                        )
                    )
                total = getattr(body, "total_count", 0) or 0
                if page * 100 >= total:
                    break
                page += 1
        except Exception as exc:
            logger.debug("Disk attachment scan skipped: %s", exc)
        return rels
