"""Azure monitoring — metric alerts via azure-mgmt-monitor.

Surfaces Azure Monitor metric alert rules at the subscription scope.
Activity log alerts and scheduled query alerts live under separate APIs
and aren't covered here yet.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.azure.auth import AzureAuth

logger = get_logger(__name__)


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
    """Fetches Azure Monitor metric alert rules."""

    def __init__(self, auth: AzureAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
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
