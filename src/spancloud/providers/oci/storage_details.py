"""OCI Object Storage bucket detailed information.

Retrieves bucket-level details beyond basic listing:
- Storage tier and versioning
- Auto-tiering and encryption
- Public access type
- Lifecycle rules
- Approximate object count and total size
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from spancloud.utils.logging import get_logger
from spancloud.providers.oci._retry import OCI_RETRY, OCI_RETRY_SLOW

if TYPE_CHECKING:
    from datetime import datetime

    from spancloud.providers.oci.auth import OCIAuth

logger = get_logger(__name__)


class OCIBucketDetails(BaseModel):
    """Comprehensive details for a single OCI Object Storage bucket."""

    name: str
    namespace: str = ""
    compartment_id: str = ""
    storage_tier: str = ""
    versioning: str = ""
    auto_tiering: str = ""
    encryption: str = ""
    public_access_type: str = ""
    lifecycle_rules: list[str] = Field(default_factory=list)
    object_count: str = ""
    total_size: str = ""
    created: datetime | None = None


class OCIStorageDetailAnalyzer:
    """Retrieves detailed OCI Object Storage bucket configuration.

    Uses ObjectStorageClient to fetch versioning, encryption, lifecycle
    policies, and approximate size metrics.
    """

    def __init__(self, auth: OCIAuth) -> None:
        self._auth = auth

    @OCI_RETRY_SLOW
    async def get_bucket_details(self, bucket_name: str) -> OCIBucketDetails:
        """Get comprehensive details for a single OCI Object Storage bucket.

        Args:
            bucket_name: The bucket name.

        Returns:
            OCIBucketDetails with full configuration.
        """
        return await asyncio.to_thread(self._sync_get_bucket_details, bucket_name)

    def _sync_get_bucket_details(self, bucket_name: str) -> OCIBucketDetails:
        import oci

        config = self._auth.config
        if not config:
            return OCIBucketDetails(name=bucket_name)

        try:
            client = oci.object_storage.ObjectStorageClient(config)
        except Exception as exc:
            logger.debug("ObjectStorageClient init failed: %s", exc)
            return OCIBucketDetails(name=bucket_name)

        # Fetch namespace
        try:
            namespace: str = client.get_namespace().data
        except Exception as exc:
            logger.debug("Could not fetch OCI namespace: %s", exc)
            return OCIBucketDetails(name=bucket_name)

        # Fetch full bucket details including size fields
        bucket: Any = None
        try:
            bucket = client.get_bucket(
                namespace_name=namespace,
                bucket_name=bucket_name,
                fields=["approximateCount", "approximateSize"],
            ).data
        except Exception as exc:
            logger.debug("get_bucket failed for %s: %s", bucket_name, exc)
            return OCIBucketDetails(name=bucket_name, namespace=namespace)

        # Extract encryption info
        kms_key = getattr(bucket, "kms_key_id", "") or ""
        encryption = (
            f"SSE-KMS (...{kms_key[-12:]})" if kms_key else "SSE (Oracle-managed)"
        )

        # Object count and size
        approx_count = getattr(bucket, "approximate_count", None)
        approx_size = getattr(bucket, "approximate_size", None)

        object_count = f"{int(approx_count):,}" if approx_count is not None else ""

        total_size = ""
        if approx_size is not None:
            size_bytes = int(approx_size)
            if size_bytes > 1_073_741_824:
                total_size = f"{size_bytes / 1_073_741_824:,.2f} GB"
            elif size_bytes > 1_048_576:
                total_size = f"{size_bytes / 1_048_576:,.2f} MB"
            elif size_bytes > 0:
                total_size = f"{size_bytes / 1024:,.2f} KB"
            else:
                total_size = "0 B"

        # Fetch lifecycle policy (single policy with multiple rules)
        lifecycle_rules: list[str] = []
        try:
            lc_response = client.get_object_lifecycle_policy(
                namespace_name=namespace, bucket_name=bucket_name
            )
            policy = lc_response.data if lc_response else None
            for rule in getattr(policy, "items", None) or []:
                name = getattr(rule, "name", "") or ""
                action = getattr(rule, "action", "") or ""
                time_amount = getattr(rule, "time_amount", "") or ""
                time_unit = getattr(rule, "time_unit", "") or ""
                is_enabled = getattr(rule, "is_enabled", True)
                status = "enabled" if is_enabled else "disabled"
                summary = f"{name}: {action} after {time_amount} {time_unit} ({status})"
                lifecycle_rules.append(summary.strip())
        except Exception as exc:
            logger.debug(
                "get_object_lifecycle_policy failed for %s: %s", bucket_name, exc
            )

        return OCIBucketDetails(
            name=getattr(bucket, "name", bucket_name) or bucket_name,
            namespace=namespace,
            compartment_id=getattr(bucket, "compartment_id", "") or "",
            storage_tier=getattr(bucket, "storage_tier", "") or "",
            versioning=getattr(bucket, "versioning", "") or "",
            auto_tiering=getattr(bucket, "auto_tiering", "") or "",
            encryption=encryption,
            public_access_type=getattr(bucket, "public_access_type", "") or "",
            lifecycle_rules=lifecycle_rules,
            object_count=object_count,
            total_size=total_size,
            created=getattr(bucket, "time_created", None),
        )
