"""Azure monitoring — metric alerts via azure-mgmt-monitor.

Surfaces Azure Monitor metric alert rules at the subscription scope.
Activity log alerts and scheduled query alerts live under separate APIs
and aren't covered here yet.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from spancloud.utils.logging import get_logger
from spancloud.providers.azure._retry import AZURE_RETRY_SLOW

if TYPE_CHECKING:
    from spancloud.providers.azure.auth import AzureAuth

logger = get_logger(__name__)

# Azure metric name → friendly label
_METRIC_NAME_MAP: dict[str, str] = {
    "Percentage CPU": "CPUUtilization",
    "Network In Total": "NetworkReceived",
    "Network Out Total": "NetworkSent",
    "Disk Read Bytes": "DiskReadBytes",
    "Disk Write Bytes": "DiskWriteBytes",
}

_VM_METRIC_NAMES = ",".join(_METRIC_NAME_MAP.keys())


class MetricPoint(BaseModel):
    """Single metric data point."""

    timestamp: datetime
    value: float


class ResourceMetrics(BaseModel):
    """Metrics for a specific Azure virtual machine."""

    resource_id: str
    resource_type: str = "virtual_machine"
    metrics: dict[str, list[MetricPoint]] = Field(default_factory=dict)


class AlertInfo(BaseModel):
    """Azure metric alert rule summary.

    Shape kept compatible with GCP's AlertInfo so the TUI/CLI renderers
    can share code.
    """

    name: str
    display_name: str = ""
    enabled: bool = True
    conditions_count: int = 0
    notification_channels: int = 0
    combiner: str = ""


class AzureMonitoringAnalyzer:
    """Fetches Azure Monitor metric alert rules and VM metrics."""

    def __init__(self, auth: AzureAuth) -> None:
        self._auth = auth

    @AZURE_RETRY_SLOW
    async def list_alert_policies(self) -> list[AlertInfo]:
        """List all metric alert rules in the subscription."""
        return await asyncio.to_thread(self._sync_list)

    def _sync_list(self) -> list[AlertInfo]:
        from azure.mgmt.monitor import MonitorManagementClient

        try:
            client = MonitorManagementClient(
                self._auth.get_credential(), self._auth.subscription_id
            )
        except Exception as exc:
            logger.debug("Could not build MonitorManagementClient: %s", exc)
            return []

        results: list[AlertInfo] = []
        try:
            for rule in client.metric_alerts.list_by_subscription():
                results.append(self._map_rule(rule))
        except Exception as exc:
            logger.debug("Azure metric alert list failed: %s", exc)

        logger.debug("Found %d Azure metric alerts", len(results))
        return results

    def _map_rule(self, rule: Any) -> AlertInfo:
        criteria = getattr(rule, "criteria", None)
        all_criteria = (
            getattr(criteria, "all_of", []) if criteria else []
        ) or []
        actions = getattr(rule, "actions", []) or []
        severity = getattr(rule, "severity", None)

        combiner_parts: list[str] = []
        if severity is not None:
            combiner_parts.append(f"sev{severity}")
        criteria_type = getattr(criteria, "odata_type", "") if criteria else ""
        if criteria_type:
            # e.g. "Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria"
            combiner_parts.append(criteria_type.rsplit(".", 1)[-1])

        return AlertInfo(
            name=rule.name,
            display_name=getattr(rule, "description", "") or rule.name,
            enabled=bool(getattr(rule, "enabled", True)),
            conditions_count=len(all_criteria),
            notification_channels=len(actions),
            combiner=" | ".join(combiner_parts) or "—",
        )

    @AZURE_RETRY_SLOW
    async def get_instance_metrics(
        self,
        resource_id: str,
        resource_group: str | None = None,
        hours: int = 1,
    ) -> ResourceMetrics:
        """Get key metrics for an Azure virtual machine.

        Args:
            resource_id: Full Azure resource ID or VM name. If it does not
                start with ``/subscriptions/``, a full ID is constructed using
                ``resource_group`` and the subscription from auth.
            resource_group: Required when ``resource_id`` is just a VM name.
            hours: Hours of historical data to retrieve.

        Returns:
            ResourceMetrics with per-metric time series.
        """
        if not resource_id.startswith("/subscriptions/"):
            if not resource_group:
                logger.debug(
                    "resource_group required when resource_id is not a full ID"
                )
                return ResourceMetrics(resource_id=resource_id)
            full_resource_id = (
                f"/subscriptions/{self._auth.subscription_id}"
                f"/resourceGroups/{resource_group}"
                f"/providers/Microsoft.Compute/virtualMachines/{resource_id}"
            )
        else:
            full_resource_id = resource_id

        return await asyncio.to_thread(
            self._sync_get_metrics, full_resource_id, hours
        )

    def _sync_get_metrics(self, resource_id: str, hours: int) -> ResourceMetrics:
        from azure.mgmt.monitor import MonitorManagementClient

        try:
            client = MonitorManagementClient(
                self._auth.get_credential(), self._auth.subscription_id
            )
        except Exception as exc:
            logger.debug("Could not build MonitorManagementClient: %s", exc)
            return ResourceMetrics(resource_id=resource_id)

        end = datetime.now(UTC)
        start = end - timedelta(hours=hours)
        timespan = f"{start.isoformat()}/{end.isoformat()}"

        try:
            metrics_response = client.metrics.list(
                resource_id,
                timespan=timespan,
                interval="PT1M",
                metricnames=_VM_METRIC_NAMES,
                aggregation="Average",
            )
        except Exception as exc:
            logger.debug("Azure metrics list failed for %s: %s", resource_id, exc)
            return ResourceMetrics(resource_id=resource_id)

        metrics: dict[str, list[MetricPoint]] = {}
        for metric in metrics_response.value:
            raw_name = metric.name.value if metric.name else ""
            label = _METRIC_NAME_MAP.get(raw_name, raw_name)
            points: list[MetricPoint] = []
            for ts in metric.timeseries or []:
                for data_point in ts.data or []:
                    avg = data_point.average
                    if avg is None:
                        continue
                    ts_value = data_point.time_stamp
                    if ts_value is None:
                        continue
                    points.append(MetricPoint(timestamp=ts_value, value=avg))
            points.sort(key=lambda p: p.timestamp)
            if points:
                metrics[label] = points

        logger.debug("Fetched %d metric series for %s", len(metrics), resource_id)
        return ResourceMetrics(resource_id=resource_id, metrics=metrics)
