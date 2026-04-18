"""DigitalOcean cost analysis.

DigitalOcean's API exposes billing in two places:

  /customers/my/balance
      current account balance, month-to-date usage, month-to-date balance.

  /customers/my/billing_history
      a list of past invoices, payments, and credits — monthly granularity,
      not daily. DO does not publish a daily cost endpoint.

This analyzer surfaces month-to-date usage as the headline number, groups
prior invoices by service (inferred from the human-readable description),
and maps each invoice to its date for the "daily" trend. It also
propagates API failures into the CostSummary notes so the user can see
*why* the total is zero (typically a PAT missing the `read` billing scope).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from skyforge.analysis.models import CostSummary, DailyCost, ServiceCost
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.digitalocean.auth import DigitalOceanAuth

logger = get_logger(__name__)


class DigitalOceanCostAnalyzer:
    """Retrieves cost data from the DO Customer API."""

    def __init__(self, auth: DigitalOceanAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def get_cost_summary(self, period_days: int = 30) -> CostSummary:
        today = date.today()
        start = today - timedelta(days=period_days)
        notes_parts: list[str] = []

        # --- Balance endpoint -------------------------------------------------
        account_balance = Decimal("0")
        mtd_usage = Decimal("0")
        mtd_balance = Decimal("0")
        balance_ok = False

        try:
            balance_data = await self._auth.get("/customers/my/balance")
            account_balance = _to_decimal(balance_data.get("account_balance", 0))
            mtd_usage = _to_decimal(balance_data.get("month_to_date_usage", 0))
            mtd_balance = _to_decimal(balance_data.get("month_to_date_balance", 0))
            balance_ok = True
        except Exception as exc:
            msg = str(exc)
            if "403" in msg or "401" in msg:
                hint = (
                    " — DigitalOcean's billing endpoints are gated by the "
                    "account-level billing role, not by PAT scope. If you're "
                    "on a team as a Member/Developer (or on a sub-user "
                    "account), your token cannot see billing even with "
                    "'Full Access'. The account Owner must view billing "
                    "directly, or grant you the Billing team role."
                )
            else:
                hint = ""
            logger.warning("DO balance endpoint failed: %s", exc)
            notes_parts.append(f"balance endpoint failed: {exc}{hint}")

        # --- Billing history (invoices) --------------------------------------
        history: list[dict] = []
        try:
            history = await self._auth.get_paginated(
                "/customers/my/billing_history", "billing_history"
            )
        except Exception as exc:
            logger.warning("DO billing_history endpoint failed: %s", exc)
            notes_parts.append(f"billing_history endpoint failed: {exc}")

        daily_map: dict[date, Decimal] = {}
        service_map: dict[str, Decimal] = {}

        for item in history:
            # Only count actual charges — skip Payment / Credit / Refund rows.
            item_type = str(item.get("type", "")).lower()
            if item_type and item_type != "invoice":
                continue

            item_date_str = item.get("date", "")
            try:
                item_date = date.fromisoformat(item_date_str[:10])
            except (ValueError, TypeError):
                continue

            if item_date < start:
                continue

            amount = _to_decimal(item.get("amount", 0))
            # Invoice amounts are positive charges on DO; anything negative
            # here would be unexpected, but guard against it.
            if amount <= 0:
                continue

            description = item.get("description", "Other")
            service = self._classify_service(description)

            daily_map[item_date] = daily_map.get(item_date, Decimal("0")) + amount
            service_map[service] = service_map.get(service, Decimal("0")) + amount

        invoice_total = sum(daily_map.values(), Decimal("0"))

        # --- Assemble the summary --------------------------------------------
        # The "total" users care about most is: what have I been charged
        # recently? We report MTD usage (running current-month accrual) +
        # any invoiced amounts inside the period window.
        total = (mtd_usage if mtd_usage > 0 else Decimal("0")) + invoice_total

        # If MTD usage is present, surface it as a synthetic "daily" point
        # on today's date so the trend chart isn't completely empty.
        if mtd_usage > 0:
            daily_map[today] = daily_map.get(today, Decimal("0")) + mtd_usage
            service_map["Current Month-to-Date Usage"] = (
                service_map.get("Current Month-to-Date Usage", Decimal("0"))
                + mtd_usage
            )

        daily_costs = [
            DailyCost(date=d, cost=c.quantize(Decimal("0.01")))
            for d, c in sorted(daily_map.items())
        ]
        service_costs = [
            ServiceCost(service=s, cost=c.quantize(Decimal("0.01")))
            for s, c in sorted(
                service_map.items(), key=lambda x: x[1], reverse=True
            )
            if c > Decimal("0")
        ]

        # Human-readable notes
        if balance_ok:
            notes_parts.insert(
                0,
                (
                    f"Account balance: ${account_balance:,.2f}  |  "
                    f"Month-to-date usage: ${mtd_usage:,.2f}  |  "
                    f"Month-to-date balance: ${mtd_balance:,.2f}"
                ),
            )
        notes_parts.append(
            "DigitalOcean publishes monthly invoices only — there is no "
            "daily cost API. The 'daily' trend below shows one point per "
            "invoice plus today's MTD accrual."
        )

        return CostSummary(
            provider="digitalocean",
            period_start=start,
            period_end=today,
            total_cost=total.quantize(Decimal("0.01")),
            currency="USD",
            by_service=service_costs,
            daily_costs=daily_costs,
            notes="  ".join(notes_parts),
        )

    def _classify_service(self, description: str) -> str:
        """Classify a billing line item into a service category."""
        desc = description.lower()
        if "droplet" in desc:
            return "Droplets"
        if "volume" in desc or "block storage" in desc:
            return "Block Storage"
        if "spaces" in desc or "object storage" in desc:
            return "Spaces (Object Storage)"
        if "load balancer" in desc:
            return "Load Balancers"
        if "kubernetes" in desc or "doks" in desc:
            return "Kubernetes (DOKS)"
        if "database" in desc or "managed db" in desc:
            return "Managed Databases"
        if "bandwidth" in desc or "transfer" in desc:
            return "Bandwidth"
        if "snapshot" in desc or "backup" in desc:
            return "Snapshots/Backups"
        if "reserved ip" in desc or "floating ip" in desc:
            return "Reserved IPs"
        if "cdn" in desc:
            return "CDN"
        if "firewall" in desc:
            return "Firewalls"
        if "invoice" in desc:
            # Generic "Invoice for <Month> <Year>" rows — can't classify further
            return "Prior Monthly Invoices"
        return "Other"


def _to_decimal(value: object) -> Decimal:
    """Parse a DO billing value into a Decimal, tolerating strings / None."""
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")
