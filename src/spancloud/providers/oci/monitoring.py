"""OCI monitoring alarms (via oci.monitoring.MonitoringClient)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

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


class OCIMonitoringAnalyzer:
    """Fetches OCI monitoring alarms."""

    def __init__(self, auth: OCIAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
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
