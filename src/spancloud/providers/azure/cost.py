"""Azure cost analysis via the Cost Management API."""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from spancloud.analysis.models import CostSummary, DailyCost, ServiceCost
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.azure.auth import AzureAuth

logger = get_logger(__name__)


class AzureCostAnalyzer:
    """Retrieves cost data from the Azure Cost Management API."""

    def __init__(self, auth: AzureAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def get_cost_summary(self, period_days: int = 30) -> CostSummary:
        """Get cost summary grouped by service (ResourceType) and by day."""
        today = date.today()
        start = today - timedelta(days=period_days)

        try:
            by_service, daily = await asyncio.gather(
                asyncio.to_thread(self._sync_query_by_service, start, today),
                asyncio.to_thread(self._sync_query_by_day, start, today),
            )
        except Exception as exc:
            logger.warning("Azure cost query failed: %s", exc)
            return CostSummary(
                provider="azure",
                period_start=start,
                period_end=today,
                total_cost=Decimal("0.00"),
                notes=f"Cost Management query failed: {exc}",
            )

        total = sum((sc.cost for sc in by_service), Decimal("0"))

        return CostSummary(
            provider="azure",
            period_start=start,
            period_end=today,
            total_cost=total.quantize(Decimal("0.01")),
            currency="USD",
            by_service=by_service,
            daily_costs=daily,
            account_id=self._auth.subscription_id,
        )

    def _sync_query_by_service(
        self, start: date, end: date
    ) -> list[ServiceCost]:
        from azure.mgmt.costmanagement import CostManagementClient

        client = CostManagementClient(self._auth.get_credential())
        scope = f"/subscriptions/{self._auth.subscription_id}"

        parameters = {
            "type": "ActualCost",
            "timeframe": "Custom",
            "time_period": {
                "from": datetime.combine(start, datetime.min.time()),
                "to": datetime.combine(end, datetime.min.time()),
            },
            "dataset": {
                "granularity": "None",
                "aggregation": {
                    "totalCost": {"name": "PreTaxCost", "function": "Sum"}
                },
                "grouping": [
                    {"type": "Dimension", "name": "ServiceName"},
                ],
            },
        }

        result = client.query.usage(scope=scope, parameters=parameters)
        return _parse_service_rows(result)

    def _sync_query_by_day(self, start: date, end: date) -> list[DailyCost]:
        from azure.mgmt.costmanagement import CostManagementClient

        client = CostManagementClient(self._auth.get_credential())
        scope = f"/subscriptions/{self._auth.subscription_id}"

        parameters = {
            "type": "ActualCost",
            "timeframe": "Custom",
            "time_period": {
                "from": datetime.combine(start, datetime.min.time()),
                "to": datetime.combine(end, datetime.min.time()),
            },
            "dataset": {
                "granularity": "Daily",
                "aggregation": {
                    "totalCost": {"name": "PreTaxCost", "function": "Sum"}
                },
            },
        }

        result = client.query.usage(scope=scope, parameters=parameters)
        return _parse_daily_rows(result)


def _parse_service_rows(result: object) -> list[ServiceCost]:
    """Parse a Cost Management usage result grouped by service."""
    rows = getattr(result, "rows", None) or []
    columns = getattr(result, "columns", None) or []
    col_names = [getattr(c, "name", "") for c in columns]

    try:
        cost_idx = col_names.index("PreTaxCost")
    except ValueError:
        return []
    try:
        service_idx = col_names.index("ServiceName")
    except ValueError:
        service_idx = -1

    service_map: dict[str, Decimal] = {}
    for row in rows:
        try:
            cost = Decimal(str(row[cost_idx]))
        except Exception:
            continue
        service = str(row[service_idx]) if service_idx >= 0 else "Other"
        service_map[service] = service_map.get(service, Decimal("0")) + cost

    return [
        ServiceCost(service=s, cost=c.quantize(Decimal("0.01")))
        for s, c in sorted(service_map.items(), key=lambda x: x[1], reverse=True)
        if c > Decimal("0")
    ]


def _parse_daily_rows(result: object) -> list[DailyCost]:
    """Parse a Cost Management usage result with daily granularity."""
    rows = getattr(result, "rows", None) or []
    columns = getattr(result, "columns", None) or []
    col_names = [getattr(c, "name", "") for c in columns]

    try:
        cost_idx = col_names.index("PreTaxCost")
    except ValueError:
        return []
    try:
        date_idx = col_names.index("UsageDate")
    except ValueError:
        return []

    daily_map: dict[date, Decimal] = {}
    for row in rows:
        try:
            cost = Decimal(str(row[cost_idx]))
        except Exception:
            continue
        raw_date = row[date_idx]
        try:
            # Azure returns YYYYMMDD as integer
            s = str(raw_date)
            d = date(int(s[:4]), int(s[4:6]), int(s[6:8]))
        except Exception:
            continue
        daily_map[d] = daily_map.get(d, Decimal("0")) + cost

    return [
        DailyCost(date=d, cost=c.quantize(Decimal("0.01")))
        for d, c in sorted(daily_map.items())
    ]
