"""GCP Cloud Storage bucket detailed information.

Retrieves bucket-level details beyond basic listing:
- Bucket IAM policy
- Lifecycle rules
- Versioning status
- Encryption configuration (CMEK)
- Size and object count
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from google.cloud import storage
from pydantic import BaseModel, Field

from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff
from spancloud.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from spancloud.providers.gcp.auth import GCPAuth

logger = get_logger(__name__)

_GCS_LIMITER = RateLimiter(calls_per_second=5.0, max_concurrency=10)


class LifecycleRule(BaseModel):
    """GCS lifecycle rule summary."""

    action: str = ""
    storage_class: str = ""
    age_days: int | None = None
    condition: str = ""


class BucketDetails(BaseModel):
    """Comprehensive details for a single GCS bucket."""

    name: str
    location: str = ""
    location_type: str = ""
    storage_class: str = ""
    versioning: bool = False
    encryption: str = ""
    public_access_prevention: str = ""
    uniform_access: bool = False
    iam_bindings: list[str] = Field(default_factory=list)
    lifecycle_rules: list[LifecycleRule] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)
    logging_bucket: str = ""
    object_count: str = ""
    total_size: str = ""
    created: str = ""


class GCSDetailAnalyzer:
    """Retrieves detailed GCS bucket configuration.

    Fetches IAM, lifecycle, encryption, and size information
    with rate limiting.
    """

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def get_bucket_details(self, bucket_name: str) -> BucketDetails:
        """Get comprehensive details for a single GCS bucket.

        Args:
            bucket_name: The GCS bucket name.

        Returns:
            BucketDetails with full configuration.
        """
        project = self._auth.project_id
        client = storage.Client(
            project=project,
            credentials=self._auth.credentials,
        )

        async with _GCS_LIMITER:
            bucket = await asyncio.to_thread(client.get_bucket, bucket_name)

        # Fetch IAM and size in parallel
        iam_task = asyncio.create_task(self._get_iam_bindings(bucket))
        size_task = asyncio.create_task(self._get_bucket_size(client, bucket_name))

        iam_bindings = await iam_task
        size_info = await size_task

        # Lifecycle rules
        lifecycle_rules = self._parse_lifecycle(bucket)

        # Encryption
        encryption = "Google-managed"
        if bucket.default_kms_key_name:
            key_short = bucket.default_kms_key_name.rsplit("/", 1)[-1]
            encryption = f"CMEK ({key_short})"

        # Versioning
        versioning = bucket.versioning_enabled or False

        # Uniform bucket-level access
        iam_config = bucket.iam_configuration or {}
        uniform = False
        pap = ""
        if hasattr(iam_config, "uniform_bucket_level_access_enabled"):
            uniform = iam_config.uniform_bucket_level_access_enabled or False
        if hasattr(iam_config, "public_access_prevention"):
            pap = iam_config.public_access_prevention or ""

        # Logging
        logging_bucket = ""
        if bucket.logging and bucket.logging.get("logBucket"):
            logging_bucket = bucket.logging["logBucket"]

        return BucketDetails(
            name=bucket_name,
            location=bucket.location or "",
            location_type=bucket.location_type or "",
            storage_class=bucket.storage_class or "",
            versioning=versioning,
            encryption=encryption,
            public_access_prevention=pap,
            uniform_access=uniform,
            iam_bindings=iam_bindings,
            lifecycle_rules=lifecycle_rules,
            labels=dict(bucket.labels) if bucket.labels else {},
            logging_bucket=logging_bucket,
            object_count=size_info.get("object_count", ""),
            total_size=size_info.get("total_size", ""),
            created=str(bucket.time_created) if bucket.time_created else "",
        )

    async def _get_iam_bindings(self, bucket: Any) -> list[str]:
        """Get IAM bindings as human-readable strings."""
        try:
            async with _GCS_LIMITER:
                policy = await asyncio.to_thread(bucket.get_iam_policy)

            bindings: list[str] = []
            for binding in policy.bindings:
                role = binding.get("role", "")
                members = binding.get("members", set())
                for member in list(members)[:3]:
                    bindings.append(f"{role} → {member}")
                if len(members) > 3:
                    bindings.append(f"{role} → (+{len(members) - 3} more)")
            return bindings
        except Exception as exc:
            logger.debug("Could not fetch IAM for bucket: %s", exc)
            return []

    async def _get_bucket_size(
        self, client: Any, bucket_name: str
    ) -> dict[str, str]:
        """Get bucket size and object count by listing all objects.

        Note: For large buckets this can be slow. We limit to counting
        and summing sizes without fetching object content.
        """
        try:
            def _count() -> tuple[int, int]:
                total_size = 0
                count = 0
                blobs = client.list_blobs(bucket_name, page_size=1000)
                for blob in blobs:
                    count += 1
                    total_size += blob.size or 0
                    # Safety: stop counting after 100k to avoid runaway
                    if count >= 100_000:
                        break
                return count, total_size

            async with _GCS_LIMITER:
                count, total_size = await asyncio.to_thread(_count)

            # Format size
            if total_size > 1_073_741_824:
                size_str = f"{total_size / 1_073_741_824:,.2f} GB"
            elif total_size > 1_048_576:
                size_str = f"{total_size / 1_048_576:,.2f} MB"
            elif total_size > 0:
                size_str = f"{total_size / 1024:,.2f} KB"
            else:
                size_str = "0 B"

            count_str = f"{count:,}"
            if count >= 100_000:
                count_str += "+"

            return {"total_size": size_str, "object_count": count_str}
        except Exception as exc:
            logger.debug("Could not count bucket objects: %s", exc)
            return {}

    def _parse_lifecycle(self, bucket: Any) -> list[LifecycleRule]:
        """Parse lifecycle rules from bucket metadata."""
        rules: list[LifecycleRule] = []
        lifecycle = bucket.lifecycle_rules or []

        for rule_data in lifecycle:
            action = rule_data.get("action", {})
            condition = rule_data.get("condition", {})

            action_type = action.get("type", "")
            storage_class = action.get("storageClass", "")
            age = condition.get("age")

            # Build a human-readable condition string
            cond_parts: list[str] = []
            if age is not None:
                cond_parts.append(f"age >= {age}d")
            if condition.get("isLive") is not None:
                cond_parts.append(
                    "live" if condition["isLive"] else "noncurrent"
                )
            if condition.get("matchesStorageClass"):
                cond_parts.append(
                    f"class in {condition['matchesStorageClass']}"
                )

            rules.append(LifecycleRule(
                action=action_type,
                storage_class=storage_class,
                age_days=age,
                condition=" AND ".join(cond_parts) if cond_parts else "",
            ))

        return rules
