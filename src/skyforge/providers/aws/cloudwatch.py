"""AWS CloudWatch alarm and metric discovery.

Surfaces active alarms and fetches key metrics (CPU, network, disk)
for EC2 instances. Uses GetMetricData for efficient batch queries.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff
from skyforge.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from skyforge.providers.aws.auth import AWSAuth

logger = get_logger(__name__)

# CloudWatch allows 400 GetMetricData TPS — be conservative
_CW_LIMITER = RateLimiter(calls_per_second=10.0, max_concurrency=10)


class AlarmInfo(BaseModel):
    """CloudWatch alarm summary."""

    name: str
    state: str
    severity: str = ""
    metric_name: str = ""
    namespace: str = ""
    threshold: str = ""
    description: str = ""
    updated_at: datetime | None = None
    dimensions: dict[str, str] = Field(default_factory=dict)


class MetricPoint(BaseModel):
    """Single metric data point."""

    timestamp: datetime
    value: float
    unit: str = ""


class ResourceMetrics(BaseModel):
    """Metrics for a specific resource."""

    resource_id: str
    resource_type: str
    metrics: dict[str, list[MetricPoint]] = Field(default_factory=dict)


class CloudWatchAnalyzer:
    """Fetches CloudWatch alarms and resource metrics.

    Uses batch APIs and rate limiting to minimize costs.
    """

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def list_alarms(
        self,
        region: str | None = None,
        state_filter: str | None = None,
    ) -> list[AlarmInfo]:
        """List CloudWatch alarms.

        Args:
            region: AWS region.
            state_filter: Filter by state (ALARM, OK, INSUFFICIENT_DATA). None = all.

        Returns:
            List of alarm summaries.
        """
        client = self._auth.client("cloudwatch", region=region)

        def _fetch() -> list[dict[str, Any]]:
            paginator = client.get_paginator("describe_alarms")
            params: dict[str, Any] = {}
            if state_filter:
                params["StateValue"] = state_filter
            pages = list(paginator.paginate(**params))
            alarms: list[dict[str, Any]] = []
            for page in pages:
                alarms.extend(page.get("MetricAlarms", []))
                alarms.extend(page.get("CompositeAlarms", []))
            return alarms

        async with _CW_LIMITER:
            raw_alarms = await asyncio.to_thread(_fetch)

        results: list[AlarmInfo] = []
        for alarm in raw_alarms:
            dims = {}
            for d in alarm.get("Dimensions", []):
                dims[d["Name"]] = d["Value"]

            threshold = alarm.get("Threshold")
            threshold_str = (
                f"{alarm.get('ComparisonOperator', '')} {threshold}" if threshold else ""
            )

            results.append(AlarmInfo(
                name=alarm.get("AlarmName", ""),
                state=alarm.get("StateValue", "UNKNOWN"),
                metric_name=alarm.get("MetricName", ""),
                namespace=alarm.get("Namespace", ""),
                threshold=threshold_str,
                description=alarm.get("AlarmDescription", ""),
                updated_at=alarm.get("StateUpdatedTimestamp"),
                dimensions=dims,
            ))

        logger.debug("Found %d CloudWatch alarms", len(results))
        return results

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def get_instance_metrics(
        self,
        instance_id: str,
        region: str | None = None,
        hours: int = 1,
    ) -> ResourceMetrics:
        """Get key metrics for an EC2 instance.

        Fetches CPU utilization, network in/out, and disk read/write
        using a single GetMetricData call for efficiency.

        Args:
            instance_id: EC2 instance ID.
            region: AWS region.
            hours: How many hours of data to retrieve.

        Returns:
            ResourceMetrics with metric time series.
        """
        client = self._auth.client("cloudwatch", region=region)
        end = datetime.now(UTC)
        start = end - timedelta(hours=hours)
        period = 300 if hours <= 3 else 3600  # 5-min or 1-hr granularity

        metric_queries = [
            {
                "Id": "cpu",
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/EC2",
                        "MetricName": "CPUUtilization",
                        "Dimensions": [
                            {"Name": "InstanceId", "Value": instance_id}
                        ],
                    },
                    "Period": period,
                    "Stat": "Average",
                },
            },
            {
                "Id": "net_in",
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/EC2",
                        "MetricName": "NetworkIn",
                        "Dimensions": [
                            {"Name": "InstanceId", "Value": instance_id}
                        ],
                    },
                    "Period": period,
                    "Stat": "Average",
                },
            },
            {
                "Id": "net_out",
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/EC2",
                        "MetricName": "NetworkOut",
                        "Dimensions": [
                            {"Name": "InstanceId", "Value": instance_id}
                        ],
                    },
                    "Period": period,
                    "Stat": "Average",
                },
            },
            {
                "Id": "disk_read",
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/EC2",
                        "MetricName": "DiskReadOps",
                        "Dimensions": [
                            {"Name": "InstanceId", "Value": instance_id}
                        ],
                    },
                    "Period": period,
                    "Stat": "Average",
                },
            },
            {
                "Id": "disk_write",
                "MetricStat": {
                    "Metric": {
                        "Namespace": "AWS/EC2",
                        "MetricName": "DiskWriteOps",
                        "Dimensions": [
                            {"Name": "InstanceId", "Value": instance_id}
                        ],
                    },
                    "Period": period,
                    "Stat": "Average",
                },
            },
        ]

        def _fetch() -> list[dict[str, Any]]:
            response = client.get_metric_data(
                MetricDataQueries=metric_queries,
                StartTime=start,
                EndTime=end,
            )
            return response.get("MetricDataResults", [])

        async with _CW_LIMITER:
            results = await asyncio.to_thread(_fetch)

        metrics: dict[str, list[MetricPoint]] = {}
        label_map = {
            "cpu": "CPUUtilization",
            "net_in": "NetworkIn",
            "net_out": "NetworkOut",
            "disk_read": "DiskReadOps",
            "disk_write": "DiskWriteOps",
        }

        for result in results:
            metric_id = result.get("Id", "")
            metric_name = label_map.get(metric_id, metric_id)
            timestamps = result.get("Timestamps", [])
            values = result.get("Values", [])

            points = [
                MetricPoint(timestamp=ts, value=val)
                for ts, val in zip(timestamps, values, strict=False)
            ]
            # Sort chronologically (CW returns reverse order)
            points.sort(key=lambda p: p.timestamp)
            if points:
                metrics[metric_name] = points

        return ResourceMetrics(
            resource_id=instance_id,
            resource_type="ec2_instance",
            metrics=metrics,
        )
