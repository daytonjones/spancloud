"""Alibaba Cloud OSS (Object Storage Service) detailed bucket inspection.

Uses the oss2 library to fetch bucket-level configuration that is not
returned by the basic bucket listing.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from spancloud.utils.logging import get_logger

if TYPE_CHECKING:
    from spancloud.providers.alibaba.auth import AlibabaAuth

logger = get_logger(__name__)


class OSSBucketDetails(BaseModel):
    """Detailed configuration for a single OSS bucket."""

    name: str
    region: str
    acl: str = ""
    versioning: str = ""
    encryption: str = ""
    cors_rules: list[str] = Field(default_factory=list)
    lifecycle_rules: list[str] = Field(default_factory=list)
    object_count: int = 0
    total_size: int = 0
    logging_target: str = ""


class AlibabaStorageDetailAnalyzer:
    """Fetches detailed configuration for an Alibaba OSS bucket."""

    def __init__(self, auth: AlibabaAuth) -> None:
        self._auth = auth

    async def get_bucket_details(
        self, bucket_name: str, region: str
    ) -> OSSBucketDetails:
        return await asyncio.to_thread(
            self._sync_get_details, bucket_name, region
        )

    def _sync_get_details(
        self, bucket_name: str, region: str
    ) -> OSSBucketDetails:
        import oss2

        self._auth._ensure_credentials()  # noqa: SLF001
        if not self._auth.access_key_id:
            logger.debug(
                "No Alibaba credentials available for OSS detail fetch"
            )
            return OSSBucketDetails(name=bucket_name, region=region)

        endpoint = f"https://oss-{region}.aliyuncs.com"
        auth = oss2.Auth(
            self._auth.access_key_id,
            self._auth._access_key_secret,  # noqa: SLF001
        )
        bucket = oss2.Bucket(auth, endpoint, bucket_name)

        # ACL
        acl = ""
        try:
            result = bucket.get_bucket_acl()
            acl = str(getattr(result, "acl", "") or "")
        except Exception as exc:
            logger.debug("get_bucket_acl failed for %s: %s", bucket_name, exc)

        # Versioning
        versioning = ""
        try:
            result = bucket.get_bucket_versioning()
            versioning = str(getattr(result, "status", "") or "")
        except Exception as exc:
            logger.debug(
                "get_bucket_versioning failed for %s: %s", bucket_name, exc
            )

        # Encryption
        encryption = ""
        try:
            result = bucket.get_bucket_encryption()
            rule = getattr(result, "rule", None)
            if rule:
                apply_server_side_encryption = getattr(
                    rule, "apply_server_side_encryption_by_default", None
                )
                if apply_server_side_encryption:
                    sse_algorithm = str(
                        getattr(apply_server_side_encryption, "sse_algorithm", "")
                        or ""
                    )
                    encryption = sse_algorithm
        except Exception as exc:
            logger.debug(
                "get_bucket_encryption failed for %s: %s", bucket_name, exc
            )

        # CORS rules
        cors_rules: list[str] = []
        try:
            result = bucket.get_bucket_cors()
            rules = getattr(result, "rules", []) or []
            for rule in rules:
                allowed_origins = getattr(rule, "allowed_origins", []) or []
                cors_rules.append(
                    ",".join(str(o) for o in allowed_origins)
                )
        except Exception as exc:
            logger.debug(
                "get_bucket_cors failed for %s: %s", bucket_name, exc
            )

        # Lifecycle rules
        lifecycle_rules: list[str] = []
        try:
            result = bucket.get_bucket_lifecycle()
            rules = getattr(result, "rules", []) or []
            for rule in rules:
                rule_id = str(getattr(rule, "id", "") or "")
                status = str(getattr(rule, "status", "") or "")
                lifecycle_rules.append(f"{rule_id}:{status}" if rule_id else status)
        except Exception as exc:
            logger.debug(
                "get_bucket_lifecycle failed for %s: %s", bucket_name, exc
            )

        # Stats
        object_count = 0
        total_size = 0
        try:
            result = bucket.get_bucket_stat()
            object_count = int(getattr(result, "object_count", 0) or 0)
            total_size = int(getattr(result, "storage_size_in_bytes", 0) or 0)
        except Exception as exc:
            logger.debug(
                "get_bucket_stat failed for %s: %s", bucket_name, exc
            )

        # Logging
        logging_target = ""
        try:
            result = bucket.get_bucket_logging()
            logging_config = getattr(result, "logging_enabled", None)
            if logging_config:
                target_bucket = str(
                    getattr(logging_config, "target_bucket", "") or ""
                )
                target_prefix = str(
                    getattr(logging_config, "target_prefix", "") or ""
                )
                if target_bucket:
                    logging_target = (
                        f"{target_bucket}/{target_prefix}"
                        if target_prefix
                        else target_bucket
                    )
        except Exception as exc:
            logger.debug(
                "get_bucket_logging failed for %s: %s", bucket_name, exc
            )

        return OSSBucketDetails(
            name=bucket_name,
            region=region,
            acl=acl,
            versioning=versioning,
            encryption=encryption,
            cors_rules=cors_rules,
            lifecycle_rules=lifecycle_rules,
            object_count=object_count,
            total_size=total_size,
            logging_target=logging_target,
        )
