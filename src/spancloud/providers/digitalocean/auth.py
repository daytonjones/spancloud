"""DigitalOcean authentication and REST API client.

Uses the DigitalOcean API v2 with Bearer token authentication.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from spancloud.config import get_settings
from spancloud.utils.logging import get_logger
from spancloud.utils.throttle import RateLimiter

logger = get_logger(__name__)

_DO_BASE_URL = "https://api.digitalocean.com/v2"

# DO API: 5000 requests/hour = ~1.4 req/s sustained, 250 req burst
_DO_LIMITER = RateLimiter(calls_per_second=3.0, max_concurrency=5)


class DigitalOceanAuth:
    """Manages DigitalOcean API token authentication."""

    def __init__(self) -> None:
        self._token: str = ""
        self._account_info: dict[str, Any] = {}

    @property
    def token(self) -> str:
        """Return the current API token."""
        return self._token

    async def verify(self) -> bool:
        """Verify the DigitalOcean API token is valid.

        Returns:
            True if the token is valid and usable.
        """
        if not self._token:
            settings = get_settings().digitalocean
            self._token = settings.token

        if not self._token:
            # Try the encrypted credential store (saved by `auth login digitalocean`)
            from spancloud.utils import credentials

            stored = credentials.load("digitalocean", "token")
            if stored:
                self._token = stored
                logger.debug("Loaded DigitalOcean token from credential store")

        if not self._token:
            logger.warning(
                "DigitalOcean token not configured. "
                "Set SPANCLOUD_DIGITALOCEAN_TOKEN or run "
                "'spancloud auth login digitalocean'."
            )
            return False

        try:
            data = await self.get("/account")
            self._account_info = data.get("account", {})
            logger.info(
                "DigitalOcean authenticated for account '%s'",
                self._account_info.get("email", ""),
            )
            return True
        except Exception as exc:
            logger.warning("DigitalOcean authentication failed: %s", exc)
            return False

    async def get_identity(self) -> dict[str, str]:
        """Return details about the authenticated DO account."""
        return {
            "email": self._account_info.get("email", ""),
            "uuid": self._account_info.get("uuid", ""),
            "status": self._account_info.get("status", ""),
            "droplet_limit": str(self._account_info.get("droplet_limit", "")),
            "email_verified": str(self._account_info.get("email_verified", "")),
        }

    async def get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make a GET request to the DigitalOcean API."""
        async with _DO_LIMITER:
            return await asyncio.to_thread(self._sync_get, path, params)

    def _sync_get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Synchronous GET — runs in a thread."""
        url = f"{_DO_BASE_URL}{path}"
        headers = {"Authorization": f"Bearer {self._token}"}
        response = httpx.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    async def post(
        self, path: str, json_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make a POST request to the DigitalOcean API."""
        async with _DO_LIMITER:
            return await asyncio.to_thread(self._sync_post, path, json_data)

    def _sync_post(
        self, path: str, json_data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Synchronous POST — runs in a thread."""
        url = f"{_DO_BASE_URL}{path}"
        headers = {"Authorization": f"Bearer {self._token}"}
        response = httpx.post(url, headers=headers, json=json_data, timeout=30)
        response.raise_for_status()
        if response.status_code in (202, 204):
            return {}
        return response.json()

    async def get_paginated(
        self,
        path: str,
        result_key: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all pages from a paginated DO endpoint.

        Uses the 'links.pages.next' cursor for pagination.

        Returns:
            Combined list from all pages.
        """
        all_items: list[dict[str, Any]] = []
        query = dict(params or {})
        query.setdefault("per_page", 200)
        next_url: str | None = None

        while True:
            if next_url:
                # Next page URL is absolute — extract path + query
                # DO returns e.g. https://api.digitalocean.com/v2/droplets?page=2&per_page=200
                from urllib.parse import parse_qs, urlparse

                parsed = urlparse(next_url)
                path_only = parsed.path.replace("/v2", "", 1)
                query = {
                    k: v[0] for k, v in parse_qs(parsed.query).items()
                }
                data = await self.get(path_only, params=query)
            else:
                data = await self.get(path, params=query)

            items = data.get(result_key, [])
            if isinstance(items, list):
                all_items.extend(items)

            # Check for next page
            links = data.get("links", {})
            pages = links.get("pages", {}) if isinstance(links, dict) else {}
            next_url = pages.get("next") if isinstance(pages, dict) else None

            if not next_url:
                break

        return all_items
