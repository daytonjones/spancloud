"""Azure unused-resource detector."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from skyforge.analysis.models import UnusedResource, UnusedResourceReport
from skyforge.utils.logging import get_logger

if TYPE_CHECKING:
    from skyforge.providers.azure.auth import AzureAuth

logger = get_logger(__name__)


class AzureUnusedDetector:
    """Finds idle or unused Azure resources."""

    def __init__(self, auth: AzureAuth) -> None:
        self._auth = auth

    async def scan(
        self,
        region: str | None = None,
        stopped_days_threshold: int = 30,
        snapshot_days_threshold: int = 30,
    ) -> UnusedResourceReport:
        """Scan for unused resources across the subscription.

        Args:
            region: Optional location filter (currently advisory).
            stopped_days_threshold: Unused if deallocated for this many days.
            snapshot_days_threshold: Flag snapshots older than this.
        """
        _ = region, stopped_days_threshold
        results = await asyncio.gather(
            asyncio.to_thread(self._find_unattached_disks),
            asyncio.to_thread(self._find_deallocated_vms),
            asyncio.to_thread(self._find_unattached_public_ips),
            asyncio.to_thread(
                self._find_old_snapshots, snapshot_days_threshold
            ),
        )

        unused: list[UnusedResource] = []
        for group in results:
            unused.extend(group)

        return UnusedResourceReport(provider="azure", resources=unused)

    def _find_unattached_disks(self) -> list[UnusedResource]:
        """Managed disks with no VM attached — cost ~$0.05/GB/mo for Standard."""
        from azure.mgmt.compute import ComputeManagementClient

        out: list[UnusedResource] = []
        try:
            client = ComputeManagementClient(
                self._auth.get_credential(), self._auth.subscription_id
            )
            for disk in client.disks.list():
                if disk.disk_state and str(disk.disk_state) == "Unattached":
                    size_gb = disk.disk_size_gb or 0
                    est = f"${size_gb * 0.05:,.2f}/mo (est @ Standard HDD)"
                    out.append(
                        UnusedResource(
                            resource_id=disk.id or disk.name,
                            resource_name=disk.name,
                            resource_type="managed_disk",
                            provider="azure",
                            region=disk.location or "",
                            reason=f"Unattached disk ({size_gb} GB)",
                            last_used=getattr(disk, "time_created", None),
                            estimated_monthly_savings=est,
                        )
                    )
        except Exception as exc:
            logger.debug("Unused-disk scan skipped: %s", exc)
        return out

    def _find_deallocated_vms(self) -> list[UnusedResource]:
        """Deallocated VMs — no compute cost but disks still incur storage cost."""
        from azure.mgmt.compute import ComputeManagementClient

        out: list[UnusedResource] = []
        try:
            client = ComputeManagementClient(
                self._auth.get_credential(), self._auth.subscription_id
            )
            for vm in client.virtual_machines.list_all():
                rg = _parse_rg(vm.id or "")
                try:
                    iv = client.virtual_machines.instance_view(rg, vm.name)
                    for s in iv.statuses or []:
                        if s.code == "PowerState/deallocated":
                            out.append(
                                UnusedResource(
                                    resource_id=vm.id or vm.name,
                                    resource_name=vm.name,
                                    resource_type="virtual_machine",
                                    provider="azure",
                                    region=vm.location or "",
                                    reason="VM is deallocated (disk costs continue)",
                                    estimated_monthly_savings="varies by disk size",
                                )
                            )
                            break
                except Exception:
                    continue
        except Exception as exc:
            logger.debug("Deallocated-VM scan skipped: %s", exc)
        return out

    def _find_unattached_public_ips(self) -> list[UnusedResource]:
        """Unassociated public IPs — cost ~$3-5/mo each."""
        from azure.mgmt.network import NetworkManagementClient

        out: list[UnusedResource] = []
        try:
            client = NetworkManagementClient(
                self._auth.get_credential(), self._auth.subscription_id
            )
            for pip in client.public_ip_addresses.list_all():
                if pip.ip_configuration is None:
                    out.append(
                        UnusedResource(
                            resource_id=pip.id or pip.name,
                            resource_name=pip.name,
                            resource_type="public_ip",
                            provider="azure",
                            region=pip.location or "",
                            reason="Public IP is not associated with any resource",
                            estimated_monthly_savings="~$3.60/mo (Standard)",
                        )
                    )
        except Exception as exc:
            logger.debug("Unattached-IP scan skipped: %s", exc)
        return out

    def _find_old_snapshots(self, days: int) -> list[UnusedResource]:
        """Snapshots older than the threshold — cost ~$0.05/GB/mo."""
        from azure.mgmt.compute import ComputeManagementClient

        out: list[UnusedResource] = []
        cutoff = datetime.now(UTC) - timedelta(days=days)

        try:
            client = ComputeManagementClient(
                self._auth.get_credential(), self._auth.subscription_id
            )
            for snap in client.snapshots.list():
                created = getattr(snap, "time_created", None)
                if not created:
                    continue
                if created < cutoff:
                    size_gb = snap.disk_size_gb or 0
                    est = f"${size_gb * 0.05:,.2f}/mo (est)"
                    out.append(
                        UnusedResource(
                            resource_id=snap.id or snap.name,
                            resource_name=snap.name,
                            resource_type="snapshot",
                            provider="azure",
                            region=snap.location or "",
                            reason=f"Snapshot older than {days} days ({size_gb} GB)",
                            last_used=created,
                            estimated_monthly_savings=est,
                        )
                    )
        except Exception as exc:
            logger.debug("Old-snapshot scan skipped: %s", exc)
        return out


def _parse_rg(resource_id: str) -> str:
    parts = resource_id.split("/")
    for i, p in enumerate(parts):
        if p.lower() == "resourcegroups" and i + 1 < len(parts):
            return parts[i + 1]
    return ""
