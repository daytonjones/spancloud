"""AWS S3 bucket detailed information.

Retrieves bucket-level details beyond basic listing:
- Bucket policy
- Lifecycle rules
- Versioning status
- Encryption configuration
- Size and object count (via CloudWatch)
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff
from skyforge.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from skyforge.providers.aws.auth import AWSAuth

logger = get_logger(__name__)

_S3_LIMITER = RateLimiter(calls_per_second=5.0, max_concurrency=10)


class LifecycleRule(BaseModel):
    """S3 lifecycle rule summary."""

    id: str = ""
    status: str = ""
    prefix: str = ""
    transitions: list[str] = Field(default_factory=list)
    expiration_days: int | None = None


class BucketDetails(BaseModel):
    """Comprehensive details for a single S3 bucket."""

    name: str
    region: str = ""
    versioning: str = ""
    encryption: str = ""
    public_access_block: dict[str, bool] = Field(default_factory=dict)
    policy_summary: str = ""
    lifecycle_rules: list[LifecycleRule] = Field(default_factory=list)
    object_count: str = ""
    total_size: str = ""
    storage_classes: dict[str, str] = Field(default_factory=dict)
    logging_enabled: bool = False
    logging_target: str = ""


class S3DetailAnalyzer:
    """Retrieves detailed S3 bucket configuration.

    Each bucket detail fetches multiple API calls (versioning, encryption,
    policy, lifecycle, etc.) — all rate-limited to avoid throttling.
    """

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def get_bucket_details(self, bucket_name: str) -> BucketDetails:
        """Get comprehensive details for a single S3 bucket.

        Args:
            bucket_name: The S3 bucket name.

        Returns:
            BucketDetails with full configuration.
        """
        s3 = self._auth.client("s3")

        # Fetch all properties in parallel
        tasks = [
            self._get_location(s3, bucket_name),
            self._get_versioning(s3, bucket_name),
            self._get_encryption(s3, bucket_name),
            self._get_public_access_block(s3, bucket_name),
            self._get_policy_summary(s3, bucket_name),
            self._get_lifecycle(s3, bucket_name),
            self._get_logging(s3, bucket_name),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        location = results[0] if not isinstance(results[0], Exception) else ""
        versioning = results[1] if not isinstance(results[1], Exception) else ""
        encryption = results[2] if not isinstance(results[2], Exception) else ""
        pab = results[3] if not isinstance(results[3], Exception) else {}
        policy = results[4] if not isinstance(results[4], Exception) else ""
        lifecycle = results[5] if not isinstance(results[5], Exception) else []
        logging_info = results[6] if not isinstance(results[6], Exception) else {}

        # Get size via CloudWatch (separate, optional)
        size_info = await self._get_bucket_size(bucket_name)

        return BucketDetails(
            name=bucket_name,
            region=location,
            versioning=versioning,
            encryption=encryption,
            public_access_block=pab,
            policy_summary=policy,
            lifecycle_rules=lifecycle,
            object_count=size_info.get("object_count", ""),
            total_size=size_info.get("total_size", ""),
            logging_enabled=bool(logging_info.get("target")),
            logging_target=logging_info.get("target", ""),
        )

    async def _get_location(self, s3: Any, bucket: str) -> str:
        async with _S3_LIMITER:
            resp = await asyncio.to_thread(
                s3.get_bucket_location, Bucket=bucket
            )
        return resp.get("LocationConstraint") or "us-east-1"

    async def _get_versioning(self, s3: Any, bucket: str) -> str:
        async with _S3_LIMITER:
            resp = await asyncio.to_thread(
                s3.get_bucket_versioning, Bucket=bucket
            )
        return resp.get("Status", "Disabled")

    async def _get_encryption(self, s3: Any, bucket: str) -> str:
        try:
            async with _S3_LIMITER:
                resp = await asyncio.to_thread(
                    s3.get_bucket_encryption, Bucket=bucket
                )
            rules = resp.get("ServerSideEncryptionConfiguration", {}).get("Rules", [])
            if rules:
                sse = rules[0].get("ApplyServerSideEncryptionByDefault", {})
                algo = sse.get("SSEAlgorithm", "")
                kms_key = sse.get("KMSMasterKeyID", "")
                if kms_key:
                    return f"{algo} (KMS: ...{kms_key[-12:]})"
                return algo
        except Exception as exc:
            if "ServerSideEncryptionConfigurationNotFoundError" in str(exc):
                return "None"
            raise
        return "Unknown"

    async def _get_public_access_block(
        self, s3: Any, bucket: str
    ) -> dict[str, bool]:
        try:
            async with _S3_LIMITER:
                resp = await asyncio.to_thread(
                    s3.get_public_access_block, Bucket=bucket
                )
            config = resp.get("PublicAccessBlockConfiguration", {})
            return {
                "block_public_acls": config.get("BlockPublicAcls", False),
                "ignore_public_acls": config.get("IgnorePublicAcls", False),
                "block_public_policy": config.get("BlockPublicPolicy", False),
                "restrict_public_buckets": config.get("RestrictPublicBuckets", False),
            }
        except Exception as exc:
            if "NoSuchPublicAccessBlockConfiguration" in str(exc):
                return {}
            raise

    async def _get_policy_summary(self, s3: Any, bucket: str) -> str:
        try:
            async with _S3_LIMITER:
                resp = await asyncio.to_thread(s3.get_bucket_policy, Bucket=bucket)
            policy = json.loads(resp.get("Policy", "{}"))
            stmts = policy.get("Statement", [])
            effects = [s.get("Effect", "") for s in stmts]
            return f"{len(stmts)} statement(s): {', '.join(set(effects))}"
        except Exception as exc:
            if "NoSuchBucketPolicy" in str(exc):
                return "No policy"
            raise

    async def _get_lifecycle(self, s3: Any, bucket: str) -> list[LifecycleRule]:
        try:
            async with _S3_LIMITER:
                resp = await asyncio.to_thread(
                    s3.get_bucket_lifecycle_configuration, Bucket=bucket
                )
            rules: list[LifecycleRule] = []
            for rule in resp.get("Rules", []):
                transitions = []
                for t in rule.get("Transitions", []):
                    days = t.get("Days", "?")
                    sc = t.get("StorageClass", "?")
                    transitions.append(f"→ {sc} after {days}d")

                exp_days = None
                if rule.get("Expiration", {}).get("Days"):
                    exp_days = rule["Expiration"]["Days"]

                rules.append(LifecycleRule(
                    id=rule.get("ID", ""),
                    status=rule.get("Status", ""),
                    prefix=rule.get("Filter", {}).get("Prefix", rule.get("Prefix", "")),
                    transitions=transitions,
                    expiration_days=exp_days,
                ))
            return rules
        except Exception as exc:
            if "NoSuchLifecycleConfiguration" in str(exc):
                return []
            raise

    async def _get_logging(self, s3: Any, bucket: str) -> dict[str, str]:
        try:
            async with _S3_LIMITER:
                resp = await asyncio.to_thread(
                    s3.get_bucket_logging, Bucket=bucket
                )
            logging_config = resp.get("LoggingEnabled", {})
            return {"target": logging_config.get("TargetBucket", "")}
        except Exception:
            return {}

    async def _get_bucket_size(self, bucket: str) -> dict[str, str]:
        """Get bucket size and object count from CloudWatch (S3 daily metrics)."""
        try:
            from datetime import UTC, datetime, timedelta

            cw = self._auth.client("cloudwatch")
            end = datetime.now(UTC)
            start = end - timedelta(days=2)

            def _fetch_metric(metric_name: str, storage_type: str) -> float:
                resp = cw.get_metric_statistics(
                    Namespace="AWS/S3",
                    MetricName=metric_name,
                    Dimensions=[
                        {"Name": "BucketName", "Value": bucket},
                        {"Name": "StorageType", "Value": storage_type},
                    ],
                    StartTime=start,
                    EndTime=end,
                    Period=86400,
                    Statistics=["Average"],
                )
                points = resp.get("Datapoints", [])
                if points:
                    return points[-1].get("Average", 0)
                return 0

            async with _S3_LIMITER:
                size_bytes = await asyncio.to_thread(
                    _fetch_metric, "BucketSizeBytes", "StandardStorage"
                )
            async with _S3_LIMITER:
                obj_count = await asyncio.to_thread(
                    _fetch_metric, "NumberOfObjects", "AllStorageTypes"
                )

            # Format size
            if size_bytes > 1_073_741_824:
                size_str = f"{size_bytes / 1_073_741_824:,.2f} GB"
            elif size_bytes > 1_048_576:
                size_str = f"{size_bytes / 1_048_576:,.2f} MB"
            elif size_bytes > 0:
                size_str = f"{size_bytes / 1024:,.2f} KB"
            else:
                size_str = "0 B"

            return {
                "total_size": size_str,
                "object_count": f"{int(obj_count):,}",
            }
        except Exception as exc:
            logger.debug("Could not fetch bucket size for %s: %s", bucket, exc)
            return {}
