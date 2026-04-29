"""GCP cost analysis via Cloud Billing API.

GCP doesn't have a simple cost-retrieval API like AWS Cost Explorer.
Detailed per-service costs require BigQuery billing export. This module:
1. Retrieves billing account info and project linkage
2. Checks for BigQuery billing export configuration
3. Queries BigQuery export data if available, otherwise provides guidance.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from spancloud.analysis.models import CostSummary, DailyCost, ServiceCost
from spancloud.utils.logging import get_logger
from spancloud.providers.gcp._retry import GCP_RETRY_SLOW
from spancloud.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from spancloud.providers.gcp.auth import GCPAuth

logger = get_logger(__name__)

# Billing API: conservative rate limit
_BILLING_LIMITER = RateLimiter(calls_per_second=2.0, max_concurrency=5)


class GCPCostAnalyzer:
    """Retrieves cost data from GCP Cloud Billing and BigQuery export.

    If BigQuery billing export is configured, queries it for detailed costs.
    Otherwise, returns billing account info with setup instructions.
    """

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    @GCP_RETRY_SLOW
    async def get_cost_summary(
        self,
        period_days: int = 30,
    ) -> CostSummary:
        """Get cost summary for the current project.

        Attempts to use BigQuery billing export for detailed costs.
        Falls back to billing account info if export is not configured.

        Args:
            period_days: How many days back to analyze (default 30).

        Returns:
            CostSummary with available cost data.
        """
        project = self._auth.project_id
        if not project:
            return CostSummary(
                provider="gcp",
                period_start=date.today() - timedelta(days=period_days),
                period_end=date.today(),
                notes="No GCP project configured.",
            )

        today = date.today()
        start = today - timedelta(days=period_days)

        # Try to get billing account info
        billing_info = await self._get_billing_info(project)
        billing_account = billing_info.get("billingAccountName", "")

        # Try BigQuery billing export
        bq_result = await self._try_bigquery_export(project, start, today)

        if isinstance(bq_result, CostSummary):
            return bq_result

        if bq_result == "permission_denied":
            note = (
                "BigQuery permission denied — cost data could not be retrieved.\n\n"
                "Grant your account these roles in GCP Console → IAM & Admin:\n"
                "  • roles/bigquery.jobUser  (on the project)\n"
                "  • roles/bigquery.dataViewer  (on the billing export dataset)"
            )
        else:
            # None — export not configured
            note = (
                "Detailed cost data requires BigQuery billing export. "
                "Set up standard billing export in the GCP Console:\n"
                "  Billing → Billing export → BigQuery export → Enable\n"
                "Once enabled, cost data will be available within 24-48 hours."
            )
        if billing_account:
            note = f"Billing account: {billing_account}\n\n{note}"

        return CostSummary(
            provider="gcp",
            period_start=start,
            period_end=today,
            account_id=billing_account,
            notes=note,
        )

    async def _get_billing_info(self, project: str) -> dict[str, Any]:
        """Get billing account info for the project via direct HTTP (avoids googleapiclient logging)."""
        import httpx

        async def _call() -> dict[str, Any]:
            try:
                # Refresh credentials if needed
                creds = self._auth.credentials
                if hasattr(creds, "token") and not creds.valid:
                    import google.auth.transport.requests
                    creds.refresh(google.auth.transport.requests.Request())
                token = getattr(creds, "token", None)
                if not token:
                    return {}
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        f"https://cloudbilling.googleapis.com/v1/projects/{project}/billingInfo",
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if resp.status_code == 200:
                        return resp.json()
                    logger.debug("Cloud Billing API %d for project %s", resp.status_code, project)
                    return {}
            except Exception as exc:
                logger.debug("Could not fetch billing info: %s", exc)
                return {}

        async with _BILLING_LIMITER:
            return await _call()

    async def _try_bigquery_export(
        self, project: str, start: date, end: date
    ) -> "CostSummary | None | str":
        """Attempt to query BigQuery billing export for cost data.

        Returns:
            CostSummary on success.
            "permission_denied" string sentinel when IAM roles are missing.
            None when BigQuery export is not configured.
        """
        try:
            from google.cloud import bigquery
        except ImportError:
            logger.debug("google-cloud-bigquery not installed — skipping BQ export check")
            return None

        def _find_billing_table(bq_client: "bigquery.Client") -> "str | None":
            """Scan all datasets in the project for a billing export table."""
            try:
                datasets = list(bq_client.list_datasets())
            except Exception as exc:
                if "PERMISSION_DENIED" in str(exc) or "403" in str(exc):
                    raise PermissionError("bigquery") from exc
                return None
            for ds in datasets:
                try:
                    tables = list(bq_client.list_tables(ds.dataset_id))
                except Exception:
                    continue
                for t in tables:
                    if t.table_id.startswith("gcp_billing_export_v1"):
                        return f"{project}.{ds.dataset_id}.{t.table_id}"
            return None

        def _query() -> tuple[list[DailyCost], list[ServiceCost], Decimal] | None:
            try:
                bq_client = bigquery.Client(
                    project=project,
                    credentials=self._auth.credentials,
                )
            except Exception:
                return None

            table = _find_billing_table(bq_client)  # may raise PermissionError
            if not table:
                logger.debug("No BigQuery billing export table found in project %s", project)
                return None

            logger.debug("Using BigQuery billing export table: %s", table)
            try:
                query = f"""
                    SELECT
                        DATE(usage_start_time) as usage_date,
                        service.description as service_name,
                        SUM(cost) as cost
                    FROM `{table}`
                    WHERE DATE(usage_start_time) >= @start_date
                      AND DATE(usage_start_time) < @end_date
                      AND project.id = @project_id
                    GROUP BY usage_date, service_name
                    ORDER BY usage_date
                """
                job_config = bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter("start_date", "DATE", start),
                        bigquery.ScalarQueryParameter("end_date", "DATE", end),
                        bigquery.ScalarQueryParameter("project_id", "STRING", project),
                    ]
                )
                results = bq_client.query(query, job_config=job_config).result()

                daily_map: dict[date, Decimal] = {}
                service_map: dict[str, Decimal] = {}
                total = Decimal("0.00")

                for row in results:
                    day = row.usage_date
                    svc = row.service_name
                    cost = Decimal(str(row.cost))
                    daily_map[day] = daily_map.get(day, Decimal("0")) + cost
                    service_map[svc] = service_map.get(svc, Decimal("0")) + cost
                    total += cost

                daily = [
                    DailyCost(date=d, cost=c.quantize(Decimal("0.01")))
                    for d, c in sorted(daily_map.items())
                ]
                services = [
                    ServiceCost(service=s, cost=c.quantize(Decimal("0.01")))
                    for s, c in service_map.items()
                    if c > Decimal("0.00")
                ]
                return daily, services, total.quantize(Decimal("0.01"))

            except PermissionError:
                raise  # propagate so _try_bigquery_export can return the sentinel
            except Exception as exc:
                logger.debug("BigQuery billing query failed: %s", exc)
                return None

        try:
            async with _BILLING_LIMITER:
                result = await asyncio.to_thread(_query)
        except PermissionError:
            logger.warning(
                "BigQuery permission denied for project '%s'. "
                "Grant your account these roles in GCP Console → IAM & Admin:\n"
                "  • roles/bigquery.jobUser  (on the project)\n"
                "  • roles/bigquery.dataViewer  (on the billing export dataset)",
                project,
            )
            return "permission_denied"

        if result is None:
            return None

        daily_costs, service_costs, total = result
        return CostSummary(
            provider="gcp",
            period_start=start,
            period_end=end,
            total_cost=total,
            currency="USD",
            by_service=sorted(service_costs, key=lambda s: s.cost, reverse=True),
            daily_costs=daily_costs,
            account_id=project,
        )
