"""GCP Cloud Functions resource discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from google.cloud.functions_v2 import FunctionServiceClient
from google.cloud.functions_v2.types import ListFunctionsRequest

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.gcp.auth import GCPAuth

logger = get_logger(__name__)

_FUNCTION_STATE_MAP: dict[str, ResourceState] = {
    "ACTIVE": ResourceState.RUNNING,
    "FAILED": ResourceState.ERROR,
    "DEPLOYING": ResourceState.PENDING,
    "DELETING": ResourceState.PENDING,
    "UNKNOWN": ResourceState.UNKNOWN,
    "STATE_UNSPECIFIED": ResourceState.UNKNOWN,
}


class CloudFunctionsResources:
    """Handles GCP Cloud Functions (2nd gen) discovery."""

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_functions(self, region: str | None = None) -> list[Resource]:
        """List all Cloud Functions in the project.

        Uses the '-' wildcard for location to list functions across all regions,
        then filters by region if specified.

        Args:
            region: Optional region to filter by (e.g., 'us-central1').

        Returns:
            List of Resource objects representing Cloud Functions.
        """
        project = self._auth.project_id
        if not project:
            logger.warning("No GCP project ID configured — cannot list Cloud Functions")
            return []

        client = FunctionServiceClient(credentials=self._auth.credentials)

        def _fetch() -> list[Any]:
            parent = f"projects/{project}/locations/-"
            request = ListFunctionsRequest(parent=parent)
            functions: list[Any] = []
            for fn in client.list_functions(request=request):
                functions.append(fn)
            return functions

        raw_functions = await asyncio.to_thread(_fetch)

        resources: list[Resource] = []
        for fn in raw_functions:
            fn_region = self._extract_region(fn.name or "")
            if region and fn_region != region:
                continue
            resources.append(self._map_function(fn, fn_region))

        logger.debug("Found %d Cloud Functions", len(resources))
        return resources

    def _extract_region(self, name: str) -> str:
        """Extract region from function resource name.

        Format: projects/{project}/locations/{region}/functions/{name}
        """
        parts = name.split("/")
        if len(parts) >= 4:
            return parts[3]
        return ""

    def _map_function(self, fn: Any, region: str) -> Resource:
        """Map a Cloud Function to a unified Resource."""
        state_str = fn.state.name if fn.state else "STATE_UNSPECIFIED"
        labels = dict(fn.labels) if fn.labels else {}

        # Extract function short name from full resource name
        fn_name = fn.name.rsplit("/", 1)[-1] if fn.name else ""

        # Build config
        build_config = fn.build_config
        service_config = fn.service_config

        runtime = build_config.runtime if build_config else ""
        entry_point = build_config.entry_point if build_config else ""

        memory = ""
        timeout = ""
        max_instances = ""
        min_instances = ""
        if service_config:
            memory = service_config.available_memory or ""
            timeout = str(service_config.timeout_seconds) if service_config.timeout_seconds else ""
            max_instances = str(service_config.max_instance_count or "")
            min_instances = str(service_config.min_instance_count or "")

        return Resource(
            id=fn_name,
            name=fn_name,
            resource_type=ResourceType.SERVERLESS,
            provider="gcp",
            region=region,
            state=_FUNCTION_STATE_MAP.get(state_str, ResourceState.UNKNOWN),
            created_at=fn.update_time.timestamp() if fn.update_time else None,
            tags=labels,
            metadata={
                "runtime": runtime,
                "entry_point": entry_point,
                "available_memory": memory,
                "timeout_seconds": timeout,
                "max_instances": max_instances,
                "min_instances": min_instances,
                "environment": fn.environment.name if fn.environment else "",
                "url": fn.url or "",
                "resource_subtype": "cloud_function",
            },
        )
