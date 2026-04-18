"""Azure Storage Account detailed information.

Retrieves storage-account-level details beyond basic listing:
- Blob service properties (versioning, soft delete, change feed)
- Lifecycle management policy
- Blob containers
- Network default action
- Encryption and TLS configuration
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.azure.auth import AzureAuth

logger = get_logger(__name__)


class AzureStorageDetails(BaseModel):
    """Comprehensive details for a single Azure Storage Account."""

    name: str
    resource_group: str = ""
    location: str = ""
    kind: str = ""
    sku: str = ""
    access_tier: str = ""
    https_only: bool = False
    min_tls_version: str = ""
    blob_public_access: bool = False
    versioning: bool = False
    soft_delete_days: int | None = None
    container_soft_delete_days: int | None = None
    lifecycle_policy: str = "none"
    encryption: str = ""
    containers: list[str] = Field(default_factory=list)
    network_default_action: str = ""


class AzureStorageDetailAnalyzer:
    """Retrieves detailed Azure Storage Account configuration.

    Each call fetches blob service properties, lifecycle policy,
    and container list for a single storage account.
    """

    def __init__(self, auth: AzureAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    async def get_account_details(
        self, account_name: str, resource_group: str
    ) -> AzureStorageDetails:
        """Get comprehensive details for a single Azure Storage Account.

        Args:
            account_name: The storage account name.
            resource_group: The resource group containing the account.

        Returns:
            AzureStorageDetails with full configuration.
        """
        return await asyncio.to_thread(
            self._sync_get_details, account_name, resource_group
        )

    def _sync_get_details(
        self, account_name: str, resource_group: str
    ) -> AzureStorageDetails:
        from azure.mgmt.storage import StorageManagementClient

        credential = self._auth.get_credential()
        subscription_id = self._auth.subscription_id

        try:
            client = StorageManagementClient(credential, subscription_id)
        except Exception as exc:
            logger.debug("Could not build StorageManagementClient: %s", exc)
            return AzureStorageDetails(
                name=account_name, resource_group=resource_group
            )

        # --- Storage account properties ---
        try:
            account = client.storage_accounts.get_properties(
                resource_group, account_name
            )
        except Exception as exc:
            logger.debug(
                "Could not fetch storage account properties for %s: %s",
                account_name,
                exc,
            )
            return AzureStorageDetails(
                name=account_name, resource_group=resource_group
            )

        sku_obj = getattr(account, "sku", None)
        sku_name = str(sku_obj.name) if sku_obj else ""
        kind = str(getattr(account, "kind", "") or "")
        location = str(getattr(account, "location", "") or "")
        access_tier = str(getattr(account, "access_tier", "") or "")
        https_only = bool(getattr(account, "enable_https_traffic_only", False))
        min_tls = str(getattr(account, "minimum_tls_version", "") or "")
        blob_public = bool(getattr(account, "allow_blob_public_access", False))

        # Encryption
        encryption_obj = getattr(account, "encryption", None)
        key_source = ""
        if encryption_obj is not None:
            key_source = str(getattr(encryption_obj, "key_source", "") or "")
        if "Customer" in key_source or "keyvault" in key_source.lower():
            encryption_str = "Customer-managed keys"
        else:
            encryption_str = "Microsoft-managed keys"

        # Network rules
        network_rule_set = getattr(account, "network_rule_set", None)
        network_default_action = ""
        if network_rule_set is not None:
            network_default_action = str(
                getattr(network_rule_set, "default_action", "") or ""
            )

        # --- Blob service properties ---
        versioning = False
        soft_delete_days: int | None = None
        container_soft_delete_days: int | None = None

        try:
            blob_props = client.blob_services.get_service_properties(
                resource_group, account_name
            )
            versioning = bool(getattr(blob_props, "versioning_enabled", False))

            drp = getattr(blob_props, "delete_retention_policy", None)
            if drp is not None and getattr(drp, "enabled", False):
                soft_delete_days = getattr(drp, "days", None)

            cdrp = getattr(blob_props, "container_delete_retention_policy", None)
            if cdrp is not None and getattr(cdrp, "enabled", False):
                container_soft_delete_days = getattr(cdrp, "days", None)
        except Exception as exc:
            logger.debug(
                "Could not fetch blob service properties for %s: %s",
                account_name,
                exc,
            )

        # --- Lifecycle management policy ---
        lifecycle_policy = "none"
        try:
            lifecycle = client.management_policies.get(
                resource_group, account_name, "default"
            )
            policy_obj = getattr(lifecycle, "policy", None)
            rules = getattr(policy_obj, "rules", []) if policy_obj else []
            rule_count = len(rules) if rules else 0
            lifecycle_policy = f"{rule_count} rule{'s' if rule_count != 1 else ''}"
        except Exception as exc:
            logger.debug(
                "No lifecycle policy for %s (or fetch failed): %s",
                account_name,
                exc,
            )

        # --- Blob containers ---
        containers: list[str] = []
        try:
            for container in client.blob_containers.list(resource_group, account_name):
                containers.append(container.name or "")
        except Exception as exc:
            logger.debug(
                "Could not list containers for %s: %s", account_name, exc
            )

        return AzureStorageDetails(
            name=account_name,
            resource_group=resource_group,
            location=location,
            kind=kind,
            sku=sku_name,
            access_tier=access_tier,
            https_only=https_only,
            min_tls_version=min_tls,
            blob_public_access=blob_public,
            versioning=versioning,
            soft_delete_days=soft_delete_days,
            container_soft_delete_days=container_soft_delete_days,
            lifecycle_policy=lifecycle_policy,
            encryption=encryption_str,
            containers=containers,
            network_default_action=network_default_action,
        )
