"""OCI DNS zone discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.providers.oci._retry import OCI_RETRY as retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.oci.auth import OCIAuth

logger = get_logger(__name__)


class DNSResources:
    """Handles OCI DNS zone discovery."""

    def __init__(self, auth: OCIAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_zones(self, region: str | None = None) -> list[Resource]:
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d OCI DNS zones", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        import oci

        config = dict(self._auth.config)
        if region:
            config["region"] = region
        compartment = self._auth.compartment_id
        if not compartment:
            return []

        client = oci.dns.DnsClient(config)
        resources: list[Resource] = []
        page: str | None = None
        while True:
            try:
                result = client.list_zones(
                    compartment_id=compartment, page=page
                )
            except Exception as exc:
                logger.debug("list_zones failed: %s", exc)
                break
            for z in result.data or []:
                resources.append(self._map_zone(z, config["region"]))
            page = result.next_page
            if not page:
                break
        return resources

    def _map_zone(self, z: Any, region: str) -> Resource:
        return Resource(
            id=z.id,
            name=getattr(z, "name", "") or z.id,
            resource_type=ResourceType.DNS,
            provider="oci",
            region=region,
            state=ResourceState.RUNNING,
            created_at=getattr(z, "time_created", None),
            tags=dict(getattr(z, "freeform_tags", None) or {}),
            metadata={
                "zone_type": str(getattr(z, "zone_type", "") or ""),
                "view_id": getattr(z, "view_id", "") or "",
                "version": str(getattr(z, "version", "") or ""),
                "resource_subtype": "dns_zone",
            },
        )
