"""AWS Route53 hosted zone and DNS record discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff
from skyforge.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from skyforge.providers.aws.auth import AWSAuth

logger = get_logger(__name__)

# Route53 API: 5 requests/second
_R53_LIMITER = RateLimiter(calls_per_second=4.0, max_concurrency=5)


class Route53Resources:
    """Handles Route53 hosted zone and record set discovery."""

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_hosted_zones(self) -> list[Resource]:
        """List all Route53 hosted zones.

        Returns:
            List of Resource objects representing hosted zones.
        """
        client = self._auth.client("route53")

        def _fetch() -> list[dict[str, Any]]:
            zones: list[dict[str, Any]] = []
            paginator = client.get_paginator("list_hosted_zones")
            for page in paginator.paginate():
                zones.extend(page.get("HostedZones", []))
            return zones

        async with _R53_LIMITER:
            raw_zones = await asyncio.to_thread(_fetch)

        resources: list[Resource] = []
        for zone in raw_zones:
            zone_id = zone["Id"].rsplit("/", 1)[-1]
            name = zone.get("Name", "").rstrip(".")
            is_private = zone.get("Config", {}).get("PrivateZone", False)
            record_count = zone.get("ResourceRecordSetCount", 0)

            resources.append(Resource(
                id=zone_id,
                name=name,
                resource_type=ResourceType.DNS,
                provider="aws",
                region="global",
                state=ResourceState.RUNNING,
                tags={},
                metadata={
                    "record_count": str(record_count),
                    "is_private": str(is_private),
                    "comment": zone.get("Config", {}).get("Comment", ""),
                    "resource_subtype": "hosted_zone",
                },
            ))

        logger.debug("Found %d Route53 hosted zones", len(resources))
        return resources

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_records(self, zone_id: str | None = None) -> list[Resource]:
        """List DNS records across all hosted zones (or a specific zone).

        Args:
            zone_id: Optional specific zone ID. If None, lists across all zones.

        Returns:
            List of Resource objects representing DNS records.
        """
        client = self._auth.client("route53")

        if zone_id:
            zone_ids = [zone_id]
        else:
            # Get all zone IDs first
            zones = await self.list_hosted_zones()
            zone_ids = [z.id for z in zones]

        resources: list[Resource] = []
        for zid in zone_ids:
            try:
                async with _R53_LIMITER:
                    records = await self._fetch_zone_records(client, zid)
                resources.extend(records)
            except Exception as exc:
                logger.warning("Failed to list records for zone %s: %s", zid, exc)

        logger.debug("Found %d DNS records", len(resources))
        return resources

    async def _fetch_zone_records(
        self, client: Any, zone_id: str
    ) -> list[Resource]:
        """Fetch all records from a single hosted zone."""

        def _fetch() -> list[dict[str, Any]]:
            records: list[dict[str, Any]] = []
            paginator = client.get_paginator("list_resource_record_sets")
            for page in paginator.paginate(HostedZoneId=zone_id):
                records.extend(page.get("ResourceRecordSets", []))
            return records

        raw_records = await asyncio.to_thread(_fetch)

        resources: list[Resource] = []
        for record in raw_records:
            rec_name = record.get("Name", "").rstrip(".")
            rec_type = record.get("Type", "")
            ttl = record.get("TTL", "")

            # Extract values
            values: list[str] = []
            if record.get("ResourceRecords"):
                values = [r.get("Value", "") for r in record["ResourceRecords"]]
            elif record.get("AliasTarget"):
                alias = record["AliasTarget"]
                values = [f"ALIAS → {alias.get('DNSName', '')}"]

            resources.append(Resource(
                id=f"{zone_id}/{rec_name}/{rec_type}",
                name=rec_name,
                resource_type=ResourceType.DNS,
                provider="aws",
                region="global",
                state=ResourceState.RUNNING,
                tags={},
                metadata={
                    "record_type": rec_type,
                    "ttl": str(ttl),
                    "values": ", ".join(values[:5]),
                    "zone_id": zone_id,
                    "resource_subtype": "dns_record",
                },
            ))

        return resources
