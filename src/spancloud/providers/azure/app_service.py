"""Azure App Service + Functions resource discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.providers.azure.compute import _parse_resource_group
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.azure.auth import AzureAuth

logger = get_logger(__name__)


class AppServiceResources:
    """Handles App Service sites (Web Apps + Function Apps)."""

    def __init__(self, auth: AzureAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_sites(self, region: str | None = None) -> list[Resource]:
        """List all Web Apps and Function Apps in the subscription."""
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d Azure App Service sites", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        from azure.mgmt.web import WebSiteManagementClient

        credential = self._auth.get_credential()
        client = WebSiteManagementClient(credential, self._auth.subscription_id)

        resources: list[Resource] = []
        for site in client.web_apps.list():
            if region and site.location != region:
                continue
            resources.append(self._map_site(site))
        return resources

    def _map_site(self, site: Any) -> Resource:
        kind = str(getattr(site, "kind", "") or "")
        is_function = "functionapp" in kind.lower()
        state_raw = str(getattr(site, "state", "") or "")

        state = (
            ResourceState.RUNNING
            if state_raw == "Running"
            else ResourceState.STOPPED
            if state_raw == "Stopped"
            else ResourceState.UNKNOWN
        )

        return Resource(
            id=site.id or site.name,
            name=site.name,
            resource_type=ResourceType.SERVERLESS,
            provider="azure",
            region=site.location,
            state=state,
            tags=dict(site.tags or {}),
            metadata={
                "kind": kind,
                "is_function_app": str(is_function),
                "default_hostname": getattr(site, "default_host_name", "") or "",
                "https_only": str(getattr(site, "https_only", "")),
                "runtime": str(getattr(site, "site_config", None) and
                    getattr(site.site_config, "linux_fx_version", "") or ""),
                "resource_group": _parse_resource_group(site.id or ""),
                "resource_subtype": (
                    "function_app" if is_function else "web_app"
                ),
            },
        )
