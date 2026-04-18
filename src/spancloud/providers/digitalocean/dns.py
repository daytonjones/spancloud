"""DigitalOcean DNS domain and record resource discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.digitalocean.auth import DigitalOceanAuth

logger = get_logger(__name__)


class DNSResources:
    """Handles DO DNS domain and record discovery."""

    def __init__(self, auth: DigitalOceanAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_domains(self) -> list[Resource]:
        """List all DNS domains."""
        raw = await self._auth.get_paginated("/domains", "domains")

        resources: list[Resource] = []
        for d in raw:
            resources.append(self._map_domain(d))

        logger.debug("Found %d DO DNS domains", len(resources))
        return resources

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_records(
        self, domain_name: str | None = None
    ) -> list[Resource]:
        """List DNS records across all domains (or a specific domain)."""
        if domain_name:
            domains = [domain_name]
        else:
            raw_domains = await self._auth.get_paginated("/domains", "domains")
            domains = [d.get("name", "") for d in raw_domains if d.get("name")]

        resources: list[Resource] = []
        for domain in domains:
            try:
                raw_records = await self._auth.get_paginated(
                    f"/domains/{domain}/records", "domain_records"
                )
                for record in raw_records:
                    resources.append(self._map_record(record, domain))
            except Exception as exc:
                logger.warning(
                    "Failed to list records for %s: %s", domain, exc
                )

        logger.debug("Found %d DO DNS records", len(resources))
        return resources

    def _map_domain(self, d: dict[str, Any]) -> Resource:
        return Resource(
            id=d.get("name", ""),
            name=d.get("name", ""),
            resource_type=ResourceType.DNS,
            provider="digitalocean",
            region="global",
            state=ResourceState.RUNNING,
            metadata={
                "ttl": str(d.get("ttl", "")),
                "resource_subtype": "dns_domain",
            },
        )

    def _map_record(self, r: dict[str, Any], domain: str) -> Resource:
        rec_name = r.get("name", "")
        rec_type = r.get("type", "")
        full_name = f"{rec_name}.{domain}" if rec_name and rec_name != "@" else domain

        return Resource(
            id=str(r.get("id", "")),
            name=full_name,
            resource_type=ResourceType.DNS,
            provider="digitalocean",
            region="global",
            state=ResourceState.RUNNING,
            metadata={
                "record_type": rec_type,
                "data": str(r.get("data", "")),
                "ttl": str(r.get("ttl", "")),
                "priority": str(r.get("priority", "")),
                "domain": domain,
                "resource_subtype": "dns_record",
            },
        )
