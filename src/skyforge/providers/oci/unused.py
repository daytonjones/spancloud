"""OCI unused-resource detection."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from skyforge.analysis.models import UnusedResource, UnusedResourceReport
from skyforge.utils.logging import get_logger

if TYPE_CHECKING:
    from skyforge.providers.oci.auth import OCIAuth

logger = get_logger(__name__)


class OCIUnusedDetector:
    """Finds idle or unused OCI resources."""

    def __init__(self, auth: OCIAuth) -> None:
        self._auth = auth

    async def scan(
        self,
        region: str | None = None,
        stopped_days_threshold: int = 30,
        snapshot_days_threshold: int = 30,
    ) -> UnusedResourceReport:
        _ = region, stopped_days_threshold
        results = await asyncio.gather(
            asyncio.to_thread(self._find_detached_volumes),
            asyncio.to_thread(self._find_stopped_instances),
            asyncio.to_thread(
                self._find_old_boot_volume_backups, snapshot_days_threshold
            ),
        )
        unused: list[UnusedResource] = []
        for group in results:
            unused.extend(group)
        return UnusedResourceReport(provider="oci", resources=unused)

    def _find_detached_volumes(self) -> list[UnusedResource]:
        """Block volumes that aren't attached — ~$0.0255/GB/mo standard."""
        import oci

        out: list[UnusedResource] = []
        compartment = self._auth.compartment_id
        if not compartment:
            return out

        try:
            bs = oci.core.BlockstorageClient(self._auth.config)
            compute = oci.core.ComputeClient(self._auth.config)

            # Attached volume IDs
            attached: set[str] = set()
            page: str | None = None
            while True:
                att = compute.list_volume_attachments(
                    compartment_id=compartment, page=page
                )
                for a in att.data or []:
                    if str(getattr(a, "lifecycle_state", "")) == "ATTACHED":
                        attached.add(getattr(a, "volume_id", ""))
                page = att.next_page
                if not page:
                    break

            page = None
            while True:
                vols = bs.list_volumes(compartment_id=compartment, page=page)
                for v in vols.data or []:
                    if str(v.lifecycle_state) != "AVAILABLE":
                        continue
                    if v.id in attached:
                        continue
                    size_gb = getattr(v, "size_in_gbs", 0) or 0
                    est = f"~${size_gb * 0.0255:,.2f}/mo (Block Volume)"
                    out.append(
                        UnusedResource(
                            resource_id=v.id,
                            resource_name=getattr(v, "display_name", "") or v.id,
                            resource_type="block_volume",
                            provider="oci",
                            region=self._auth.region or "",
                            reason=f"Unattached block volume ({size_gb} GB)",
                            last_used=getattr(v, "time_created", None),
                            estimated_monthly_savings=est,
                        )
                    )
                page = vols.next_page
                if not page:
                    break
        except Exception as exc:
            logger.debug("OCI unattached-volume scan skipped: %s", exc)
        return out

    def _find_stopped_instances(self) -> list[UnusedResource]:
        """STOPPED instances — boot/block volumes still incur storage cost."""
        import oci

        out: list[UnusedResource] = []
        compartment = self._auth.compartment_id
        if not compartment:
            return out

        try:
            compute = oci.core.ComputeClient(self._auth.config)
            page: str | None = None
            while True:
                instances = compute.list_instances(
                    compartment_id=compartment, page=page
                )
                for inst in instances.data or []:
                    if str(inst.lifecycle_state) == "STOPPED":
                        out.append(
                            UnusedResource(
                                resource_id=inst.id,
                                resource_name=(
                                    getattr(inst, "display_name", "") or inst.id
                                ),
                                resource_type="compute_instance",
                                provider="oci",
                                region=self._auth.region or "",
                                reason="Instance is stopped (boot volume still billed)",
                                estimated_monthly_savings="varies by boot volume size",
                            )
                        )
                page = instances.next_page
                if not page:
                    break
        except Exception as exc:
            logger.debug("OCI stopped-instance scan skipped: %s", exc)
        return out

    def _find_old_boot_volume_backups(self, days: int) -> list[UnusedResource]:
        """Boot-volume backups older than the threshold — ~$0.0255/GB/mo."""
        import oci

        out: list[UnusedResource] = []
        compartment = self._auth.compartment_id
        if not compartment:
            return out
        cutoff = datetime.now(UTC) - timedelta(days=days)

        try:
            bs = oci.core.BlockstorageClient(self._auth.config)
            page: str | None = None
            while True:
                result = bs.list_boot_volume_backups(
                    compartment_id=compartment, page=page
                )
                for b in result.data or []:
                    created = getattr(b, "time_created", None)
                    if not created or created > cutoff:
                        continue
                    size_gb = getattr(b, "size_in_gbs", 0) or 0
                    est = f"~${size_gb * 0.0255:,.2f}/mo (backup storage)"
                    out.append(
                        UnusedResource(
                            resource_id=b.id,
                            resource_name=getattr(b, "display_name", "") or b.id,
                            resource_type="boot_volume_backup",
                            provider="oci",
                            region=self._auth.region or "",
                            reason=f"Boot volume backup older than {days} days",
                            last_used=created,
                            estimated_monthly_savings=est,
                        )
                    )
                page = result.next_page
                if not page:
                    break
        except Exception as exc:
            logger.debug("OCI old-backup scan skipped: %s", exc)
        return out
