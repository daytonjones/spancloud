"""OCI cost analysis via the Usage API.

Requests ResourceType.COMPUTED daily usage summaries with cost for the
tenancy root, grouped by service.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from spancloud.analysis.models import CostSummary, DailyCost, ServiceCost
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.oci.auth import OCIAuth

logger = get_logger(__name__)


class OCICostAnalyzer:
    """Fetches cost data from the OCI Usage API."""

    def __init__(self, auth: OCIAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def get_cost_summary(self, period_days: int = 30) -> CostSummary:
        today = date.today()
        start = today - timedelta(days=period_days)

        try:
            by_service, daily = await asyncio.gather(
                asyncio.to_thread(
                    self._sync_query, start, today, "service"
                ),
                asyncio.to_thread(
                    self._sync_query, start, today, "daily"
                ),
            )
        except Exception as exc:
            logger.warning("OCI cost query failed: %s", exc)
            return CostSummary(
                provider="oci",
                period_start=start,
                period_end=today,
                total_cost=Decimal("0.00"),
                notes=f"Usage API query failed: {exc}",
            )

        total = sum((sc.cost for sc in by_service), Decimal("0"))
        return CostSummary(
            provider="oci",
            period_start=start,
            period_end=today,
            total_cost=total.quantize(Decimal("0.01")),
            currency="USD",
            by_service=by_service,
            daily_costs=daily,
            account_id=self._auth.config.get("tenancy", ""),
        )

    def _sync_query(
        self, start: date, end: date, mode: str
    ) -> list[Any]:
        import oci

        client = oci.usage_api.UsageapiClient(self._auth.config)
        tenancy = self._auth.config.get("tenancy", "")
        if not tenancy:
            return []

        time_start = datetime.combine(start, datetime.min.time()).replace(tzinfo=UTC)
        time_end = datetime.combine(end, datetime.min.time()).replace(tzinfo=UTC)

        if mode == "service":
            details = oci.usage_api.models.RequestSummarizedUsagesDetails(
                tenant_id=tenancy,
                time_usage_started=time_start,
                time_usage_ended=time_end,
                granularity="DAILY",
                query_type="COST",
                group_by=["service"],
            )
            response = client.request_summarized_usages(details)
            totals: dict[str, Decimal] = {}
            for item in response.data.items or []:
                name = getattr(item, "service", "") or "Other"
                cost = Decimal(str(getattr(item, "computed_amount", 0) or 0))
                totals[name] = totals.get(name, Decimal("0")) + cost
            return [
                ServiceCost(service=s, cost=c.quantize(Decimal("0.01")))
                for s, c in sorted(
                    totals.items(), key=lambda x: x[1], reverse=True
                )
                if c > Decimal("0")
            ]

        # daily mode
        details = oci.usage_api.models.RequestSummarizedUsagesDetails(
            tenant_id=tenancy,
            time_usage_started=time_start,
            time_usage_ended=time_end,
            granularity="DAILY",
            query_type="COST",
        )
        response = client.request_summarized_usages(details)
        daily_map: dict[date, Decimal] = {}
        for item in response.data.items or []:
            ts = getattr(item, "time_usage_started", None)
            if not ts:
                continue
            d = ts.date() if hasattr(ts, "date") else date.fromisoformat(str(ts)[:10])
            cost = Decimal(str(getattr(item, "computed_amount", 0) or 0))
            daily_map[d] = daily_map.get(d, Decimal("0")) + cost

        return [
            DailyCost(date=d, cost=c.quantize(Decimal("0.01")))
            for d, c in sorted(daily_map.items())
        ]
