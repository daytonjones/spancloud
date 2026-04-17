"""Alibaba Cloud cost analysis via the BSSOpenAPI."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from skyforge.analysis.models import CostSummary, DailyCost, ServiceCost
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.alibaba.auth import AlibabaAuth

logger = get_logger(__name__)


class AlibabaCostAnalyzer:
    """Fetches cost data from the BSS OpenAPI.

    Alibaba's BSS API exposes monthly bills (QueryBill / QueryBillOverview)
    and daily billing (QueryInstanceBill). We aggregate the current + prior
    month, then bucket by service name.
    """

    def __init__(self, auth: AlibabaAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def get_cost_summary(self, period_days: int = 30) -> CostSummary:
        today = date.today()
        start = today - timedelta(days=period_days)

        try:
            by_service, daily = await asyncio.gather(
                asyncio.to_thread(self._sync_query_by_service, start, today),
                asyncio.to_thread(self._sync_query_daily, start, today),
            )
        except Exception as exc:
            logger.warning("Alibaba BSS query failed: %s", exc)
            return CostSummary(
                provider="alibaba",
                period_start=start,
                period_end=today,
                total_cost=Decimal("0.00"),
                notes=f"BSS query failed: {exc}",
            )

        total = sum((sc.cost for sc in by_service), Decimal("0"))
        return CostSummary(
            provider="alibaba",
            period_start=start,
            period_end=today,
            total_cost=total.quantize(Decimal("0.01")),
            currency="USD",
            by_service=by_service,
            daily_costs=daily,
            account_id=self._auth.access_key_id[:6] + "..." if self._auth.access_key_id else "",
        )

    def _sync_query_by_service(
        self, start: date, end: date
    ) -> list[ServiceCost]:
        from alibabacloud_bssopenapi20171214 import models as bss_models
        from alibabacloud_bssopenapi20171214.client import Client as BssClient

        client = BssClient(self._auth.bss_config())
        totals: dict[str, Decimal] = {}

        months = _iter_months(start, end)
        for yyyymm in months:
            try:
                response = client.query_bill_overview(
                    bss_models.QueryBillOverviewRequest(billing_cycle=yyyymm)
                )
            except Exception as exc:
                logger.debug("BSS overview %s failed: %s", yyyymm, exc)
                continue

            data = getattr(response.body, "data", None)
            items_holder = getattr(data, "items", None) if data else None
            items = getattr(items_holder, "item", []) or [] if items_holder else []
            for it in items:
                service = str(
                    getattr(it, "product_name", "") or getattr(it, "product_code", "")
                    or "Other"
                )
                cost = Decimal(str(getattr(it, "pretax_amount", 0) or 0))
                totals[service] = totals.get(service, Decimal("0")) + cost

        return [
            ServiceCost(service=s, cost=c.quantize(Decimal("0.01")))
            for s, c in sorted(totals.items(), key=lambda x: x[1], reverse=True)
            if c > Decimal("0")
        ]

    def _sync_query_daily(self, start: date, end: date) -> list[DailyCost]:
        from alibabacloud_bssopenapi20171214 import models as bss_models
        from alibabacloud_bssopenapi20171214.client import Client as BssClient

        client = BssClient(self._auth.bss_config())

        daily_map: dict[date, Decimal] = {}
        for yyyymm in _iter_months(start, end):
            try:
                response = client.query_bill(
                    bss_models.QueryBillRequest(
                        billing_cycle=yyyymm, granularity="DAILY"
                    )
                )
            except Exception as exc:
                logger.debug("BSS bill %s failed: %s", yyyymm, exc)
                continue

            data = getattr(response.body, "data", None)
            items_holder = getattr(data, "items", None) if data else None
            items = getattr(items_holder, "item", []) or [] if items_holder else []
            for it in items:
                raw_date = str(
                    getattr(it, "usage_start_time", None)
                    or getattr(it, "billing_date", "")
                    or ""
                )
                if not raw_date:
                    continue
                try:
                    d = date.fromisoformat(raw_date[:10])
                except ValueError:
                    continue
                if d < start or d > end:
                    continue
                cost = Decimal(str(getattr(it, "pretax_amount", 0) or 0))
                daily_map[d] = daily_map.get(d, Decimal("0")) + cost

        return [
            DailyCost(date=d, cost=c.quantize(Decimal("0.01")))
            for d, c in sorted(daily_map.items())
        ]


def _iter_months(start: date, end: date) -> list[str]:
    """Return ['YYYY-MM', ...] covering start..end inclusive."""
    months: list[str] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months
