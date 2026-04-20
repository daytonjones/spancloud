"""GCP Cloud DNS managed zone and record set discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from google.cloud import dns

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.providers.gcp._retry import GCP_RETRY
from spancloud.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from spancloud.providers.gcp.auth import GCPAuth

logger = get_logger(__name__)

_DNS_LIMITER = RateLimiter(calls_per_second=5.0, max_concurrency=5)


class CloudDNSResources:
    """Handles Cloud DNS managed zone and record set discovery."""

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    @GCP_RETRY
    async def list_zones(self) -> list[Resource]:
        """List all Cloud DNS managed zones.

        Returns:
            List of Resource objects representing managed zones.
        """
        project = self._auth.project_id
        if not project:
            logger.warning("No GCP project ID configured — cannot list DNS zones")
            return []

        client = dns.Client(project=project, credentials=self._auth.credentials)

        async with _DNS_LIMITER:
            zones = await asyncio.to_thread(lambda: list(client.list_zones()))

        resources: list[Resource] = []
        for zone in zones:
            visibility = "private" if zone.name_server_set else "public"

            resources.append(Resource(
                id=zone.zone_id or zone.name,
                name=zone.dns_name.rstrip(".") if zone.dns_name else zone.name,
                resource_type=ResourceType.DNS,
                provider="gcp",
                region="global",
                state=ResourceState.RUNNING,
                tags={},
                metadata={
                    "zone_name": zone.name or "",
                    "dns_name": zone.dns_name or "",
                    "description": zone.description or "",
                    "visibility": visibility,
                    "name_servers": ", ".join(zone.name_servers or []),
                    "resource_subtype": "managed_zone",
                },
            ))

        logger.debug("Found %d Cloud DNS managed zones", len(resources))
        return resources

    @GCP_RETRY
    async def list_records(self, zone_name: str | None = None) -> list[Resource]:
        """List DNS record sets across all zones (or a specific zone).

        Args:
            zone_name: Optional zone name to filter. If None, lists across all zones.

        Returns:
            List of Resource objects representing DNS records.
        """
        project = self._auth.project_id
        if not project:
            return []

        client = dns.Client(project=project, credentials=self._auth.credentials)

        if zone_name:
            zone_names = [zone_name]
        else:
            async with _DNS_LIMITER:
                zones = await asyncio.to_thread(lambda: list(client.list_zones()))
            zone_names = [z.name for z in zones]

        resources: list[Resource] = []
        for zn in zone_names:
            try:
                zone = client.zone(zn)
                async with _DNS_LIMITER:
                    records = await asyncio.to_thread(
                        lambda z=zone: list(z.list_resource_record_sets())
                    )
                resources.extend(self._map_records(records, zn))
            except Exception as exc:
                logger.warning("Failed to list records for zone %s: %s", zn, exc)

        logger.debug("Found %d DNS records", len(resources))
        return resources

    def _map_records(
        self, records: list[Any], zone_name: str
    ) -> list[Resource]:
        """Map Cloud DNS record sets to Resource objects."""
        resources: list[Resource] = []
        for record in records:
            rec_name = (record.name or "").rstrip(".")
            rec_type = record.record_type or ""
            ttl = record.ttl or 0
            values = list(record.rrdatas) if record.rrdatas else []

            resources.append(Resource(
                id=f"{zone_name}/{rec_name}/{rec_type}",
                name=rec_name,
                resource_type=ResourceType.DNS,
                provider="gcp",
                region="global",
                state=ResourceState.RUNNING,
                tags={},
                metadata={
                    "record_type": rec_type,
                    "ttl": str(ttl),
                    "values": ", ".join(values[:5]),
                    "zone_name": zone_name,
                    "resource_subtype": "dns_record",
                },
            ))

        return resources
