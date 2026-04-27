"""GCP unused resource detection.

Finds:
- Unattached persistent disks
- Unused static external IPs
- Old snapshots with no disk reference
- VMs stopped for extended periods
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from google.cloud import compute_v1

from spancloud.analysis.models import UnusedResource, UnusedResourceReport
from spancloud.utils.logging import get_logger
from spancloud.providers.gcp._retry import GCP_RETRY_SLOW
from spancloud.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from spancloud.providers.gcp.auth import GCPAuth

logger = get_logger(__name__)

_GCP_LIMITER = RateLimiter(calls_per_second=8.0, max_concurrency=10)


class GCPUnusedDetector:
    """Finds unused or idle GCP resources that may be wasting money.

    All checks use rate limiting and pagination to avoid throttling.
    """

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    @GCP_RETRY_SLOW
    async def scan(
        self,
        region: str | None = None,
        stopped_days_threshold: int = 30,
        snapshot_days_threshold: int = 90,
    ) -> UnusedResourceReport:
        """Scan for unused GCP resources.

        Args:
            region: Optional region to filter by.
            stopped_days_threshold: Days a VM must be stopped to flag.
            snapshot_days_threshold: Days since snapshot creation without disk.

        Returns:
            UnusedResourceReport with all identified waste.
        """
        project = self._auth.project_id
        if not project:
            return UnusedResourceReport(provider="gcp")

        tasks = [
            self._find_unattached_disks(project, region),
            self._find_unused_ips(project, region),
            self._find_old_snapshots(project, snapshot_days_threshold),
            self._find_long_stopped_vms(project, region, stopped_days_threshold),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        resources: list[UnusedResource] = []
        for result in results:
            if isinstance(result, list):
                resources.extend(result)
            elif isinstance(result, Exception):
                logger.warning("GCP unused detection check failed: %s", result)

        return UnusedResourceReport(provider="gcp", resources=resources)

    async def _find_unattached_disks(
        self, project: str, region: str | None = None
    ) -> list[UnusedResource]:
        """Find persistent disks not attached to any instance."""
        client = compute_v1.DisksClient(credentials=self._auth.credentials)

        def _fetch() -> list[dict[str, Any]]:
            disks: list[dict[str, Any]] = []
            request = compute_v1.AggregatedListDisksRequest(project=project)
            for zone_key, scoped_list in client.aggregated_list(request=request):
                for disk in scoped_list.disks or []:
                    zone_name = zone_key.split("/")[-1] if "/" in zone_key else zone_key
                    if region and not zone_name.startswith(region):
                        continue
                    if not disk.users:  # No attached instances
                        disks.append({
                            "name": disk.name or str(disk.id),
                            "zone": zone_name,
                            "size_gb": disk.size_gb or 0,
                            "type": (disk.type_ or "").rsplit("/", 1)[-1],
                            "status": disk.status or "",
                        })
            return disks

        async with _GCP_LIMITER:
            unattached = await asyncio.to_thread(_fetch)

        resources: list[UnusedResource] = []
        for disk in unattached:
            # Rough cost: pd-standard ~$0.04/GB/mo, pd-ssd ~$0.17/GB/mo
            rate = 0.17 if "ssd" in disk["type"].lower() else 0.04
            est = f"~${disk['size_gb'] * rate:,.2f}/mo ({disk['type']})"

            resources.append(
                UnusedResource(
                    resource_id=disk["name"],
                    resource_name=disk["name"],
                    resource_type="persistent_disk",
                    provider="gcp",
                    region=disk["zone"],
                    reason=f"Unattached {disk['size_gb']} GB persistent disk ({disk['type']})",
                    estimated_monthly_savings=est,
                )
            )

        return resources

    async def _find_unused_ips(
        self, project: str, region: str | None = None
    ) -> list[UnusedResource]:
        """Find static external IPs not in use."""
        client = compute_v1.AddressesClient(credentials=self._auth.credentials)

        def _fetch() -> list[dict[str, Any]]:
            addresses: list[dict[str, Any]] = []
            request = compute_v1.AggregatedListAddressesRequest(project=project)
            for region_key, scoped_list in client.aggregated_list(request=request):
                for addr in scoped_list.addresses or []:
                    region_name = (
                        region_key.split("/")[-1] if "/" in region_key else region_key
                    )
                    if region and region != region_name:
                        continue
                    if addr.status == "RESERVED" and not addr.users:
                        addresses.append({
                            "name": addr.name or "",
                            "address": addr.address or "",
                            "region": region_name,
                            "type": addr.address_type or "",
                        })
            return addresses

        async with _GCP_LIMITER:
            unused = await asyncio.to_thread(_fetch)

        resources: list[UnusedResource] = []
        for addr in unused:
            resources.append(
                UnusedResource(
                    resource_id=addr["name"],
                    resource_name=f"{addr['name']} ({addr['address']})",
                    resource_type="static_ip",
                    provider="gcp",
                    region=addr["region"],
                    reason=f"Static IP {addr['address']} is reserved but not in use",
                    estimated_monthly_savings="~$7.30/mo (idle static IP)",
                )
            )

        return resources

    async def _find_old_snapshots(
        self, project: str, days_threshold: int = 90
    ) -> list[UnusedResource]:
        """Find snapshots older than threshold."""
        client = compute_v1.SnapshotsClient(credentials=self._auth.credentials)
        cutoff = datetime.now(UTC) - timedelta(days=days_threshold)

        def _fetch() -> list[dict[str, Any]]:
            snapshots: list[dict[str, Any]] = []
            for snap in client.list(project=project):
                # Parse creation timestamp
                created = snap.creation_timestamp or ""
                try:
                    created_dt = datetime.fromisoformat(created)
                except (ValueError, TypeError):
                    continue

                if created_dt < cutoff:
                    snapshots.append({
                        "name": snap.name or str(snap.id),
                        "size_gb": snap.disk_size_gb or 0,
                        "source_disk": (snap.source_disk or "").rsplit("/", 1)[-1],
                        "created": created_dt,
                        "status": snap.status or "",
                    })
            return snapshots

        async with _GCP_LIMITER:
            old_snaps = await asyncio.to_thread(_fetch)

        resources: list[UnusedResource] = []
        for snap in old_snaps:
            est = f"~${snap['size_gb'] * 0.026:,.2f}/mo (snapshot storage)"
            resources.append(
                UnusedResource(
                    resource_id=snap["name"],
                    resource_name=snap["name"],
                    resource_type="snapshot",
                    provider="gcp",
                    reason=(
                        f"Snapshot '{snap['name']}' ({snap['size_gb']} GB) "
                        f"is {days_threshold}+ days old"
                    ),
                    last_used=snap["created"],
                    estimated_monthly_savings=est,
                )
            )

        return resources

    async def _find_long_stopped_vms(
        self, project: str, region: str | None = None, days_threshold: int = 30
    ) -> list[UnusedResource]:
        """Find VMs that have been stopped (TERMINATED status) for an extended period."""
        client = compute_v1.InstancesClient(credentials=self._auth.credentials)

        def _fetch() -> list[dict[str, Any]]:
            instances: list[dict[str, Any]] = []
            request = compute_v1.AggregatedListInstancesRequest(project=project)
            for zone_key, scoped_list in client.aggregated_list(request=request):
                for inst in scoped_list.instances or []:
                    if inst.status not in ("TERMINATED", "SUSPENDED"):
                        continue
                    zone_name = zone_key.split("/")[-1] if "/" in zone_key else zone_key
                    if region and not zone_name.startswith(region):
                        continue

                    # Use last_stop_timestamp or creation_timestamp
                    ts = inst.last_stop_timestamp or inst.creation_timestamp or ""
                    try:
                        stopped_dt = datetime.fromisoformat(ts)
                    except (ValueError, TypeError):
                        continue

                    cutoff = datetime.now(UTC) - timedelta(days=days_threshold)
                    if stopped_dt < cutoff:
                        labels = dict(inst.labels) if inst.labels else {}
                        instances.append({
                            "name": inst.name or str(inst.id),
                            "zone": zone_name,
                            "machine_type": (inst.machine_type or "").rsplit("/", 1)[-1],
                            "stopped_at": stopped_dt,
                            "labels": labels,
                        })
            return instances

        async with _GCP_LIMITER:
            stopped = await asyncio.to_thread(_fetch)

        resources: list[UnusedResource] = []
        for vm in stopped:
            resources.append(
                UnusedResource(
                    resource_id=vm["name"],
                    resource_name=vm["name"],
                    resource_type="gce_instance",
                    provider="gcp",
                    region=vm["zone"],
                    reason=(
                        f"VM '{vm['name']}' ({vm['machine_type']}) "
                        f"stopped for {days_threshold}+ days"
                    ),
                    last_used=vm["stopped_at"],
                    estimated_monthly_savings="Disk charges still apply for attached disks",
                )
            )

        return resources
