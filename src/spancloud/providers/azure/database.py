"""Azure database resources — SQL Databases + Cosmos DB accounts."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.providers.azure.compute import _parse_resource_group
from spancloud.utils.logging import get_logger
from spancloud.providers.azure._retry import AZURE_RETRY

if TYPE_CHECKING:
    from spancloud.providers.azure.auth import AzureAuth

logger = get_logger(__name__)


class SQLResources:
    """Handles Azure SQL Server + Database discovery."""

    def __init__(self, auth: AzureAuth) -> None:
        self._auth = auth

    @AZURE_RETRY
    async def list_databases(self, region: str | None = None) -> list[Resource]:
        """List all SQL databases across all SQL servers in the subscription."""
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d Azure SQL databases", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        from azure.mgmt.sql import SqlManagementClient

        credential = self._auth.get_credential()
        client = SqlManagementClient(credential, self._auth.subscription_id)

        resources: list[Resource] = []
        for server in client.servers.list():
            if region and server.location != region:
                continue
            rg = _parse_resource_group(server.id or "")
            try:
                for db in client.databases.list_by_server(rg, server.name):
                    if db.name == "master":
                        continue
                    resources.append(self._map_db(db, server, rg))
            except Exception as exc:
                logger.debug("Skipping server %s: %s", server.name, exc)
        return resources

    def _map_db(self, db: Any, server: Any, rg: str) -> Resource:
        sku = getattr(db, "sku", None)
        status = str(getattr(db, "status", "") or "")

        state = (
            ResourceState.RUNNING
            if status in ("Online", "DatabaseStatus.ONLINE")
            else ResourceState.UNKNOWN
        )

        return Resource(
            id=db.id or db.name,
            name=f"{server.name}/{db.name}",
            resource_type=ResourceType.DATABASE,
            provider="azure",
            region=db.location or server.location,
            state=state,
            tags=dict(db.tags or {}),
            metadata={
                "server": server.name,
                "status": status,
                "sku": str(getattr(sku, "name", "") or ""),
                "tier": str(getattr(sku, "tier", "") or ""),
                "collation": getattr(db, "collation", "") or "",
                "resource_group": rg,
                "resource_subtype": "sql_database",
            },
        )


class CosmosDBResources:
    """Handles Azure Cosmos DB account discovery."""

    def __init__(self, auth: AzureAuth) -> None:
        self._auth = auth

    @AZURE_RETRY
    async def list_accounts(self, region: str | None = None) -> list[Resource]:
        """List all Cosmos DB accounts in the subscription."""
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d Azure Cosmos DB accounts", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        from azure.mgmt.cosmosdb import CosmosDBManagementClient

        credential = self._auth.get_credential()
        client = CosmosDBManagementClient(credential, self._auth.subscription_id)

        resources: list[Resource] = []
        for acct in client.database_accounts.list():
            if region and acct.location != region:
                continue
            resources.append(self._map_account(acct))
        return resources

    def _map_account(self, acct: Any) -> Resource:
        kind = str(getattr(acct, "kind", "") or "")
        provisioning = str(getattr(acct, "provisioning_state", "") or "")
        locations = getattr(acct, "locations", []) or []

        return Resource(
            id=acct.id or acct.name,
            name=acct.name,
            resource_type=ResourceType.DATABASE,
            provider="azure",
            region=acct.location,
            state=(
                ResourceState.RUNNING
                if provisioning.endswith("Succeeded")
                else ResourceState.PENDING
            ),
            tags=dict(acct.tags or {}),
            metadata={
                "kind": kind,
                "provisioning_state": provisioning,
                "region_count": str(len(locations)),
                "endpoint": getattr(acct, "document_endpoint", "") or "",
                "resource_group": _parse_resource_group(acct.id or ""),
                "resource_subtype": "cosmos_db",
            },
        )
