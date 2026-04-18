"""Alibaba unused-resource detection."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from skyforge.analysis.models import UnusedResource, UnusedResourceReport
from skyforge.utils.logging import get_logger

if TYPE_CHECKING:
    from skyforge.providers.alibaba.auth import AlibabaAuth

logger = get_logger(__name__)


class AlibabaUnusedDetector:
    """Finds idle or unused Alibaba resources."""

    def __init__(self, auth: AlibabaAuth) -> None:
        self._auth = auth

    async def scan(
        self,
        region: str | None = None,
        stopped_days_threshold: int = 30,
        snapshot_days_threshold: int = 30,
    ) -> UnusedResourceReport:
        _ = stopped_days_threshold, snapshot_days_threshold
        results = await asyncio.gather(
            asyncio.to_thread(self._find_unattached_disks, region),
            asyncio.to_thread(self._find_stopped_instances, region),
        )
        unused: list[UnusedResource] = []
        for group in results:
            unused.extend(group)
        return UnusedResourceReport(provider="alibaba", resources=unused)

    def _find_unattached_disks(
        self, region: str | None
    ) -> list[UnusedResource]:
        """Disks with status 'Available' aren't attached."""
        from alibabacloud_ecs20140526 import models as ecs_models
        from alibabacloud_ecs20140526.client import Client as EcsClient

        out: list[UnusedResource] = []
        region_id = region or self._auth.region
        try:
            client = EcsClient(self._auth.ecs_config(region_id))
            page = 1
            while True:
                req = ecs_models.DescribeDisksRequest(
                    region_id=region_id,
                    status="Available",
                    page_number=page,
                    page_size=100,
                )
                response = client.describe_disks(req)
                body = response.body
                disks_holder = getattr(body, "disks", None)
                disks = (
                    getattr(disks_holder, "disk", []) or []
                    if disks_holder
                    else []
                )
                if not disks:
                    break
                for d in disks:
                    size_gb = getattr(d, "size", 0) or 0
                    # Alibaba cloud SSD/ESSD pricing varies — use ~$0.08/GB/mo as rough
                    est = f"~${size_gb * 0.08:,.2f}/mo"
                    out.append(
                        UnusedResource(
                            resource_id=getattr(d, "disk_id", ""),
                            resource_name=(
                                getattr(d, "disk_name", "")
                                or getattr(d, "disk_id", "")
                            ),
                            resource_type="ecs_disk",
                            provider="alibaba",
                            region=region_id,
                            reason=f"Unattached disk ({size_gb} GB)",
                            estimated_monthly_savings=est,
                        )
                    )
                total = getattr(body, "total_count", 0) or 0
                if page * 100 >= total:
                    break
                page += 1
        except Exception as exc:
            logger.debug("Disk scan skipped: %s", exc)
        return out

    def _find_stopped_instances(
        self, region: str | None
    ) -> list[UnusedResource]:
        """Stopped ECS instances — disks still incur storage cost."""
        from alibabacloud_ecs20140526 import models as ecs_models
        from alibabacloud_ecs20140526.client import Client as EcsClient

        out: list[UnusedResource] = []
        region_id = region or self._auth.region
        try:
            client = EcsClient(self._auth.ecs_config(region_id))
            page = 1
            while True:
                req = ecs_models.DescribeInstancesRequest(
                    region_id=region_id,
                    status="Stopped",
                    page_number=page,
                    page_size=100,
                )
                response = client.describe_instances(req)
                body = response.body
                holder = getattr(body, "instances", None)
                inst_list = (
                    getattr(holder, "instance", []) or [] if holder else []
                )
                if not inst_list:
                    break
                for inst in inst_list:
                    out.append(
                        UnusedResource(
                            resource_id=getattr(inst, "instance_id", ""),
                            resource_name=(
                                getattr(inst, "instance_name", "")
                                or getattr(inst, "instance_id", "")
                            ),
                            resource_type="ecs_instance",
                            provider="alibaba",
                            region=region_id,
                            reason="Instance is stopped (disk still billed)",
                            estimated_monthly_savings="varies by disk size",
                        )
                    )
                total = getattr(body, "total_count", 0) or 0
                if page * 100 >= total:
                    break
                page += 1
        except Exception as exc:
            logger.debug("Stopped-instance scan skipped: %s", exc)
        return out
