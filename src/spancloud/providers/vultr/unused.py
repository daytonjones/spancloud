"""Vultr unused resource detection.

Finds:
- Unattached block storage volumes
- Stopped/halted instances
- Unattached reserved IPs
- Snapshots (potential waste if old)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from skyforge.analysis.models import UnusedResource, UnusedResourceReport
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.vultr.auth import VultrAuth

logger = get_logger(__name__)


class VultrUnusedDetector:
    """Finds unused or idle Vultr resources."""

    def __init__(self, auth: VultrAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def scan(
        self,
        region: str | None = None,
        stopped_days_threshold: int = 30,
        snapshot_days_threshold: int = 90,
    ) -> UnusedResourceReport:
        """Scan for unused Vultr resources.

        Args:
            region: Optional region filter.
            stopped_days_threshold: Days an instance must be stopped to flag.
            snapshot_days_threshold: Days since snapshot creation.

        Returns:
            UnusedResourceReport with identified waste.
        """
        tasks = [
            self._find_unattached_blocks(region),
            self._find_stopped_instances(region, stopped_days_threshold),
            self._find_unattached_ips(),
            self._find_old_snapshots(snapshot_days_threshold),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        resources: list[UnusedResource] = []
        for result in results:
            if isinstance(result, list):
                resources.extend(result)
            elif isinstance(result, Exception):
                logger.warning("Vultr unused check failed: %s", result)

        return UnusedResourceReport(provider="vultr", resources=resources)

    async def _find_unattached_blocks(
        self, region: str | None = None
    ) -> list[UnusedResource]:
        """Find block storage volumes not attached to any instance."""
        blocks = await self._auth.get_paginated("/blocks", "blocks")

        resources: list[UnusedResource] = []
        for block in blocks:
            if region and block.get("region") != region:
                continue
            if not block.get("attached_to_instance"):
                size = block.get("size_gb", 0)
                cost = block.get("cost", 0)
                resources.append(UnusedResource(
                    resource_id=block.get("id", ""),
                    resource_name=block.get("label", "") or block.get("id", ""),
                    resource_type="block_storage",
                    provider="vultr",
                    region=block.get("region", ""),
                    reason=f"Unattached {size} GB block storage volume",
                    estimated_monthly_savings=f"~${cost}/mo" if cost else "",
                ))

        return resources

    async def _find_stopped_instances(
        self, region: str | None = None, days_threshold: int = 30
    ) -> list[UnusedResource]:
        """Find instances that are stopped/halted."""
        instances = await self._auth.get_paginated("/instances", "instances")

        resources: list[UnusedResource] = []
        for inst in instances:
            if region and inst.get("region") != region:
                continue
            status = inst.get("status", "")
            power = inst.get("power_status", "")

            if status in ("halted", "suspended") or power == "stopped":
                label = inst.get("label", "") or inst.get("id", "")
                plan = inst.get("plan", "")
                resources.append(UnusedResource(
                    resource_id=inst.get("id", ""),
                    resource_name=label,
                    resource_type="instance",
                    provider="vultr",
                    region=inst.get("region", ""),
                    reason=f"Instance '{label}' ({plan}) is {status}/{power}",
                    estimated_monthly_savings="Charges continue while stopped",
                ))

        return resources

    async def _find_unattached_ips(self) -> list[UnusedResource]:
        """Find reserved IPs not attached to any instance."""
        ips = await self._auth.get_paginated("/reserved-ips", "reserved_ips")

        resources: list[UnusedResource] = []
        for ip in ips:
            if not ip.get("instance_id"):
                resources.append(UnusedResource(
                    resource_id=ip.get("id", ""),
                    resource_name=ip.get("subnet", "") or ip.get("id", ""),
                    resource_type="reserved_ip",
                    provider="vultr",
                    region=ip.get("region", ""),
                    reason=f"Reserved IP {ip.get('subnet', '')} not attached to any instance",
                    estimated_monthly_savings="~$3/mo (reserved IP charge)",
                ))

        return resources

    async def _find_old_snapshots(
        self, days_threshold: int = 90
    ) -> list[UnusedResource]:
        """Find snapshots older than threshold."""
        snapshots = await self._auth.get_paginated("/snapshots", "snapshots")
        cutoff = datetime.now(UTC) - timedelta(days=days_threshold)

        resources: list[UnusedResource] = []
        for snap in snapshots:
            created = snap.get("date_created", "")
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue

            if created_dt < cutoff:
                # Vultr /snapshots returns `size` in BYTES — convert to GB
                # before multiplying by the per-GB monthly rate.
                size_bytes = snap.get("size", 0) or 0
                size_gb = size_bytes / (1024 ** 3)
                resources.append(UnusedResource(
                    resource_id=snap.get("id", ""),
                    resource_name=snap.get("description", "") or snap.get("id", ""),
                    resource_type="snapshot",
                    provider="vultr",
                    reason=(
                        f"Snapshot ({size_gb:.2f} GB) is {days_threshold}+ days old"
                    ),
                    last_used=created_dt,
                    estimated_monthly_savings=(
                        f"~${size_gb * 0.05:,.2f}/mo (snapshot storage)"
                    ),
                ))

        return resources
