"""DigitalOcean monitoring — alert policies via the /v2/monitoring API.

DO exposes droplet metric alerts (CPU, load, memory, disk, outbound bandwidth)
as "alert policies". Each policy targets a set of droplet IDs or tags and
fires notifications via email or Slack.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

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


class DigitalOceanMonitoringAnalyzer:
    """Fetches DigitalOcean alert policies."""

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
