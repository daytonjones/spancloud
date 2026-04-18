"""Vultr managed database resource discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.vultr.auth import VultrAuth

logger = get_logger(__name__)

_DB_STATE_MAP: dict[str, ResourceState] = {
    "Running": ResourceState.RUNNING,
    "Rebuilding": ResourceState.PENDING,
    "Rebalancing": ResourceState.PENDING,
    "Configuring": ResourceState.PENDING,
    "Error": ResourceState.ERROR,
}


class DatabaseResources:
    """Handles Vultr managed database discovery."""

    def __init__(self, auth: VultrAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_databases(self, region: str | None = None) -> list[Resource]:
        """List all managed databases.

        Args:
            region: Optional region filter.

        Returns:
            List of Resource objects representing managed databases.
        """
        raw = await self._auth.get_paginated("/databases", "databases")

        resources: list[Resource] = []
        for db in raw:
            db_region = db.get("region", "")
            if region and db_region != region:
                continue
            resources.append(self._map_database(db))

        logger.debug("Found %d Vultr managed databases", len(resources))
        return resources

    def _map_database(self, db: dict[str, Any]) -> Resource:
        """Map a Vultr managed database to a unified Resource."""
        status = db.get("status", "")
        tags = db.get("tags", [])
        tag_dict = {f"tag_{i}": t for i, t in enumerate(tags)} if tags else {}

        return Resource(
            id=db.get("id", ""),
            name=db.get("label", "") or db.get("id", ""),
            resource_type=ResourceType.DATABASE,
            provider="vultr",
            region=db.get("region", ""),
            state=_DB_STATE_MAP.get(status, ResourceState.UNKNOWN),
            created_at=db.get("date_created"),
            tags=tag_dict,
            metadata={
                "engine": db.get("database_engine", ""),
                "engine_version": str(db.get("database_engine_version", "")),
                "plan": db.get("plan", ""),
                "plan_disk": str(db.get("plan_disk", "")),
                "plan_ram": str(db.get("plan_ram", "")),
                "plan_vcpus": str(db.get("plan_vcpus", "")),
                "plan_replicas": str(db.get("plan_replicas", "")),
                "host": db.get("host", ""),
                "port": str(db.get("port", "")),
                "dbname": db.get("dbname", ""),
                "cluster_time_zone": db.get("cluster_time_zone", ""),
                "resource_subtype": "managed_database",
            },
        )
