"""OCI monitoring alarms and instance metrics (via oci.monitoring.MonitoringClient)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from spancloud.utils.logging import get_logger
from spancloud.providers.oci._retry import OCI_RETRY, OCI_RETRY_SLOW

if TYPE_CHECKING:
    from spancloud.providers.oci.auth import OCIAuth

logger = get_logger(__name__)


class AlertInfo(BaseModel):
    """OCI monitoring alarm summary (GCP AlertInfo-compatible)."""

    name: str
    display_name: str = ""
    enabled: bool = True
    conditions_count: int = 1
    notification_channels: int = 0
    combiner: str = ""


class MetricPoint(BaseModel):
    """A single timestamped metric data point."""

    timestamp: datetime
    value: float


class ResourceMetrics(BaseModel):
    """Metrics for a single OCI compute instance."""

    resource_id: str
    resource_type: str = "compute_instance"
    metrics: dict[str, list[MetricPoint]] = Field(default_factory=dict)


# OCI Monitoring metric definitions: (metric_name, namespace)
_INSTANCE_METRICS: list[tuple[str, str]] = [
    ("CpuUtilization", "oci_computeagent"),
    ("MemoryUtilization", "oci_computeagent"),
    ("NetworksBytesIn", "oci_computeagent"),
    ("NetworksBytesOut", "oci_computeagent"),
    ("DiskBytesRead", "oci_computeagent"),
    ("DiskBytesWritten", "oci_computeagent"),
]


class OCIMonitoringAnalyzer:
    """Fetches OCI monitoring alarms and instance metrics."""

    def __init__(self, auth: OCIAuth) -> None:
        self._auth = auth

    @OCI_RETRY_SLOW
    async def list_alert_policies(self) -> list[AlertInfo]:
        return await asyncio.to_thread(self._sync_list)

    def _sync_list(self) -> list[AlertInfo]:
        import oci

        compartment = self._auth.compartment_id
        if not compartment:
            return []

        try:
            client = oci.monitoring.MonitoringClient(self._auth.config)
        except Exception as exc:
            logger.debug("MonitoringClient init failed: %s", exc)
            return []

        results: list[AlertInfo] = []
        page: str | None = None
        try:
            while True:
                r = client.list_alarms(compartment_id=compartment, page=page)
                for alarm in r.data or []:
                    results.append(self._map_alarm(alarm))
                page = r.next_page
                if not page:
                    break
        except Exception as exc:
            logger.debug("OCI alarm list failed: %s", exc)
        return results

    def _map_alarm(self, alarm: Any) -> AlertInfo:
        severity = str(getattr(alarm, "severity", "") or "")
        namespace = getattr(alarm, "namespace", "") or ""
        combiner = " | ".join(p for p in (severity, namespace) if p)
        destinations = getattr(alarm, "destinations", None) or []
        return AlertInfo(
            name=alarm.id,
            display_name=getattr(alarm, "display_name", "") or alarm.id,
            enabled=bool(getattr(alarm, "is_enabled", True)),
            conditions_count=1,
            notification_channels=len(destinations),
            combiner=combiner or "—",
        )

    @OCI_RETRY
    async def get_instance_metrics(
        self,
        instance_id: str,
        region: str | None = None,
        hours: int = 1,
    ) -> ResourceMetrics:
        """Fetch compute instance metrics from OCI Monitoring.

        Args:
            instance_id: The OCID of the compute instance.
            region: Optional region override.
            hours: Number of hours of history to fetch (default 1).

        Returns:
            ResourceMetrics with per-metric time series data.
        """
        return await asyncio.to_thread(
            self._sync_get_instance_metrics, instance_id, region, hours
        )

    def _sync_get_instance_metrics(
        self,
        instance_id: str,
        region: str | None,
        hours: int,
    ) -> ResourceMetrics:
        import oci

        config = dict(self._auth.config)
        if region:
            config["region"] = region

        compartment = self._auth.compartment_id
        if not compartment:
            logger.debug("No OCI compartment_id configured — skipping metrics")
            return ResourceMetrics(resource_id=instance_id)

        try:
            client = oci.monitoring.MonitoringClient(config)
        except Exception as exc:
            logger.debug("MonitoringClient init failed: %s", exc)
            return ResourceMetrics(resource_id=instance_id)

        end = datetime.now(UTC)
        start = end - timedelta(hours=hours)

        collected: dict[str, list[MetricPoint]] = {}

        for metric_name, namespace in _INSTANCE_METRICS:
            query = (
                f'{metric_name}[1m]{{resourceId="{instance_id}"}}.mean()'
            )
            request = oci.monitoring.models.SummarizeMetricsDataDetails(
                namespace=namespace,
                query=query,
                start_time=start.isoformat(),
                end_time=end.isoformat(),
                resolution="1m",
            )
            try:
                response = client.summarize_metrics_data(
                    compartment_id=compartment,
                    summarize_metrics_data_details=request,
                )
                points: list[MetricPoint] = []
                for metric_data in response.data or []:
                    for dp in getattr(metric_data, "aggregated_datapoints", None) or []:
                        ts = getattr(dp, "timestamp", None)
                        val = getattr(dp, "value", None)
                        if ts is not None and val is not None:
                            points.append(
                                MetricPoint(timestamp=ts, value=float(val))
                            )
                if points:
                    collected[metric_name] = sorted(
                        points, key=lambda p: p.timestamp
                    )
            except Exception as exc:
                logger.debug(
                    "OCI metric %s for instance %s failed: %s",
                    metric_name,
                    instance_id,
                    exc,
                )

        return ResourceMetrics(resource_id=instance_id, metrics=collected)
