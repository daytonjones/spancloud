"""Alibaba Cloud authentication — AccessKey ID + Secret.

Uses the Tea-based alibabacloud_* SDKs, which take a Config object
with access_key_id, access_key_secret, and endpoint per service.

Tokens are persisted in the Skyforge credential store after a
successful login (OS keychain or encrypted file fallback).
"""

from __future__ import annotations

import asyncio
from typing import Any

from skyforge.config import get_settings
from skyforge.utils.logging import get_logger

logger = get_logger(__name__)

# Region string → endpoint pattern helpers
_ECS_ENDPOINT = "ecs.{region}.aliyuncs.com"
_VPC_ENDPOINT = "vpc.{region}.aliyuncs.com"
_RDS_ENDPOINT = "rds.{region}.aliyuncs.com"
_CS_ENDPOINT = "cs.{region}.aliyuncs.com"
_SLB_ENDPOINT = "slb.{region}.aliyuncs.com"
_ALIDNS_ENDPOINT = "alidns.aliyuncs.com"
_BSS_ENDPOINT = "business.aliyuncs.com"
_CMS_ENDPOINT = "metrics.{region}.aliyuncs.com"


class AlibabaAuth:
    """Manages Alibaba AccessKey credentials + per-service clients."""

    def __init__(self) -> None:
        self._access_key_id: str = ""
        self._access_key_secret: str = ""
        self._region: str = ""
        self._identity: dict[str, str] = {}

    @property
    def access_key_id(self) -> str:
        return self._access_key_id

    @property
    def region(self) -> str:
        return self._region

    def set_credentials(
        self, access_key_id: str, access_key_secret: str
    ) -> None:
        """Assign credentials in-memory (used by TUI auth modal)."""
        self._access_key_id = access_key_id
        self._access_key_secret = access_key_secret

    def _ensure_credentials(self) -> None:
        """Load credentials from settings → credential store if not set."""
        if self._access_key_id and self._access_key_secret:
            return

        settings = get_settings().alibaba
        if not self._region:
            self._region = settings.default_region

        if not self._access_key_id:
            self._access_key_id = settings.access_key_id
        if not self._access_key_secret:
            self._access_key_secret = settings.access_key_secret

        if self._access_key_id and self._access_key_secret:
            return

        # Fall back to the encrypted credential store
        from skyforge.utils import credentials

        stored_id = credentials.load("alibaba", "access_key_id")
        stored_secret = credentials.load("alibaba", "access_key_secret")
        if stored_id and stored_secret:
            self._access_key_id = stored_id
            self._access_key_secret = stored_secret

    def build_config(self, endpoint: str) -> Any:
        """Build a Tea-SDK Config object for the given endpoint."""
        from alibabacloud_tea_openapi import models as open_api_models

        self._ensure_credentials()
        return open_api_models.Config(
            access_key_id=self._access_key_id,
            access_key_secret=self._access_key_secret,
            endpoint=endpoint,
        )

    def ecs_config(self, region: str | None = None) -> Any:
        return self.build_config(
            _ECS_ENDPOINT.format(region=region or self._region)
        )

    def vpc_config(self, region: str | None = None) -> Any:
        return self.build_config(
            _VPC_ENDPOINT.format(region=region or self._region)
        )

    def rds_config(self, region: str | None = None) -> Any:
        return self.build_config(
            _RDS_ENDPOINT.format(region=region or self._region)
        )

    def cs_config(self, region: str | None = None) -> Any:
        return self.build_config(
            _CS_ENDPOINT.format(region=region or self._region)
        )

    def slb_config(self, region: str | None = None) -> Any:
        return self.build_config(
            _SLB_ENDPOINT.format(region=region or self._region)
        )

    def alidns_config(self) -> Any:
        return self.build_config(_ALIDNS_ENDPOINT)

    def bss_config(self) -> Any:
        return self.build_config(_BSS_ENDPOINT)

    def cms_config(self, region: str | None = None) -> Any:
        return self.build_config(
            _CMS_ENDPOINT.format(region=region or self._region)
        )

    async def verify(self) -> bool:
        """Verify credentials by calling DescribeRegions on ECS."""
        self._ensure_credentials()
        if not self._access_key_id or not self._access_key_secret:
            logger.warning(
                "Alibaba credentials not configured. "
                "Run `skyforge auth login alibaba`."
            )
            return False

        try:
            identity = await asyncio.to_thread(self._sync_verify)
            self._identity = identity
            logger.info(
                "Alibaba authenticated (access_key_id=%s..., region=%s)",
                self._access_key_id[:6],
                self._region,
            )
            return True
        except Exception as exc:
            logger.warning("Alibaba authentication failed: %s", exc)
            return False

    def _sync_verify(self) -> dict[str, str]:
        from alibabacloud_ecs20140526 import models as ecs_models
        from alibabacloud_ecs20140526.client import Client as EcsClient

        client = EcsClient(self.ecs_config())
        req = ecs_models.DescribeRegionsRequest()
        response = client.describe_regions(req)
        regions = getattr(response.body, "regions", None)
        region_list = getattr(regions, "region", []) or [] if regions else []
        return {
            "region": self._region,
            "region_count": str(len(region_list)),
        }

    async def get_identity(self) -> dict[str, str]:
        return {
            "access_key_id": self._access_key_id[:6] + "..."
            if self._access_key_id
            else "",
            "region": self._region,
            "region_count": self._identity.get("region_count", ""),
        }
