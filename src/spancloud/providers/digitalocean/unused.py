"""DigitalOcean unused resource detection."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from spancloud.analysis.models import UnusedResource, UnusedResourceReport
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.digitalocean.auth import DigitalOceanAuth

logger = get_logger(__name__)


class DigitalOceanUnusedDetector:
    """Finds unused DO resources."""

    def __init__(self, auth: DigitalOceanAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def scan(
        self,
        region: str | None = None,
        stopped_days_threshold: int = 30,
        snapshot_days_threshold: int = 90,
    ) -> UnusedResourceReport:
        """Scan for unused DO resources."""
        tasks = [
            self._find_unattached_volumes(region),
            self._find_stopped_droplets(region, stopped_days_threshold),
            self._find_unused_reserved_ips(),
            self._find_old_snapshots(snapshot_days_threshold),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        resources: list[UnusedResource] = []
        for result in results:
            if isinstance(result, list):
                resources.extend(result)
            elif isinstance(result, Exception):
                logger.warning("DO unused check failed: %s", result)

        return UnusedResourceReport(provider="digitalocean", resources=resources)

    async def _find_unattached_volumes(
        self, region: str | None = None
    ) -> list[UnusedResource]:
        """Find block storage volumes not attached to any droplet."""
        volumes = await self._auth.get_paginated("/volumes", "volumes")

        resources: list[UnusedResource] = []
        for v in volumes:
            if region and (v.get("region") or {}).get("slug") != region:
                continue
            if not v.get("droplet_ids"):
                size = v.get("size_gigabytes", 0)
                # DO block storage: $0.10/GB/mo
                est = f"~${size * 0.10:,.2f}/mo"
                resources.append(UnusedResource(
                    resource_id=v.get("id", ""),
                    resource_name=v.get("name", "") or v.get("id", ""),
                    resource_type="volume",
                    provider="digitalocean",
                    region=(v.get("region") or {}).get("slug", ""),
                    reason=f"Unattached {size} GB block storage volume",
                    estimated_monthly_savings=est,
                ))

        return resources

    async def _find_stopped_droplets(
        self, region: str | None = None, days_threshold: int = 30
    ) -> list[UnusedResource]:
        """Find droplets that are powered off."""
        droplets = await self._auth.get_paginated("/droplets", "droplets")

        resources: list[UnusedResource] = []
        for d in droplets:
            if region and (d.get("region") or {}).get("slug") != region:
                continue
            if d.get("status") == "off":
                name = d.get("name", str(d.get("id", "")))
                size = d.get("size") or {}
                price = size.get("price_monthly", 0)
                resources.append(UnusedResource(
                    resource_id=str(d.get("id", "")),
                    resource_name=name,
                    resource_type="droplet",
                    provider="digitalocean",
                    region=(d.get("region") or {}).get("slug", ""),
                    reason=f"Droplet '{name}' is powered off (still billed)",
                    estimated_monthly_savings=f"~${price}/mo" if price else "",
                ))

        return resources

    async def _find_unused_reserved_ips(self) -> list[UnusedResource]:
        """Find reserved IPs not attached to any droplet."""
        try:
            ips = await self._auth.get_paginated(
                "/reserved_ips", "reserved_ips"
            )
        except Exception:
            return []

        resources: list[UnusedResource] = []
        for ip in ips:
            if not ip.get("droplet"):
                addr = ip.get("ip", "")
                resources.append(UnusedResource(
                    resource_id=addr,
                    resource_name=addr,
                    resource_type="reserved_ip",
                    provider="digitalocean",
                    region=(ip.get("region") or {}).get("slug", ""),
                    reason=f"Reserved IP {addr} not attached to any droplet",
                    estimated_monthly_savings="~$4/mo (idle reserved IP)",
                ))

        return resources

    async def _find_old_snapshots(
        self, days_threshold: int = 90
    ) -> list[UnusedResource]:
        """Find old snapshots."""
        try:
            snaps = await self._auth.get_paginated("/snapshots", "snapshots")
        except Exception:
            return []

        cutoff = datetime.now(UTC) - timedelta(days=days_threshold)
        resources: list[UnusedResource] = []
        for snap in snaps:
            created = snap.get("created_at", "")
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            if created_dt < cutoff:
                size_gb = snap.get("size_gigabytes", 0)
                resources.append(UnusedResource(
                    resource_id=snap.get("id", ""),
                    resource_name=snap.get("name", "") or snap.get("id", ""),
                    resource_type="snapshot",
                    provider="digitalocean",
                    reason=(
                        f"Snapshot ({size_gb} GB) is {days_threshold}+ days old"
                    ),
                    last_used=created_dt,
                    estimated_monthly_savings=(
                        f"~${size_gb * 0.06:,.2f}/mo (snapshot storage)"
                    ),
                ))

        return resources
