"""Alibaba Cloud Function Compute (FC) resource discovery.

Uses FC 3.0 SDK (alibabacloud-fc3-20230330) where available.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.alibaba.auth import AlibabaAuth

logger = get_logger(__name__)

_FC_ENDPOINT_TEMPLATE = "{region}.fcapp.run"

_FUNCTION_STATE_MAP: dict[str, ResourceState] = {
    "Active": ResourceState.RUNNING,
    "Inactive": ResourceState.STOPPED,
    "Pending": ResourceState.PENDING,
    "Deleting": ResourceState.PENDING,
    "Failed": ResourceState.ERROR,
}


class AlibabaFCResources:
    """Handles Alibaba Function Compute (FC 3.0) discovery."""

    def __init__(self, auth: AlibabaAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_functions(self, region: str | None = None) -> list[Resource]:
        raw = await asyncio.to_thread(self._sync_list, region)
        logger.debug("Found %d Alibaba FC functions", len(raw))
        return raw

    def _sync_list(self, region: str | None) -> list[Resource]:
        try:
            from alibabacloud_fc3_20230330 import models as fc_models
            from alibabacloud_fc3_20230330.client import Client as FcClient
        except ImportError:
            logger.debug(
                "alibabacloud-fc3-20230330 not installed — skipping FC discovery"
            )
            return []

        self._auth._ensure_credentials()  # noqa: SLF001
        if not self._auth.access_key_id:
            return []

        region_id = region or self._auth.region
        endpoint = _FC_ENDPOINT_TEMPLATE.format(region=region_id)

        try:
            config = self._auth.build_config(endpoint)
            client = FcClient(config)
        except Exception as exc:
            logger.debug("FC client init failed for region %s: %s", region_id, exc)
            return []

        resources: list[Resource] = []
        next_token: str | None = None

        try:
            while True:
                req = fc_models.ListFunctionsRequest(
                    limit=100,
                    next_token=next_token,
                )
                response = client.list_functions(req)
                body = response.body
                functions = getattr(body, "functions", []) or []
                for fn in functions:
                    resources.append(self._map_function(fn, region_id))

                next_token = getattr(body, "next_token", None)
                if not next_token:
                    break
        except Exception as exc:
            logger.debug("FC list_functions failed for region %s: %s", region_id, exc)

        return resources

    def _map_function(self, fn: Any, region: str) -> Resource:
        fn_name = str(getattr(fn, "function_name", "") or "")
        fn_arn = str(getattr(fn, "function_arn", "") or fn_name)
        state_raw = str(getattr(fn, "state", "") or "")
        runtime = str(getattr(fn, "runtime", "") or "")
        description = str(getattr(fn, "description", "") or "")
        timeout = str(getattr(fn, "timeout", "") or "")
        memory_size = str(getattr(fn, "memory_size", "") or "")
        cpu = str(getattr(fn, "cpu", "") or "")

        return Resource(
            id=fn_arn or fn_name,
            name=fn_name,
            resource_type=ResourceType.SERVERLESS,
            provider="alibaba",
            region=region,
            state=_FUNCTION_STATE_MAP.get(state_raw, ResourceState.UNKNOWN),
            metadata={
                "resource_subtype": "function",
                "runtime": runtime,
                "cpu": cpu,
                "memory_size": memory_size,
                "timeout": timeout,
                "description": description,
            },
        )
