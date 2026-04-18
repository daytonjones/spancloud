"""Alibaba CloudMonitor (CMS) alarm rules and instance metrics."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.alibaba.auth import AlibabaAuth

logger = get_logger(__name__)

# ECS metrics available via CMS acs_ecs_dashboard namespace
_ECS_METRICS = [
    "CPUUtilization",
    "memory_usedutilization",
    "disk_readbytes",
    "disk_writebytes",
    "net_tx.rate",
    "net_rx.rate",
]


class MetricPoint(BaseModel):
    """A single time-series data point."""

    timestamp: datetime
    value: float


class ResourceMetrics(BaseModel):
    """Time-series metrics for a single cloud resource."""

    resource_id: str
    resource_type: str = "ecs_instance"
    metrics: dict[str, list[MetricPoint]] = Field(default_factory=dict)


class AlertInfo(BaseModel):
    """Alibaba metric alarm summary (GCP AlertInfo-compatible)."""

    name: str
    display_name: str = ""
    enabled: bool = True
    conditions_count: int = 1
    notification_channels: int = 0
    combiner: str = ""


class AlibabaMonitoringAnalyzer:
    """Fetches Alibaba CloudMonitor metric alarm rules."""

    def __init__(self, auth: AlibabaAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def list_alert_policies(self) -> list[AlertInfo]:
        return await asyncio.to_thread(self._sync_list)

    def _sync_list(self) -> list[AlertInfo]:
        from alibabacloud_cms20190101 import models as cms_models
        from alibabacloud_cms20190101.client import Client as CmsClient

        try:
            client = CmsClient(self._auth.cms_config())
        except Exception as exc:
            logger.debug("CMS client init failed: %s", exc)
            return []

        results: list[AlertInfo] = []
        page = 1
        try:
            while True:
                response = client.describe_metric_rule_list(
                    cms_models.DescribeMetricRuleListRequest(
                        page=page, page_size=100
                    )
                )
                body = response.body
                alarm_holder = getattr(body, "alarms", None)
                alarms = (
                    getattr(alarm_holder, "alarm", []) or []
                    if alarm_holder
                    else []
                )
                if not alarms:
                    break
                for a in alarms:
                    results.append(self._map_rule(a))
                total = int(getattr(body, "total", 0) or 0)
                if page * 100 >= total:
                    break
                page += 1
        except Exception as exc:
            logger.debug("CMS alarm list failed: %s", exc)
        return results

    def _map_rule(self, rule: Any) -> AlertInfo:
        enabled_raw = str(getattr(rule, "enable_state", "") or "")
        namespace = str(getattr(rule, "namespace", "") or "")
        metric = str(getattr(rule, "metric_name", "") or "")
        contact_groups = getattr(rule, "contact_groups", "") or ""
        channels = (
            len([g for g in str(contact_groups).split(",") if g.strip()])
            if contact_groups
            else 0
        )
        combiner = "/".join(p for p in (namespace, metric) if p) or "—"
        return AlertInfo(
            name=getattr(rule, "rule_id", "") or "",
            display_name=getattr(rule, "rule_name", "") or "",
            enabled=enabled_raw.lower() in ("true", "1", "enabled"),
            conditions_count=1,
            notification_channels=channels,
            combiner=combiner,
        )

    async def get_instance_metrics(
        self,
        instance_id: str,
        region: str | None = None,
        hours: int = 1,
    ) -> ResourceMetrics:
        """Fetch CMS time-series metrics for an ECS instance.

        Args:
            instance_id: The ECS instance ID.
            region: Optional region override (uses auth default if omitted).
            hours: Number of hours of history to retrieve (default 1).

        Returns:
            ResourceMetrics with per-metric lists of MetricPoint objects.
        """
        return await asyncio.to_thread(
            self._sync_get_instance_metrics, instance_id, region, hours
        )

    def _sync_get_instance_metrics(
        self, instance_id: str, region: str | None, hours: int
    ) -> ResourceMetrics:
        from alibabacloud_cms20190101 import models as cms_models
        from alibabacloud_cms20190101.client import Client as CmsClient

        try:
            client = CmsClient(self._auth.cms_config(region))
        except Exception as exc:
            logger.debug("CMS client init failed for metrics: %s", exc)
            return ResourceMetrics(resource_id=instance_id)

        now = datetime.now(tz=timezone.utc)
        start = now - timedelta(hours=hours)
        start_ms = str(int(start.timestamp() * 1000))
        end_ms = str(int(now.timestamp() * 1000))
        dimensions = json.dumps([{"instanceId": instance_id}])

        collected: dict[str, list[MetricPoint]] = {}

        for metric_name in _ECS_METRICS:
            points: list[MetricPoint] = []
            try:
                request = cms_models.DescribeMetricListRequest(
                    namespace="acs_ecs_dashboard",
                    metric_name=metric_name,
                    dimensions=dimensions,
                    start_time=start_ms,
                    end_time=end_ms,
                    period="60",
                )
                response = client.describe_metric_list(request)
                raw_datapoints = str(
                    getattr(response.body, "datapoints", "") or ""
                )
                if raw_datapoints and raw_datapoints != "null":
                    try:
                        dp_list = json.loads(raw_datapoints)
                        for dp in dp_list or []:
                            ts_ms = dp.get("timestamp")
                            value = dp.get("Average")
                            if ts_ms is not None and value is not None:
                                points.append(
                                    MetricPoint(
                                        timestamp=datetime.fromtimestamp(
                                            int(ts_ms) / 1000, tz=timezone.utc
                                        ),
                                        value=float(value),
                                    )
                                )
                    except (json.JSONDecodeError, TypeError, ValueError) as parse_exc:
                        logger.debug(
                            "Failed to parse CMS datapoints for %s/%s: %s",
                            metric_name,
                            instance_id,
                            parse_exc,
                        )
            except Exception as exc:
                logger.debug(
                    "CMS DescribeMetricList failed for %s/%s: %s",
                    metric_name,
                    instance_id,
                    exc,
                )

            collected[metric_name] = points

        return ResourceMetrics(
            resource_id=instance_id,
            resource_type="ecs_instance",
            metrics=collected,
        )
