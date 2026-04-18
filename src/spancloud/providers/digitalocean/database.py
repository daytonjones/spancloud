"""DigitalOcean managed database resource discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.digitalocean.auth import DigitalOceanAuth

logger = get_logger(__name__)

_DB_STATE_MAP: dict[str, ResourceState] = {
    "online": ResourceState.RUNNING,
    "creating": ResourceState.PENDING,
    "resizing": ResourceState.PENDING,
    "migrating": ResourceState.PENDING,
    "forking": ResourceState.PENDING,
}


class DatabaseResources:
    """Handles DO managed database discovery."""

    def __init__(self, auth: DigitalOceanAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_databases(self, region: str | None = None) -> list[Resource]:
        """List all managed database clusters."""
        raw = await self._auth.get_paginated("/databases", "databases")

        resources: list[Resource] = []
        for db in raw:
            db_region = db.get("region", "")
            if region and db_region != region:
                continue
            resources.append(self._map_database(db))

        logger.debug("Found %d DO managed databases", len(resources))
        return resources

    def _map_database(self, db: dict[str, Any]) -> Resource:
        status = db.get("status", "")
        tags = db.get("tags") or []
        tag_dict = {f"tag_{i}": t for i, t in enumerate(tags)} if tags else {}
        connection = db.get("connection") or {}

        return Resource(
            id=db.get("id", ""),
            name=db.get("name", "") or db.get("id", ""),
            resource_type=ResourceType.DATABASE,
            provider="digitalocean",
            region=db.get("region", ""),
            state=_DB_STATE_MAP.get(status, ResourceState.UNKNOWN),
            created_at=db.get("created_at"),
            tags=tag_dict,
            metadata={
                "engine": db.get("engine", ""),
                "version": db.get("version", ""),
                "size": db.get("size", ""),
                "num_nodes": str(db.get("num_nodes", "")),
                "host": connection.get("host", ""),
                "port": str(connection.get("port", "")),
                "database": connection.get("database", ""),
                "resource_subtype": "managed_database",
            },
        )
