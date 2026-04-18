"""Alibaba CloudMonitor (CMS) alarm rules."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.alibaba.auth import AlibabaAuth

logger = get_logger(__name__)


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
