"""Vultr cost analysis via Billing API.

Uses the /billing/history and /account endpoints to surface
current balance, pending charges, and billing history.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from spancloud.analysis.models import CostSummary, DailyCost, ServiceCost
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.vultr.auth import VultrAuth

logger = get_logger(__name__)


class VultrCostAnalyzer:
    """Retrieves cost data from the Vultr Billing API."""

    def __init__(self, auth: VultrAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def get_cost_summary(self, period_days: int = 30) -> CostSummary:
        """Get cost summary from Vultr billing.

        Uses the account endpoint for current balance/charges and
        billing history for daily breakdown.

        Args:
            period_days: How many days back to analyze.

        Returns:
            CostSummary with available cost data.
        """
        today = date.today()
        start = today - timedelta(days=period_days)

        # Get account info for current charges
        account = await self._auth.get("/account")
        acct = account.get("account", {})
        pending = Decimal(str(acct.get("pending_charges", "0")))
        balance = Decimal(str(acct.get("balance", "0")))

        # Get billing history
        history = await self._auth.get_paginated(
            "/billing/history", "billing_history"
        )

        # Aggregate by date and description (as service proxy)
        daily_map: dict[date, Decimal] = {}
        service_map: dict[str, Decimal] = {}

        for item in history:
            item_date_str = item.get("date", "")
            try:
                item_date = date.fromisoformat(item_date_str[:10])
            except (ValueError, TypeError):
                continue

            if item_date < start:
                continue

            amount = Decimal(str(item.get("amount", "0")))
            if amount <= 0:
                continue  # skip credits and promotional items
            description = item.get("description", "Other")

            # Classify by description keywords
            service = self._classify_service(description)

            daily_map[item_date] = daily_map.get(item_date, Decimal("0")) + amount
            service_map[service] = service_map.get(service, Decimal("0")) + amount

        total = sum(daily_map.values(), Decimal("0"))

        daily_costs = [
            DailyCost(date=d, cost=c.quantize(Decimal("0.01")))
            for d, c in sorted(daily_map.items())
        ]
        service_costs = [
            ServiceCost(service=s, cost=c.quantize(Decimal("0.01")))
            for s, c in sorted(service_map.items(), key=lambda x: x[1], reverse=True)
            if c > Decimal("0")
        ]

        return CostSummary(
            provider="vultr",
            period_start=start,
            period_end=today,
            total_cost=total.quantize(Decimal("0.01")),
            currency="USD",
            by_service=service_costs,
            daily_costs=daily_costs,
            account_id=acct.get("email", ""),
            notes=f"Balance: ${balance}, Pending charges: ${pending}",
        )

    def _classify_service(self, description: str) -> str:
        """Classify a billing line item into a service category."""
        desc = description.lower()
        if "instance" in desc or "cloud compute" in desc or "server" in desc:
            return "Compute (Instances)"
        if "bare metal" in desc:
            return "Compute (Bare Metal)"
        if "block storage" in desc:
            return "Block Storage"
        if "object storage" in desc:
            return "Object Storage"
        if "load balancer" in desc:
            return "Load Balancers"
        if "kubernetes" in desc or "vke" in desc:
            return "Kubernetes (VKE)"
        if "database" in desc or "managed db" in desc:
            return "Managed Databases"
        if "dns" in desc:
            return "DNS"
        if "bandwidth" in desc or "transfer" in desc:
            return "Bandwidth"
        if "snapshot" in desc or "backup" in desc:
            return "Snapshots/Backups"
        if "ip" in desc or "reserved" in desc:
            return "Reserved IPs"
        return "Other"
