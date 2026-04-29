"""OCI Oracle Functions (serverless) resource discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.providers.oci._retry import OCI_RETRY as retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.oci.auth import OCIAuth

logger = get_logger(__name__)

_LIFECYCLE_STATE_MAP: dict[str, ResourceState] = {
    "ACTIVE": ResourceState.RUNNING,
    "CREATING": ResourceState.PENDING,
    "DELETING": ResourceState.PENDING,
    "DELETED": ResourceState.TERMINATED,
    "FAILED": ResourceState.ERROR,
}


class OCIFunctionsResources:
    """Handles OCI Oracle Functions (applications + functions) discovery."""

    def __init__(self, auth: OCIAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_functions(self, region: str | None = None) -> list[Resource]:
        """List all Oracle Functions applications and their functions."""
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d OCI serverless resources", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        import oci

        config = dict(self._auth.config)
        if region:
            config["region"] = region
        effective_region: str = config.get("region", self._auth.region) or ""

        compartment = self._auth.compartment_id
        if not compartment:
            logger.debug("No OCI compartment_id configured — skipping Functions")
            return []

        try:
            client = oci.functions.FunctionsManagementClient(config)
        except Exception as exc:
            logger.debug("FunctionsManagementClient init failed: %s", exc)
            return []

        resources: list[Resource] = []

        # Collect applications
        applications: list[Any] = []
        page: str | None = None
        try:
            while True:
                result = client.list_applications(
                    compartment_id=compartment, page=page
                )
                applications.extend(result.data or [])
                page = result.next_page
                if not page:
                    break
        except Exception as exc:
            logger.debug("OCI list_applications failed: %s", exc)
            return []

        for app in applications:
            resources.append(self._map_application(app, effective_region))

            # Collect functions within each application
            fn_page: str | None = None
            try:
                while True:
                    fn_result = client.list_functions(
                        application_id=app.id, page=fn_page
                    )
                    for fn in fn_result.data or []:
                        resources.append(
                            self._map_function(fn, effective_region)
                        )
                    fn_page = fn_result.next_page
                    if not fn_page:
                        break
            except Exception as exc:
                logger.debug(
                    "OCI list_functions for app %s failed: %s", app.id, exc
                )

        return resources

    def _map_application(self, app: Any, region: str) -> Resource:
        tags = dict(getattr(app, "freeform_tags", None) or {})
        metadata: dict[str, Any] = {
            "resource_subtype": "function_application",
            "shape": getattr(app, "shape", "") or "",
            "compartment_id": getattr(app, "compartment_id", "") or "",
            "config": dict(getattr(app, "config", None) or {}),
        }
        return Resource(
            id=app.id,
            name=getattr(app, "display_name", "") or app.id,
            resource_type=ResourceType.SERVERLESS,
            provider="oci",
            region=region,
            state=_LIFECYCLE_STATE_MAP.get(
                str(getattr(app, "lifecycle_state", "") or ""),
                ResourceState.UNKNOWN,
            ),
            created_at=getattr(app, "time_created", None),
            tags=tags,
            metadata=metadata,
        )

    def _map_function(self, fn: Any, region: str) -> Resource:
        tags = dict(getattr(fn, "freeform_tags", None) or {})
        metadata: dict[str, Any] = {
            "resource_subtype": "function",
            "application_id": getattr(fn, "application_id", "") or "",
            "image": getattr(fn, "image", "") or "",
            "memory_in_mbs": str(getattr(fn, "memory_in_mbs", "") or ""),
            "timeout_in_seconds": str(
                getattr(fn, "timeout_in_seconds", "") or ""
            ),
            "invoke_endpoint": getattr(fn, "invoke_endpoint", "") or "",
        }
        return Resource(
            id=fn.id,
            name=getattr(fn, "display_name", "") or fn.id,
            resource_type=ResourceType.SERVERLESS,
            provider="oci",
            region=region,
            state=_LIFECYCLE_STATE_MAP.get(
                str(getattr(fn, "lifecycle_state", "") or ""),
                ResourceState.UNKNOWN,
            ),
            created_at=getattr(fn, "time_created", None),
            tags=tags,
            metadata=metadata,
        )
