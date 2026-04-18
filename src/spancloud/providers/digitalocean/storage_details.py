"""DigitalOcean Spaces bucket detailed information.

DO Spaces is S3-compatible. Spaces use separate access/secret key credentials
(not the API token), so this module attempts to load them from the keychain or
environment variables.

Credential lookup order:
1. Env vars  DO_SPACES_KEY  and  DO_SPACES_SECRET
2. spancloud credential store  load("digitalocean_spaces", "key")  /  "secret"
3. Graceful degradation — returns SpacesDetails with an access_note explaining
   the missing credentials rather than raising.
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff
from spancloud.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from spancloud.providers.digitalocean.auth import DigitalOceanAuth

logger = get_logger(__name__)

_SPACES_LIMITER = RateLimiter(calls_per_second=5.0, max_concurrency=10)

_SPACES_ENDPOINT_TEMPLATE = "https://{region}.digitaloceanspaces.com"


class LifecycleRule(BaseModel):
    """Spaces lifecycle rule summary."""

    id: str = ""
    status: str = ""
    prefix: str = ""
    transitions: list[str] = Field(default_factory=list)
    expiration_days: int | None = None


class SpacesDetails(BaseModel):
    """Comprehensive details for a single DO Spaces bucket."""

    name: str
    region: str = ""
    versioning: str = ""
    cors_rules_count: int = 0
    lifecycle_rules: list[LifecycleRule] = Field(default_factory=list)
    acl: str = ""
    object_count: str = ""
    total_size: str = ""
    access_note: str = ""


class SpacesDetailAnalyzer:
    """Retrieves detailed DO Spaces bucket configuration using the S3-compatible API.

    Spaces credentials (access key + secret) are separate from the DO API token.
    If they are not found, a minimal SpacesDetails is returned with an explanatory
    access_note instead of raising an error.
    """

    def __init__(self, auth: DigitalOceanAuth) -> None:
        self._auth = auth

    def _load_spaces_credentials(self) -> tuple[str, str]:
        """Return (access_key, secret_key) or ('', '') if not configured."""
        # 1. Environment variables
        key = os.environ.get("DO_SPACES_KEY", "")
        secret = os.environ.get("DO_SPACES_SECRET", "")
        if key and secret:
            logger.debug("DO Spaces credentials loaded from environment variables")
            return key, secret

        # 2. spancloud credential store
        try:
            from spancloud.utils import credentials

            stored_key = credentials.load("digitalocean_spaces", "key")
            stored_secret = credentials.load("digitalocean_spaces", "secret")
            if stored_key and stored_secret:
                logger.debug("DO Spaces credentials loaded from credential store")
                return stored_key, stored_secret
        except Exception as exc:
            logger.debug("Could not load DO Spaces credentials from store: %s", exc)

        return "", ""

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def get_bucket_details(
        self, bucket_name: str, region: str
    ) -> SpacesDetails:
        """Get comprehensive details for a single Spaces bucket.

        Args:
            bucket_name: The Spaces bucket name.
            region: The region slug where the bucket lives (e.g., 'nyc3', 'ams3').

        Returns:
            SpacesDetails with configuration; access_note set if credentials
            were not available.
        """
        access_key, secret_key = self._load_spaces_credentials()

        if not access_key or not secret_key:
            logger.debug(
                "DO Spaces credentials not available — returning minimal details "
                "for bucket '%s'",
                bucket_name,
            )
            return SpacesDetails(
                name=bucket_name,
                region=region,
                access_note=(
                    "Spaces credentials not configured (separate from API token). "
                    "Set DO_SPACES_KEY / DO_SPACES_SECRET or run "
                    "'spancloud auth login digitalocean-spaces'."
                ),
            )

        endpoint_url = _SPACES_ENDPOINT_TEMPLATE.format(region=region)

        try:
            import boto3
            from botocore.config import Config as BotoConfig

            s3 = boto3.client(
                "s3",
                region_name=region,
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                config=BotoConfig(signature_version="s3v4"),
            )
        except ImportError:
            logger.debug("boto3 not available — cannot fetch Spaces details")
            return SpacesDetails(
                name=bucket_name,
                region=region,
                access_note="boto3 package is required for Spaces detail fetching",
            )

        # Fetch all properties in parallel
        tasks = [
            self._get_versioning(s3, bucket_name),
            self._get_cors_count(s3, bucket_name),
            self._get_lifecycle(s3, bucket_name),
            self._get_acl(s3, bucket_name),
            self._get_bucket_size(s3, bucket_name),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        versioning: str = results[0] if not isinstance(results[0], BaseException) else ""  # type: ignore[assignment]
        cors_count: int = results[1] if not isinstance(results[1], BaseException) else 0  # type: ignore[assignment]
        lifecycle: list[LifecycleRule] = results[2] if not isinstance(results[2], BaseException) else []  # type: ignore[assignment]
        acl: str = results[3] if not isinstance(results[3], BaseException) else ""  # type: ignore[assignment]
        size_info: dict[str, str] = results[4] if not isinstance(results[4], BaseException) else {}  # type: ignore[assignment]

        return SpacesDetails(
            name=bucket_name,
            region=region,
            versioning=versioning,
            cors_rules_count=cors_count,
            lifecycle_rules=lifecycle,
            acl=acl,
            object_count=size_info.get("object_count", ""),
            total_size=size_info.get("total_size", ""),
        )

    async def _get_versioning(self, s3: Any, bucket: str) -> str:
        async with _SPACES_LIMITER:
            resp = await asyncio.to_thread(s3.get_bucket_versioning, Bucket=bucket)
        return resp.get("Status", "Disabled") or "Disabled"

    async def _get_cors_count(self, s3: Any, bucket: str) -> int:
        try:
            async with _SPACES_LIMITER:
                resp = await asyncio.to_thread(
                    s3.get_bucket_cors, Bucket=bucket
                )
            return len(resp.get("CORSRules", []))
        except Exception as exc:
            if "NoSuchCORSConfiguration" in str(exc):
                return 0
            raise

    async def _get_lifecycle(self, s3: Any, bucket: str) -> list[LifecycleRule]:
        try:
            async with _SPACES_LIMITER:
                resp = await asyncio.to_thread(
                    s3.get_bucket_lifecycle_configuration, Bucket=bucket
                )
            rules: list[LifecycleRule] = []
            for rule in resp.get("Rules", []):
                transitions: list[str] = []
                for t in rule.get("Transitions", []):
                    days = t.get("Days", "?")
                    sc = t.get("StorageClass", "?")
                    transitions.append(f"-> {sc} after {days}d")

                exp_days: int | None = None
                expiration = rule.get("Expiration") or {}
                if expiration.get("Days"):
                    exp_days = expiration["Days"]

                rules.append(LifecycleRule(
                    id=rule.get("ID", ""),
                    status=rule.get("Status", ""),
                    prefix=(rule.get("Filter") or {}).get(
                        "Prefix", rule.get("Prefix", "")
                    ),
                    transitions=transitions,
                    expiration_days=exp_days,
                ))
            return rules
        except Exception as exc:
            if "NoSuchLifecycleConfiguration" in str(exc):
                return []
            raise

    async def _get_acl(self, s3: Any, bucket: str) -> str:
        try:
            async with _SPACES_LIMITER:
                resp = await asyncio.to_thread(s3.get_bucket_acl, Bucket=bucket)
            grants = resp.get("Grants", [])
            public_grants = [
                g for g in grants
                if (g.get("Grantee") or {}).get("URI", "").endswith(
                    "AllUsers"
                )
            ]
            return "public-read" if public_grants else "private"
        except Exception as exc:
            logger.debug("Could not fetch ACL for bucket %s: %s", bucket, exc)
            return ""

    async def _get_bucket_size(self, s3: Any, bucket: str) -> dict[str, str]:
        """Estimate bucket size by listing objects (up to 100k)."""
        try:
            def _count() -> tuple[int, int]:
                paginator = s3.get_paginator("list_objects_v2")
                total_size = 0
                count = 0
                for page in paginator.paginate(Bucket=bucket, PaginationConfig={"PageSize": 1000}):
                    for obj in page.get("Contents", []):
                        count += 1
                        total_size += obj.get("Size", 0)
                        if count >= 100_000:
                            return count, total_size
                return count, total_size

            async with _SPACES_LIMITER:
                count, total_bytes = await asyncio.to_thread(_count)

            if total_bytes > 1_073_741_824:
                size_str = f"{total_bytes / 1_073_741_824:,.2f} GB"
            elif total_bytes > 1_048_576:
                size_str = f"{total_bytes / 1_048_576:,.2f} MB"
            elif total_bytes > 0:
                size_str = f"{total_bytes / 1024:,.2f} KB"
            else:
                size_str = "0 B"

            count_str = f"{count:,}"
            if count >= 100_000:
                count_str += "+"

            return {"total_size": size_str, "object_count": count_str}
        except Exception as exc:
            logger.debug("Could not count Spaces objects in %s: %s", bucket, exc)
            return {}
