"""GCP Cloud Monitoring alert policy and metric discovery.

Surfaces active alerting policies and fetches key metrics (CPU, disk, network)
for GCE instances. Uses the Monitoring v3 API.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from google.cloud import monitoring_v3
from pydantic import BaseModel, Field

from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff
from skyforge.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from skyforge.providers.gcp.auth import GCPAuth

logger = get_logger(__name__)

_MON_LIMITER = RateLimiter(calls_per_second=5.0, max_concurrency=5)


class AlertInfo(BaseModel):
    """Cloud Monitoring alert policy summary."""

    name: str
    display_name: str = ""
    enabled: bool = True
    conditions_count: int = 0
    notification_channels: int = 0
    combiner: str = ""


class MetricPoint(BaseModel):
    """Single metric data point."""

    timestamp: datetime
    value: float


class ResourceMetrics(BaseModel):
    """Metrics for a specific GCE instance."""

    resource_id: str
    resource_type: str = "gce_instance"
    metrics: dict[str, list[MetricPoint]] = Field(default_factory=dict)


class CloudMonitoringAnalyzer:
    """Fetches Cloud Monitoring alert policies and GCE instance metrics."""

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def list_alert_policies(self) -> list[AlertInfo]:
        """List all alerting policies in the project.

        Returns:
            List of alert policy summaries.
        """
        project = self._auth.project_id
        if not project:
            return []

        client = monitoring_v3.AlertPolicyServiceClient(
            credentials=self._auth.credentials
        )

        def _fetch() -> list[Any]:
            name = f"projects/{project}"
            return list(client.list_alert_policies(name=name))

        async with _MON_LIMITER:
            policies = await asyncio.to_thread(_fetch)

        results: list[AlertInfo] = []
        for policy in policies:
            results.append(AlertInfo(
                name=(policy.name or "").rsplit("/", 1)[-1],
                display_name=policy.display_name or "",
                enabled=policy.enabled.value if policy.enabled else True,
                conditions_count=len(policy.conditions or []),
                notification_channels=len(policy.notification_channels or []),
                combiner=policy.combiner.name if policy.combiner else "",
            ))

        logger.debug("Found %d alert policies", len(results))
        return results

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def get_instance_metrics(
        self,
        instance_id: str,
        zone: str,
        hours: int = 1,
    ) -> ResourceMetrics:
        """Get key metrics for a GCE instance.

        Fetches CPU utilization, disk read/write, and network bytes
        from the Monitoring API.

        Args:
            instance_id: GCE instance ID (numeric).
            zone: Zone where the instance runs.
            hours: Hours of data to retrieve.

        Returns:
            ResourceMetrics with metric time series.
        """
        project = self._auth.project_id
        if not project:
            return ResourceMetrics(resource_id=instance_id)

        client = monitoring_v3.MetricServiceClient(
            credentials=self._auth.credentials
        )

        end = datetime.now(UTC)
        start = end - timedelta(hours=hours)
        interval = monitoring_v3.TimeInterval(
            start_time=start,
            end_time=end,
        )

        # Metric types to fetch
        metric_types = {
            "CPUUtilization": "compute.googleapis.com/instance/cpu/utilization",
            "DiskReadBytes": "compute.googleapis.com/instance/disk/read_bytes_count",
            "DiskWriteBytes": "compute.googleapis.com/instance/disk/write_bytes_count",
            "NetworkReceived": "compute.googleapis.com/instance/network/received_bytes_count",
            "NetworkSent": "compute.googleapis.com/instance/network/sent_bytes_count",
        }

        metrics: dict[str, list[MetricPoint]] = {}
        project_name = f"projects/{project}"

        for label, metric_type in metric_types.items():
            try:
                async with _MON_LIMITER:
                    points = await self._fetch_metric(
                        client, project_name, metric_type,
                        instance_id, zone, interval,
                    )
                if points:
                    metrics[label] = points
            except Exception as exc:
                logger.debug("Could not fetch %s for %s: %s", label, instance_id, exc)

        return ResourceMetrics(resource_id=instance_id, metrics=metrics)

    async def _fetch_metric(
        self,
        client: monitoring_v3.MetricServiceClient,
        project_name: str,
        metric_type: str,
        instance_id: str,
        zone: str,
        interval: monitoring_v3.TimeInterval,
    ) -> list[MetricPoint]:
        """Fetch a single metric time series."""

        def _call() -> list[MetricPoint]:
            filter_str = (
                f'metric.type = "{metric_type}" AND '
                f'resource.labels.instance_id = "{instance_id}" AND '
                f'resource.labels.zone = "{zone}"'
            )
            results = client.list_time_series(
                request={
                    "name": project_name,
                    "filter": filter_str,
                    "interval": interval,
                    "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                }
            )
            points: list[MetricPoint] = []
            for ts in results:
                for point in ts.points:
                    value = point.value.double_value
                    timestamp = point.interval.end_time
                    points.append(MetricPoint(timestamp=timestamp, value=value))
            # Sort chronologically (API returns newest first)
            points.sort(key=lambda p: p.timestamp)
            return points

        return await asyncio.to_thread(_call)
