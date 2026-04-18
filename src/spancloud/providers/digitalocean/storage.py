"""DigitalOcean Spaces (object storage) and Volumes (block storage) discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.digitalocean.auth import DigitalOceanAuth

logger = get_logger(__name__)


class VolumeResources:
    """Handles DO block storage volume discovery."""

    def __init__(self, auth: DigitalOceanAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_volumes(self, region: str | None = None) -> list[Resource]:
        """List all block storage volumes."""
        raw = await self._auth.get_paginated("/volumes", "volumes")

        resources: list[Resource] = []
        for v in raw:
            region_slug = (v.get("region") or {}).get("slug", "")
            if region and region_slug != region:
                continue
            resources.append(self._map_volume(v))

        logger.debug("Found %d DO volumes", len(resources))
        return resources

    def _map_volume(self, v: dict[str, Any]) -> Resource:
        region = v.get("region") or {}
        droplet_ids = v.get("droplet_ids") or []
        tags = v.get("tags") or []
        tag_dict = {f"tag_{i}": t for i, t in enumerate(tags)} if tags else {}

        return Resource(
            id=v.get("id", ""),
            name=v.get("name", "") or v.get("id", ""),
            resource_type=ResourceType.STORAGE,
            provider="digitalocean",
            region=region.get("slug", ""),
            state=ResourceState.RUNNING if droplet_ids else ResourceState.STOPPED,
            created_at=v.get("created_at"),
            tags=tag_dict,
            metadata={
                "size_gb": str(v.get("size_gigabytes", "")),
                "filesystem_type": v.get("filesystem_type", ""),
                "filesystem_label": v.get("filesystem_label", ""),
                "description": v.get("description", ""),
                "attached_to": (
                    ", ".join(str(d) for d in droplet_ids) if droplet_ids
                    else "not attached"
                ),
                "resource_subtype": "volume",
            },
        )


class SpacesResources:
    """Handles DO Spaces (object storage) discovery.

    Note: DO Spaces uses S3-compatible API but the metadata we can get
    via the DO API is limited — we can list regions and CDN endpoints.
    Full bucket listing requires the S3 API with separate credentials.
    """

    def __init__(self, auth: DigitalOceanAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_cdn_endpoints(
        self, region: str | None = None
    ) -> list[Resource]:
        """List Spaces CDN endpoints (closest we can get to 'spaces' via DO API)."""
        try:
            raw = await self._auth.get_paginated("/cdn/endpoints", "endpoints")
        except Exception as exc:
            logger.debug("Could not list CDN endpoints: %s", exc)
            return []

        resources: list[Resource] = []
        for ep in raw:
            resources.append(self._map_endpoint(ep))

        logger.debug("Found %d DO CDN endpoints", len(resources))
        return resources

    def _map_endpoint(self, ep: dict[str, Any]) -> Resource:
        return Resource(
            id=ep.get("id", ""),
            name=ep.get("origin", "") or ep.get("id", ""),
            resource_type=ResourceType.STORAGE,
            provider="digitalocean",
            region="global",
            state=ResourceState.RUNNING,
            created_at=ep.get("created_at"),
            metadata={
                "origin": ep.get("origin", ""),
                "endpoint": ep.get("endpoint", ""),
                "ttl": str(ep.get("ttl", "")),
                "custom_domain": ep.get("custom_domain", ""),
                "resource_subtype": "cdn_endpoint",
            },
        )
