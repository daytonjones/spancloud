"""DigitalOcean monitoring — alert policies and droplet metrics.

DO exposes droplet metric alerts (CPU, load, memory, disk, outbound bandwidth)
as "alert policies". Each policy targets a set of droplet IDs or tags and
fires notifications via email or Slack.

Metric time-series are available via /v2/monitoring/metrics/droplet/*.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.digitalocean.auth import DigitalOceanAuth

logger = get_logger(__name__)


class AlertInfo(BaseModel):
    """DigitalOcean alert policy summary.

    Shape kept compatible with GCP's AlertInfo so the TUI/CLI renderers
    can share code.
    """

    name: str
    display_name: str = ""
    enabled: bool = True
    conditions_count: int = 1
    notification_channels: int = 0
    combiner: str = ""


class MetricPoint(BaseModel):
    """Single metric data point."""

    timestamp: datetime
    value: float


class ResourceMetrics(BaseModel):
    """Metrics for a specific Droplet."""

    resource_id: str
    resource_type: str = "droplet"
    metrics: dict[str, list[MetricPoint]] = Field(default_factory=dict)


class DigitalOceanMonitoringAnalyzer:
    """Fetches DigitalOcean alert policies and Droplet metrics."""

    def __init__(self, auth: DigitalOceanAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def list_alert_policies(self) -> list[AlertInfo]:
        """List all alert policies in the account."""
        try:
            policies = await self._auth.get_paginated(
                "/monitoring/alerts", "policies"
            )
        except Exception as exc:
            logger.debug("DO alert policy list failed: %s", exc)
            return []

        results: list[AlertInfo] = []
        for p in policies:
            alerts = p.get("alerts") or {}
            emails = alerts.get("email") or []
            slack = alerts.get("slack") or []
            channel_count = len(emails) + len(slack)

            entity_count = len(p.get("entities") or [])
            tag_count = len(p.get("tags") or [])
            scope = (
                f"{entity_count} droplet(s)"
                if entity_count
                else f"{tag_count} tag(s)"
                if tag_count
                else "—"
            )

            results.append(
                AlertInfo(
                    name=p.get("uuid", ""),
                    display_name=p.get("description", "") or p.get("uuid", ""),
                    enabled=bool(p.get("enabled", True)),
                    conditions_count=1,
                    notification_channels=channel_count,
                    combiner=f"{p.get('type', '')} ({scope})",
                )
            )

        logger.debug("Found %d DO alert policies", len(results))
        return results

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def get_instance_metrics(
        self,
        droplet_id: str,
        hours: int = 1,
    ) -> ResourceMetrics:
        """Get key metrics for a Droplet over the last *hours* hours.

        Fetches CPU utilisation, memory utilisation, inbound/outbound bandwidth,
        disk read, and disk write from the DO monitoring API.

        Args:
            droplet_id: Numeric Droplet ID as a string.
            hours: Hours of historical data to retrieve (default 1).

        Returns:
            ResourceMetrics with per-metric time series.
        """
        end_dt = datetime.now(UTC)
        start_dt = end_dt - timedelta(hours=hours)
        start_ts = str(int(start_dt.timestamp()))
        end_ts = str(int(end_dt.timestamp()))

        base_params: dict[str, str] = {
            "host_id": droplet_id,
            "start": start_ts,
            "end": end_ts,
        }

        # Metric path -> label mapping
        metric_configs: list[tuple[str, str, dict[str, str]]] = [
            ("/monitoring/metrics/droplet/cpu", "CPUUtilization", {}),
            (
                "/monitoring/metrics/droplet/memory_utilization_percent",
                "MemoryUtilization",
                {},
            ),
            (
                "/monitoring/metrics/droplet/bandwidth",
                "BandwidthInbound",
                {"direction": "inbound"},
            ),
            (
                "/monitoring/metrics/droplet/bandwidth",
                "BandwidthOutbound",
                {"direction": "outbound"},
            ),
            ("/monitoring/metrics/droplet/disk_read", "DiskRead", {}),
            ("/monitoring/metrics/droplet/disk_write", "DiskWrite", {}),
        ]

        metrics: dict[str, list[MetricPoint]] = {}

        for path, label, extra_params in metric_configs:
            params = {**base_params, **extra_params}
            try:
                data = await self._auth.get(path, params=params)
                points = self._parse_metric_response(data)
                if points:
                    metrics[label] = points
            except Exception as exc:
                logger.debug(
                    "Could not fetch DO metric '%s' for droplet %s: %s",
                    label,
                    droplet_id,
                    exc,
                )

        return ResourceMetrics(resource_id=droplet_id, metrics=metrics)

    def _parse_metric_response(
        self, data: dict[str, object]
    ) -> list[MetricPoint]:
        """Parse the DO monitoring matrix response into MetricPoints.

        Expected shape:
            {
              "status": "success",
              "data": {
                "resultType": "matrix",
                "result": [
                  {"metric": {}, "values": [[timestamp, "value"], ...]}
                ]
              }
            }
        """
        points: list[MetricPoint] = []
        result_data = (data.get("data") or {}) if isinstance(data, dict) else {}
        result_list = result_data.get("result") or []  # type: ignore[union-attr]

        for series in result_list:
            for ts_raw, val_raw in series.get("values") or []:
                try:
                    points.append(
                        MetricPoint(
                            timestamp=datetime.fromtimestamp(float(ts_raw), tz=UTC),
                            value=float(val_raw),
                        )
                    )
                except (ValueError, TypeError) as exc:
                    logger.debug("Skipping malformed metric point: %s", exc)

        # Sort chronologically (API may return newest first)
        points.sort(key=lambda p: p.timestamp)
        return points
