"""OCI database — Autonomous DBs + DB Systems."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.oci.auth import OCIAuth

logger = get_logger(__name__)

_DB_STATE_MAP: dict[str, ResourceState] = {
    "AVAILABLE": ResourceState.RUNNING,
    "STOPPED": ResourceState.STOPPED,
    "PROVISIONING": ResourceState.PENDING,
    "STARTING": ResourceState.PENDING,
    "STOPPING": ResourceState.PENDING,
    "TERMINATED": ResourceState.TERMINATED,
    "TERMINATING": ResourceState.PENDING,
    "FAILED": ResourceState.ERROR,
}


class DatabaseResources:
    """Handles OCI Autonomous DB + DB System discovery."""

    def __init__(self, auth: OCIAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_databases(self, region: str | None = None) -> list[Resource]:
        adbs, systems = await asyncio.gather(
            asyncio.to_thread(self._sync_list_autonomous, region),
            asyncio.to_thread(self._sync_list_db_systems, region),
        )
        combined = adbs + systems
        logger.debug("Found %d OCI databases", len(combined))
        return combined

    def _sync_list_autonomous(self, region: str | None) -> list[Resource]:
        import oci

        config = dict(self._auth.config)
        if region:
            config["region"] = region
        compartment = self._auth.compartment_id
        if not compartment:
            return []

        client = oci.database.DatabaseClient(config)
        resources: list[Resource] = []
        page: str | None = None
        while True:
            result = client.list_autonomous_databases(
                compartment_id=compartment, page=page
            )
            for adb in result.data or []:
                resources.append(self._map_adb(adb, config["region"]))
            page = result.next_page
            if not page:
                break
        return resources

    def _map_adb(self, adb: Any, region: str) -> Resource:
        return Resource(
            id=adb.id,
            name=getattr(adb, "display_name", "") or adb.id,
            resource_type=ResourceType.DATABASE,
            provider="oci",
            region=region,
            state=_DB_STATE_MAP.get(
                str(adb.lifecycle_state), ResourceState.UNKNOWN
            ),
            created_at=getattr(adb, "time_created", None),
            tags=dict(getattr(adb, "freeform_tags", None) or {}),
            metadata={
                "db_name": getattr(adb, "db_name", "") or "",
                "db_workload": getattr(adb, "db_workload", "") or "",
                "cpu_core_count": str(getattr(adb, "cpu_core_count", "") or ""),
                "data_storage_size_tb": str(
                    getattr(adb, "data_storage_size_in_tbs", "") or ""
                ),
                "is_free_tier": str(getattr(adb, "is_free_tier", "") or ""),
                "compartment_id": getattr(adb, "compartment_id", "") or "",
                "resource_subtype": "autonomous_database",
            },
        )

    def _sync_list_db_systems(self, region: str | None) -> list[Resource]:
        import oci

        config = dict(self._auth.config)
        if region:
            config["region"] = region
        compartment = self._auth.compartment_id
        if not compartment:
            return []

        client = oci.database.DatabaseClient(config)
        resources: list[Resource] = []
        page: str | None = None
        while True:
            try:
                result = client.list_db_systems(
                    compartment_id=compartment, page=page
                )
            except Exception as exc:
                logger.debug("list_db_systems failed: %s", exc)
                break
            for sys in result.data or []:
                resources.append(self._map_db_system(sys, config["region"]))
            page = result.next_page
            if not page:
                break
        return resources

    def _map_db_system(self, sys: Any, region: str) -> Resource:
        return Resource(
            id=sys.id,
            name=getattr(sys, "display_name", "") or sys.id,
            resource_type=ResourceType.DATABASE,
            provider="oci",
            region=region,
            state=_DB_STATE_MAP.get(
                str(sys.lifecycle_state), ResourceState.UNKNOWN
            ),
            created_at=getattr(sys, "time_created", None),
            tags=dict(getattr(sys, "freeform_tags", None) or {}),
            metadata={
                "shape": getattr(sys, "shape", "") or "",
                "version": getattr(sys, "version", "") or "",
                "node_count": str(getattr(sys, "node_count", "") or ""),
                "db_edition": getattr(sys, "database_edition", "") or "",
                "availability_domain": getattr(sys, "availability_domain", "") or "",
                "resource_subtype": "db_system",
            },
        )
