"""Vultr DNS domain and record resource discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.vultr.auth import VultrAuth

logger = get_logger(__name__)


class DNSResources:
    """Handles Vultr DNS domain and record discovery."""

    def __init__(self, auth: VultrAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_domains(self) -> list[Resource]:
        """List all DNS domains.

        Returns:
            List of Resource objects representing DNS domains.
        """
        raw = await self._auth.get_paginated("/domains", "domains")

        resources: list[Resource] = []
        for domain in raw:
            resources.append(self._map_domain(domain))

        logger.debug("Found %d Vultr DNS domains", len(resources))
        return resources

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_records(self, domain_name: str | None = None) -> list[Resource]:
        """List DNS records across all domains (or a specific domain).

        Args:
            domain_name: Optional domain to filter.

        Returns:
            List of Resource objects representing DNS records.
        """
        if domain_name:
            domains = [domain_name]
        else:
            raw_domains = await self._auth.get_paginated("/domains", "domains")
            domains = [d.get("domain", "") for d in raw_domains if d.get("domain")]

        resources: list[Resource] = []
        for domain in domains:
            try:
                raw_records = await self._auth.get_paginated(
                    f"/domains/{domain}/records", "records"
                )
                for record in raw_records:
                    resources.append(self._map_record(record, domain))
            except Exception as exc:
                logger.warning("Failed to list records for %s: %s", domain, exc)

        logger.debug("Found %d Vultr DNS records", len(resources))
        return resources

    def _map_domain(self, domain: dict[str, Any]) -> Resource:
        """Map a Vultr DNS domain to a unified Resource."""
        return Resource(
            id=domain.get("domain", ""),
            name=domain.get("domain", ""),
            resource_type=ResourceType.DNS,
            provider="vultr",
            region="global",
            state=ResourceState.RUNNING,
            created_at=domain.get("date_created"),
            tags={},
            metadata={
                "dns_sec": domain.get("dns_sec", ""),
                "resource_subtype": "dns_domain",
            },
        )

    def _map_record(self, record: dict[str, Any], domain: str) -> Resource:
        """Map a Vultr DNS record to a unified Resource."""
        rec_type = record.get("type", "")
        rec_name = record.get("name", "")
        full_name = f"{rec_name}.{domain}" if rec_name else domain

        return Resource(
            id=record.get("id", ""),
            name=full_name,
            resource_type=ResourceType.DNS,
            provider="vultr",
            region="global",
            state=ResourceState.RUNNING,
            tags={},
            metadata={
                "record_type": rec_type,
                "data": record.get("data", ""),
                "ttl": str(record.get("ttl", "")),
                "priority": str(record.get("priority", "")),
                "domain": domain,
                "resource_subtype": "dns_record",
            },
        )
