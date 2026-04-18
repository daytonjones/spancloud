"""AWS cost analysis via Cost Explorer.

Cost Explorer charges $0.01 per API request, so we minimize calls:
one request for monthly totals, one for daily breakdown, one for per-service.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from skyforge.analysis.models import CostSummary, DailyCost, ServiceCost
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff
from skyforge.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from skyforge.providers.aws.auth import AWSAuth

logger = get_logger(__name__)

# Cost Explorer allows 5 requests/second
_CE_LIMITER = RateLimiter(calls_per_second=4.0, max_concurrency=5)


class AWSCostAnalyzer:
    """Retrieves cost data from AWS Cost Explorer.

    Minimizes API calls to keep Cost Explorer charges low ($0.01/request).
    Uses a single grouped query to get both service breakdown and totals.
    """

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def get_cost_summary(
        self,
        period_days: int = 30,
    ) -> CostSummary:
        """Get cost summary for the current billing period.

        Makes exactly 2 Cost Explorer API calls:
        1. Daily totals for the period
        2. Per-service breakdown for the period

        Args:
            period_days: How many days back to analyze (default 30).

        Returns:
            CostSummary with totals, daily breakdown, and per-service costs.
        """
        today = date.today()
        start = today - timedelta(days=period_days)

        # Fetch daily totals and per-service breakdown in parallel
        daily_task = asyncio.create_task(self._fetch_daily_costs(start, today))
        service_task = asyncio.create_task(self._fetch_service_costs(start, today))

        daily_costs = await daily_task
        service_costs = await service_task

        total = sum((d.cost for d in daily_costs), Decimal("0.00"))

        # Get account ID from auth
        identity = await self._auth.get_identity()

        return CostSummary(
            provider="aws",
            period_start=start,
            period_end=today,
            total_cost=total,
            currency="USD",
            by_service=sorted(service_costs, key=lambda s: s.cost, reverse=True),
            daily_costs=daily_costs,
            account_id=identity.get("account", ""),
        )

    async def _fetch_daily_costs(self, start: date, end: date) -> list[DailyCost]:
        """Fetch daily cost totals from Cost Explorer."""
        client = self._auth.client("ce")

        def _call() -> list[dict[str, Any]]:
            response = client.get_cost_and_usage(
                TimePeriod={
                    "Start": start.isoformat(),
                    "End": end.isoformat(),
                },
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
            )
            return response.get("ResultsByTime", [])

        async with _CE_LIMITER:
            results = await asyncio.to_thread(_call)

        daily: list[DailyCost] = []
        for result in results:
            day_str = result["TimePeriod"]["Start"]
            amount = result["Total"]["UnblendedCost"]["Amount"]
            daily.append(
                DailyCost(
                    date=date.fromisoformat(day_str),
                    cost=Decimal(amount).quantize(Decimal("0.01")),
                )
            )
        return daily

    async def _fetch_service_costs(self, start: date, end: date) -> list[ServiceCost]:
        """Fetch per-service cost breakdown from Cost Explorer."""
        client = self._auth.client("ce")

        def _call() -> list[dict[str, Any]]:
            response = client.get_cost_and_usage(
                TimePeriod={
                    "Start": start.isoformat(),
                    "End": end.isoformat(),
                },
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )
            return response.get("ResultsByTime", [])

        async with _CE_LIMITER:
            results = await asyncio.to_thread(_call)

        services: dict[str, Decimal] = {}
        for result in results:
            for group in result.get("Groups", []):
                service_name = group["Keys"][0]
                amount = Decimal(group["Metrics"]["UnblendedCost"]["Amount"])
                services[service_name] = services.get(service_name, Decimal("0")) + amount

        return [
            ServiceCost(
                service=name,
                cost=cost.quantize(Decimal("0.01")),
            )
            for name, cost in services.items()
            if cost > Decimal("0.00")
        ]
