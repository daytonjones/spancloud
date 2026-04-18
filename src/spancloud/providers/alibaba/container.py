"""Alibaba Container Service for Kubernetes (ACK) discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.alibaba.auth import AlibabaAuth

logger = get_logger(__name__)


class ACKResources:
    """Handles Alibaba ACK cluster discovery."""

    def __init__(self, auth: AlibabaAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_clusters(self, region: str | None = None) -> list[Resource]:
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d Alibaba ACK clusters", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        from alibabacloud_cs20151215.client import Client as CsClient

        region_id = region or self._auth.region
        client = CsClient(self._auth.cs_config(region_id))

        try:
            response = client.describe_clusters_v1with_options({}, {})
        except Exception as exc:
            logger.debug("ACK list failed: %s", exc)
            return []

        clusters = getattr(response.body, "clusters", None) or []
        resources: list[Resource] = []
        for c in clusters:
            resources.append(self._map_cluster(c, region_id))
        return resources

    def _map_cluster(self, c: Any, region: str) -> Resource:
        state_raw = str(getattr(c, "state", "") or "")
        state = (
            ResourceState.RUNNING
            if state_raw == "running"
            else ResourceState.PENDING
            if state_raw in ("initial", "updating", "scaling")
            else ResourceState.STOPPED
            if state_raw == "stopped"
            else ResourceState.UNKNOWN
        )
        return Resource(
            id=getattr(c, "cluster_id", "") or "",
            name=getattr(c, "name", "") or getattr(c, "cluster_id", ""),
            resource_type=ResourceType.CONTAINER,
            provider="alibaba",
            region=region,
            state=state,
            metadata={
                "cluster_type": getattr(c, "cluster_type", "") or "",
                "version": getattr(c, "current_version", "") or "",
                "size": str(getattr(c, "size", "") or ""),
                "vpc_id": getattr(c, "vpc_id", "") or "",
                "resource_subtype": "ack_cluster",
            },
        )
