"""Azure Storage Account (blob) resource discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.providers.azure.compute import _parse_resource_group
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.azure.auth import AzureAuth

logger = get_logger(__name__)


class StorageAccountResources:
    """Handles Azure Storage Account discovery."""

    def __init__(self, auth: AzureAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_accounts(self, region: str | None = None) -> list[Resource]:
        """List all storage accounts in the active subscription."""
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d Azure Storage Accounts", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        from azure.mgmt.storage import StorageManagementClient

        credential = self._auth.get_credential()
        client = StorageManagementClient(credential, self._auth.subscription_id)

        resources: list[Resource] = []
        for sa in client.storage_accounts.list():
            if region and sa.location != region:
                continue
            resources.append(self._map_account(sa))
        return resources

    def _map_account(self, sa: Any) -> Resource:
        tags = dict(sa.tags or {})
        sku = getattr(sa, "sku", None)
        kind = str(getattr(sa, "kind", ""))
        provisioning = str(getattr(sa, "provisioning_state", ""))

        state = (
            ResourceState.RUNNING
            if provisioning == "ProvisioningState.SUCCEEDED"
            or provisioning.endswith("Succeeded")
            else ResourceState.PENDING
        )

        return Resource(
            id=sa.id or sa.name,
            name=sa.name,
            resource_type=ResourceType.STORAGE,
            provider="azure",
            region=sa.location,
            state=state,
            created_at=getattr(sa, "creation_time", None),
            tags=tags,
            metadata={
                "sku": str(sku.name) if sku else "",
                "tier": str(getattr(sku, "tier", "") or ""),
                "kind": kind,
                "access_tier": str(getattr(sa, "access_tier", "") or ""),
                "https_only": str(getattr(sa, "enable_https_traffic_only", "")),
                "allow_blob_public_access": str(
                    getattr(sa, "allow_blob_public_access", "")
                ),
                "resource_group": _parse_resource_group(sa.id or ""),
                "resource_subtype": "storage_account",
            },
        )
