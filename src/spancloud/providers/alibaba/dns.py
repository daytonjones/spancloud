"""Alibaba Cloud DNS (Alidns) discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.alibaba.auth import AlibabaAuth

logger = get_logger(__name__)


class DNSResources:
    """Handles Alibaba DNS domain discovery."""

    def __init__(self, auth: AlibabaAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_domains(self, region: str | None = None) -> list[Resource]:
        """List domains. Alibaba DNS is a global service."""
        _ = region
        raw = await asyncio.to_thread(self._sync_list)
        logger.debug("Found %d Alibaba DNS domains", len(raw))
        return raw

    def _sync_list(self) -> list[Resource]:
        from alibabacloud_alidns20150109 import models as dns_models
        from alibabacloud_alidns20150109.client import Client as DnsClient

        client = DnsClient(self._auth.alidns_config())

        resources: list[Resource] = []
        page_number = 1
        while True:
            req = dns_models.DescribeDomainsRequest(
                page_number=page_number, page_size=100
            )
            try:
                response = client.describe_domains(req)
            except Exception as exc:
                logger.debug("Alidns list failed: %s", exc)
                break
            body = response.body
            holder = getattr(body, "domains", None)
            domain_list = (
                getattr(holder, "domain", []) or [] if holder else []
            )
            if not domain_list:
                break
            for d in domain_list:
                resources.append(self._map_domain(d))
            total = getattr(body, "total_count", 0) or 0
            if page_number * 100 >= total:
                break
            page_number += 1
        return resources

    def _map_domain(self, d: Any) -> Resource:
        return Resource(
            id=getattr(d, "domain_id", "") or getattr(d, "domain_name", ""),
            name=getattr(d, "domain_name", ""),
            resource_type=ResourceType.DNS,
            provider="alibaba",
            region="global",
            state=ResourceState.RUNNING,
            metadata={
                "record_count": str(getattr(d, "record_count", "") or ""),
                "group_name": getattr(d, "group_name", "") or "",
                "version_name": getattr(d, "version_name", "") or "",
                "resource_subtype": "dns_domain",
            },
        )
