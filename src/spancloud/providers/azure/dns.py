"""Azure DNS zone and record discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.providers.azure.compute import _parse_resource_group
from spancloud.utils.logging import get_logger
from spancloud.providers.azure._retry import AZURE_RETRY

if TYPE_CHECKING:
    from spancloud.providers.azure.auth import AzureAuth

logger = get_logger(__name__)


class DNSResources:
    """Handles Azure DNS zone discovery."""

    def __init__(self, auth: AzureAuth) -> None:
        self._auth = auth

    @AZURE_RETRY
    async def list_zones(self, region: str | None = None) -> list[Resource]:
        """List all DNS zones in the subscription.

        Note: Azure DNS zones are not region-scoped in the normal sense —
        they're global. `region` filter is accepted for API parity but is
        ignored for DNS zones.
        """
        _ = region
        raw = await asyncio.to_thread(self._sync_list)
        logger.debug("Found %d Azure DNS zones", len(raw))
        return raw

    def _sync_list(self) -> list[Resource]:
        from azure.mgmt.dns import DnsManagementClient

        credential = self._auth.get_credential()
        client = DnsManagementClient(credential, self._auth.subscription_id)

        resources: list[Resource] = []
        for zone in client.zones.list():
            resources.append(self._map_zone(zone))
        return resources

    def _map_zone(self, zone: Any) -> Resource:
        record_count = getattr(zone, "number_of_record_sets", 0) or 0
        zone_type = str(getattr(zone, "zone_type", "") or "")
        name_servers = getattr(zone, "name_servers", []) or []

        return Resource(
            id=zone.id or zone.name,
            name=zone.name,
            resource_type=ResourceType.DNS,
            provider="azure",
            region="global",
            state=ResourceState.RUNNING,
            tags=dict(zone.tags or {}),
            metadata={
                "zone_type": zone_type,
                "record_count": str(record_count),
                "name_server_count": str(len(name_servers)),
                "resource_group": _parse_resource_group(zone.id or ""),
                "resource_subtype": "dns_zone",
            },
        )
