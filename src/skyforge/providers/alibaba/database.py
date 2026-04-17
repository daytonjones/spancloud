"""Alibaba RDS discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.alibaba.auth import AlibabaAuth

logger = get_logger(__name__)

_RDS_STATE_MAP: dict[str, ResourceState] = {
    "Running": ResourceState.RUNNING,
    "Stopped": ResourceState.STOPPED,
    "Creating": ResourceState.PENDING,
    "Rebooting": ResourceState.PENDING,
    "DBInstanceClassChanging": ResourceState.PENDING,
    "Deleting": ResourceState.PENDING,
}


class RDSResources:
    """Handles Alibaba RDS instance discovery."""

    def __init__(self, auth: AlibabaAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_instances(self, region: str | None = None) -> list[Resource]:
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d Alibaba RDS instances", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        from alibabacloud_rds20140815 import models as rds_models
        from alibabacloud_rds20140815.client import Client as RdsClient

        region_id = region or self._auth.region
        client = RdsClient(self._auth.rds_config(region_id))

        resources: list[Resource] = []
        page_number = 1
        while True:
            req = rds_models.DescribeDBInstancesRequest(
                region_id=region_id,
                page_number=page_number,
                page_size=50,
            )
            response = client.describe_dbinstances(req)
            body = response.body
            items = getattr(body, "items", None)
            db_list = (
                getattr(items, "dbinstance", []) or [] if items else []
            )
            if not db_list:
                break
            for inst in db_list:
                resources.append(self._map_rds(inst, region_id))

            total = getattr(body, "total_record_count", 0) or 0
            if page_number * 50 >= total:
                break
            page_number += 1
        return resources

    def _map_rds(self, inst: Any, region: str) -> Resource:
        status = str(getattr(inst, "dbinstance_status", "") or "")
        return Resource(
            id=getattr(inst, "dbinstance_id", "") or "",
            name=(
                getattr(inst, "dbinstance_description", "")
                or getattr(inst, "dbinstance_id", "")
            ),
            resource_type=ResourceType.DATABASE,
            provider="alibaba",
            region=region,
            state=_RDS_STATE_MAP.get(status, ResourceState.UNKNOWN),
            metadata={
                "engine": getattr(inst, "engine", "") or "",
                "engine_version": getattr(inst, "engine_version", "") or "",
                "dbinstance_class": getattr(inst, "dbinstance_class", "") or "",
                "dbinstance_type": getattr(inst, "dbinstance_type", "") or "",
                "pay_type": getattr(inst, "pay_type", "") or "",
                "vpc_id": getattr(inst, "vpc_id", "") or "",
                "resource_subtype": "rds_instance",
            },
        )
