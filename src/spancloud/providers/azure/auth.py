"""Azure authentication — wraps azure-identity credential chain.

Uses DefaultAzureCredential which checks, in order:
  1. Environment variables (AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID)
  2. Managed Identity
  3. Azure CLI (`az login`)
  4. Azure PowerShell
  5. Interactive browser (last resort)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.config import get_settings
from spancloud.utils.logging import get_logger

if TYPE_CHECKING:
    from azure.identity import DefaultAzureCredential

logger = get_logger(__name__)


class AzureAuth:
    """Manages Azure credential + subscription context."""

    def __init__(self) -> None:
        self._credential: DefaultAzureCredential | None = None
        self._subscription_id: str = ""
        self._tenant_id: str = ""
        self._account_info: dict[str, Any] = {}

    @property
    def subscription_id(self) -> str:
        """Return the configured subscription ID."""
        return self._subscription_id

    @property
    def tenant_id(self) -> str:
        """Return the configured tenant ID (may be empty)."""
        return self._tenant_id

    def set_subscription(self, subscription_id: str) -> None:
        """Switch active subscription. Invalidates cached credential chain."""
        self._subscription_id = subscription_id
        self._account_info = {}

    def _ensure_credential(self) -> DefaultAzureCredential:
        """Build (or return cached) DefaultAzureCredential."""
        if self._credential is None:
            from azure.identity import DefaultAzureCredential

            self._credential = DefaultAzureCredential()
        return self._credential

    def get_credential(self) -> DefaultAzureCredential:
        """Return the Azure credential object for SDK client construction."""
        return self._ensure_credential()

    async def verify(self) -> bool:
        """Verify Azure credentials and subscription access.

        Returns:
            True if auth works and the subscription is reachable.
        """
        settings = get_settings().azure
        if not self._subscription_id:
            self._subscription_id = settings.subscription_id
        if not self._tenant_id:
            self._tenant_id = settings.tenant_id

        if not self._subscription_id:
            logger.warning(
                "Azure subscription_id not configured. "
                "Set SPANCLOUD_AZURE_SUBSCRIPTION_ID or run "
                "'spancloud auth login azure'."
            )
            return False

        try:
            info = await asyncio.to_thread(self._sync_verify)
            self._account_info = info
            logger.info(
                "Azure authenticated for subscription '%s' (%s)",
                info.get("display_name", ""),
                info.get("id", ""),
            )
            return True
        except Exception as exc:
            logger.warning("Azure authentication failed: %s", exc)
            return False

    def _sync_verify(self) -> dict[str, Any]:
        """Sync verification — fetches subscription metadata."""
        from azure.mgmt.subscription import SubscriptionClient

        credential = self._ensure_credential()
        client = SubscriptionClient(credential)
        sub = client.subscriptions.get(self._subscription_id)
        return {
            "id": sub.subscription_id,
            "display_name": sub.display_name,
            "state": str(sub.state),
            "tenant_id": getattr(sub, "tenant_id", None) or self._tenant_id,
        }

    async def get_identity(self) -> dict[str, str]:
        """Return details about the authenticated Azure subscription."""
        return {
            "subscription_id": self._subscription_id,
            "subscription_name": str(self._account_info.get("display_name", "")),
            "state": str(self._account_info.get("state", "")),
            "tenant_id": str(self._account_info.get("tenant_id", self._tenant_id)),
        }

    async def list_subscriptions(self) -> list[dict[str, str]]:
        """List all subscriptions visible to the authenticated identity."""
        return await asyncio.to_thread(self._sync_list_subscriptions)

    def _sync_list_subscriptions(self) -> list[dict[str, str]]:
        from azure.mgmt.subscription import SubscriptionClient

        credential = self._ensure_credential()
        client = SubscriptionClient(credential)
        return [
            {
                "id": sub.subscription_id or "",
                "display_name": sub.display_name or "",
                "state": str(sub.state),
                "tenant_id": getattr(sub, "tenant_id", None) or "",
            }
            for sub in client.subscriptions.list()
        ]
