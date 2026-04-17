"""AWS Lambda function resource discovery."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.aws.auth import AWSAuth

logger = get_logger(__name__)


class LambdaResources:
    """Handles AWS Lambda function discovery."""

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_functions(self, region: str | None = None) -> list[Resource]:
        """List all Lambda functions in the given region.

        Args:
            region: AWS region.

        Returns:
            List of Resource objects representing Lambda functions.
        """
        client = self._auth.client("lambda", region=region)
        paginator = client.get_paginator("list_functions")

        pages = await asyncio.to_thread(lambda: list(paginator.paginate()))

        resources: list[Resource] = []
        for page in pages:
            for fn in page.get("Functions", []):
                resources.append(self._map_function(fn, region or ""))

        logger.debug("Found %d Lambda functions in %s", len(resources), region or "default region")
        return resources

    def _map_function(self, fn: dict[str, Any], region: str) -> Resource:
        """Map a Lambda function to a unified Resource."""
        last_modified = fn.get("LastModified", "")
        created_at = None
        if last_modified:
            with contextlib.suppress(ValueError, TypeError):
                created_at = datetime.fromisoformat(last_modified.replace("+0000", "+00:00"))

        # Lambda functions don't have tags in list response; they're always "active"
        state = fn.get("State", "Active")
        resource_state = ResourceState.RUNNING if state == "Active" else ResourceState.PENDING

        return Resource(
            id=fn["FunctionName"],
            name=fn["FunctionName"],
            resource_type=ResourceType.SERVERLESS,
            provider="aws",
            region=region,
            state=resource_state,
            created_at=created_at,
            metadata={
                "runtime": fn.get("Runtime", ""),
                "handler": fn.get("Handler", ""),
                "memory_mb": str(fn.get("MemorySize", "")),
                "timeout_s": str(fn.get("Timeout", "")),
                "code_size_bytes": str(fn.get("CodeSize", "")),
                "description": fn.get("Description", ""),
                "architectures": ", ".join(fn.get("Architectures", [])),
                "package_type": fn.get("PackageType", ""),
            },
        )
