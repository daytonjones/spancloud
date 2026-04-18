"""Vultr authentication and REST API client.

Uses the Vultr API v2 with Bearer token authentication.
All API calls go through the VultrClient which handles rate limiting,
retries, and pagination.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from spancloud.config import get_settings
from spancloud.utils.logging import get_logger
from spancloud.utils.throttle import RateLimiter

logger = get_logger(__name__)

_VULTR_BASE_URL = "https://api.vultr.com/v2"

# Vultr API: 3 requests/second for general, 1/s for some endpoints
_VULTR_LIMITER = RateLimiter(calls_per_second=3.0, max_concurrency=5)


class VultrAuth:
    """Manages Vultr API key authentication.

    The API key can be set via SPANCLOUD_VULTR_API_KEY environment variable
    or through the interactive login flow.
    """

    def __init__(self) -> None:
        self._api_key: str = ""
        self._account_info: dict[str, Any] = {}

    @property
    def api_key(self) -> str:
        """Return the current API key."""
        return self._api_key

    async def verify(self) -> bool:
        """Verify that the Vultr API key is valid.

        Uses the existing key if already set (e.g., from auth modal),
        otherwise reads from settings/environment.

        Returns:
            True if the API key is valid and usable.
        """
        if not self._api_key:
            settings = get_settings().vultr
            self._api_key = settings.api_key

        if not self._api_key:
            # Try the encrypted credential store (saved by `auth login vultr`)
            from spancloud.utils import credentials

            stored = credentials.load("vultr", "api_key")
            if stored:
                self._api_key = stored
                logger.debug("Loaded Vultr API key from credential store")

        if not self._api_key:
            logger.warning(
                "Vultr API key not configured. "
                "Set SPANCLOUD_VULTR_API_KEY or run 'spancloud auth login vultr'."
            )
            return False

        try:
            data = await self.get("/account")
            self._account_info = data.get("account", {})
            logger.info("Vultr authenticated for account '%s'", self._account_info.get("email", ""))
            return True
        except Exception as exc:
            logger.warning("Vultr authentication failed: %s", exc)
            return False

    async def get_identity(self) -> dict[str, str]:
        """Return details about the authenticated Vultr account."""
        return {
            "email": self._account_info.get("email", ""),
            "name": self._account_info.get("name", ""),
            "balance": str(self._account_info.get("balance", "")),
            "pending_charges": str(self._account_info.get("pending_charges", "")),
        }

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a GET request to the Vultr API.

        Args:
            path: API path (e.g., '/instances').
            params: Optional query parameters.

        Returns:
            Parsed JSON response.
        """
        async with _VULTR_LIMITER:
            return await asyncio.to_thread(self._sync_get, path, params)

    def _sync_get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Synchronous GET — runs in a thread."""
        url = f"{_VULTR_BASE_URL}{path}"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        response = httpx.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    async def post(self, path: str, json_data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a POST request to the Vultr API."""
        async with _VULTR_LIMITER:
            return await asyncio.to_thread(self._sync_post, path, json_data)

    def _sync_post(
        self, path: str, json_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Synchronous POST — runs in a thread."""
        url = f"{_VULTR_BASE_URL}{path}"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        response = httpx.post(url, headers=headers, json=json_data, timeout=30)
        response.raise_for_status()
        if response.status_code == 204:
            return {}
        return response.json()

    async def get_paginated(
        self, path: str, result_key: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch all pages from a paginated Vultr API endpoint.

        Args:
            path: API path.
            result_key: Key in the response containing the results list.
            params: Optional query parameters.

        Returns:
            Combined list from all pages.
        """
        all_items: list[dict[str, Any]] = []
        query = dict(params or {})
        query.setdefault("per_page", 100)

        while True:
            data = await self.get(path, params=query)
            items = data.get(result_key, [])
            all_items.extend(items)

            # Check for next page cursor
            meta = data.get("meta", {})
            links = meta.get("links", {})
            next_cursor = links.get("next", "")

            if not next_cursor or not items:
                break

            query["cursor"] = next_cursor

        return all_items
