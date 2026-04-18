"""DigitalOcean serverless resource discovery.

Covers two products:
- App Platform — GET /v2/apps
- Functions     — GET /v2/functions/namespaces, then per-namespace function list
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.digitalocean.auth import DigitalOceanAuth

logger = get_logger(__name__)

_APP_STATE_MAP: dict[str, ResourceState] = {
    "ACTIVE": ResourceState.RUNNING,
    "DEPLOYING": ResourceState.PENDING,
    "ERROR": ResourceState.ERROR,
    "SUPERSEDED": ResourceState.TERMINATED,
    "CANCELED": ResourceState.TERMINATED,
    "PENDING_BUILD": ResourceState.PENDING,
    "PENDING_DEPLOY": ResourceState.PENDING,
    "UNKNOWN": ResourceState.UNKNOWN,
}


class ServerlessResources:
    """Handles DigitalOcean App Platform and Functions discovery."""

    def __init__(self, auth: DigitalOceanAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_serverless(self, region: str | None = None) -> list[Resource]:
        """List all App Platform apps and Functions namespaces/functions.

        Args:
            region: Optional region slug filter (e.g., 'nyc', 'ams').

        Returns:
            List of Resource objects with resource_type=SERVERLESS.
        """
        apps = await self._list_apps(region=region)
        functions = await self._list_functions(region=region)
        resources = apps + functions
        logger.debug(
            "Found %d DO serverless resources (%d apps, %d functions)",
            len(resources),
            len(apps),
            len(functions),
        )
        return resources

    async def _list_apps(self, region: str | None = None) -> list[Resource]:
        """List App Platform apps."""
        try:
            raw = await self._auth.get_paginated("/apps", "apps")
        except Exception as exc:
            logger.debug("DO App Platform list failed: %s", exc)
            return []

        resources: list[Resource] = []
        for app in raw:
            app_region = self._app_region(app)
            if region and app_region and app_region != region:
                continue
            resources.append(self._map_app(app))

        return resources

    async def _list_functions(self, region: str | None = None) -> list[Resource]:
        """List Functions namespaces and their functions."""
        try:
            namespaces = await self._auth.get_paginated(
                "/functions/namespaces", "namespaces"
            )
        except Exception as exc:
            logger.debug("DO Functions namespace list failed: %s", exc)
            return []

        resources: list[Resource] = []
        for ns in namespaces:
            ns_slug = ns.get("namespace", {}).get("api_host", "") or ns.get("id", "")
            # The namespace slug used in paths is the 'id' field
            ns_id = ns.get("id", "") or ns.get("namespace", {}).get("uuid", "")
            ns_region = ns.get("region", "")
            ns_label = ns.get("label", "") or ns_id

            if region and ns_region and ns_region != region:
                continue

            # Fetch functions within this namespace
            try:
                fn_data = await self._auth.get(
                    f"/functions/namespaces/{ns_id}/functions"
                )
                fns = fn_data.get("functions") or []
            except Exception as exc:
                logger.debug(
                    "DO Functions list for namespace %s failed: %s", ns_id, exc
                )
                fns = []

            for fn in fns:
                resources.append(self._map_function(fn, ns_id, ns_label, ns_region))

        return resources

    def _app_region(self, app: dict[str, Any]) -> str:
        """Extract the region slug from an app object."""
        spec = app.get("spec") or {}
        region_obj = app.get("region") or {}
        # prefer the live region slug over the spec's region string
        return region_obj.get("slug", "") or spec.get("region", "")

    def _map_app(self, app: dict[str, Any]) -> Resource:
        """Map a DO App Platform app to a unified Resource."""
        spec = app.get("spec") or {}
        region_obj = app.get("region") or {}
        phase = app.get("phase", "UNKNOWN").upper()

        # Build component count summary
        components: list[str] = []
        for kind in ("services", "workers", "jobs", "static_sites", "functions"):
            items = spec.get(kind) or []
            if items:
                components.append(f"{len(items)} {kind}")

        active_dep = app.get("active_deployment_id", "") or ""
        tier_slug = spec.get("tier_slug", "")

        return Resource(
            id=app.get("id", ""),
            name=spec.get("name", "") or app.get("id", ""),
            resource_type=ResourceType.SERVERLESS,
            provider="digitalocean",
            region=region_obj.get("slug", "") or spec.get("region", ""),
            state=_APP_STATE_MAP.get(phase, ResourceState.UNKNOWN),
            created_at=app.get("created_at"),
            tags={},
            metadata={
                "resource_subtype": "app_platform",
                "phase": phase,
                "tier": tier_slug,
                "active_deployment_id": active_dep,
                "components": ", ".join(components) if components else "",
                "default_ingress": app.get("default_ingress", ""),
                "live_url": app.get("live_url", ""),
                "updated_at": app.get("updated_at", "") or "",
            },
        )

    def _map_function(
        self,
        fn: dict[str, Any],
        namespace_id: str,
        namespace_label: str,
        ns_region: str,
    ) -> Resource:
        """Map a DO Function to a unified Resource."""
        annotations = fn.get("annotations") or {}
        slug = fn.get("name", "") or fn.get("slug", "")
        # name is typically "namespace/package/functionname"
        short_name = slug.rsplit("/", 1)[-1] if "/" in slug else slug

        return Resource(
            id=slug,
            name=short_name,
            resource_type=ResourceType.SERVERLESS,
            provider="digitalocean",
            region=ns_region,
            state=ResourceState.RUNNING,
            created_at=fn.get("created_at"),
            tags={},
            metadata={
                "resource_subtype": "function",
                "namespace": namespace_label,
                "namespace_id": namespace_id,
                "language": annotations.get("web-export", "") or fn.get("language", ""),
                "size": str(fn.get("limits", {}).get("memory", "") or ""),
                "timeout": str(fn.get("limits", {}).get("timeout", "") or ""),
                "updated_at": fn.get("updated_at", "") or "",
            },
        )
