"""Tests for Tier 2 analysis data models."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from spancloud.analysis.models import (
    CostSummary,
    DailyCost,
    RelationshipMap,
    RelationshipType,
    ResourceRelationship,
    SecurityAuditResult,
    SecurityFinding,
    ServiceCost,
    Severity,
    UnusedResource,
    UnusedResourceReport,
)


class TestCostModels:
    """Tests for cost summary models."""

    def test_cost_summary_defaults(self) -> None:
        summary = CostSummary(
            provider="aws",
            period_start=date(2026, 3, 1),
            period_end=date(2026, 4, 1),
        )
        assert summary.total_cost == Decimal("0.00")
        assert summary.currency == "USD"
        assert summary.by_service == []
        assert summary.daily_costs == []

    def test_cost_summary_with_data(self) -> None:
        summary = CostSummary(
            provider="aws",
            period_start=date(2026, 3, 1),
            period_end=date(2026, 4, 1),
            total_cost=Decimal("152.43"),
            by_service=[
                ServiceCost(service="EC2", cost=Decimal("100.00")),
                ServiceCost(service="S3", cost=Decimal("52.43")),
            ],
            daily_costs=[
                DailyCost(date=date(2026, 3, 1), cost=Decimal("5.07")),
            ],
        )
        assert summary.total_cost == Decimal("152.43")
        assert len(summary.by_service) == 2
        assert summary.by_service[0].service == "EC2"


class TestSecurityModels:
    """Tests for security audit models."""

    def test_finding_creation(self) -> None:
        finding = SecurityFinding(
            severity=Severity.CRITICAL,
            resource_id="sg-123",
            resource_type="security_group",
            provider="aws",
            region="us-east-1",
            title="Open SSH",
            description="SSH is open to the world",
            recommendation="Restrict to known IPs",
        )
        assert finding.severity == Severity.CRITICAL
        assert finding.resource_id == "sg-123"

    def test_audit_result_summary(self) -> None:
        result = SecurityAuditResult(
            provider="aws",
            findings=[
                SecurityFinding(
                    severity=Severity.CRITICAL,
                    resource_id="sg-1",
                    resource_type="sg",
                    provider="aws",
                    title="t",
                    description="d",
                    recommendation="r",
                ),
                SecurityFinding(
                    severity=Severity.HIGH,
                    resource_id="sg-2",
                    resource_type="sg",
                    provider="aws",
                    title="t",
                    description="d",
                    recommendation="r",
                ),
                SecurityFinding(
                    severity=Severity.LOW,
                    resource_id="sg-3",
                    resource_type="sg",
                    provider="aws",
                    title="t",
                    description="d",
                    recommendation="r",
                ),
            ],
        )
        assert result.critical_count == 1
        assert result.high_count == 1
        assert result.medium_count == 0
        assert result.summary == "1 critical, 1 high, 0 medium, 1 low/info"

    def test_empty_audit(self) -> None:
        result = SecurityAuditResult(provider="gcp")
        assert result.critical_count == 0
        assert "0 critical" in result.summary


class TestUnusedModels:
    """Tests for unused resource models."""

    def test_unused_resource(self) -> None:
        res = UnusedResource(
            resource_id="vol-123",
            resource_name="vol-123",
            resource_type="ebs_volume",
            provider="aws",
            region="us-east-1",
            reason="Unattached 50 GB EBS volume",
            estimated_monthly_savings="~$4.00/mo",
        )
        assert res.resource_id == "vol-123"
        assert res.reason.startswith("Unattached")

    def test_report_total_count(self) -> None:
        report = UnusedResourceReport(
            provider="aws",
            resources=[
                UnusedResource(
                    resource_id="vol-1",
                    resource_name="vol-1",
                    resource_type="ebs_volume",
                    provider="aws",
                    reason="unattached",
                ),
                UnusedResource(
                    resource_id="eip-1",
                    resource_name="1.2.3.4",
                    resource_type="elastic_ip",
                    provider="aws",
                    reason="unused",
                ),
            ],
        )
        assert report.total_count == 2

    def test_total_estimated_monthly_savings(self) -> None:
        report = UnusedResourceReport(
            provider="aws",
            resources=[
                UnusedResource(
                    resource_id="vol-1", resource_name="v1",
                    resource_type="ebs_volume", provider="aws",
                    reason="unattached",
                    estimated_monthly_savings="~$4.00/mo (gp3 rate)",
                ),
                UnusedResource(
                    resource_id="vol-2", resource_name="v2",
                    resource_type="ebs_volume", provider="aws",
                    reason="unattached",
                    estimated_monthly_savings="~$1,234.56/mo",
                ),
                UnusedResource(
                    resource_id="snap-1", resource_name="s1",
                    resource_type="snapshot", provider="aws",
                    reason="old",
                    estimated_monthly_savings="$12.50/mo (snapshot)",
                ),
                UnusedResource(
                    resource_id="vm-1", resource_name="vm1",
                    resource_type="vm", provider="aws",
                    reason="stopped",
                    estimated_monthly_savings="varies by disk size",
                ),
            ],
        )
        assert report.total_estimated_monthly_savings == Decimal("1251.06")
        assert report.unestimated_count == 1

    def test_total_savings_empty(self) -> None:
        report = UnusedResourceReport(provider="aws", resources=[])
        assert report.total_estimated_monthly_savings == Decimal("0")
        assert report.unestimated_count == 0


class TestRelationshipModels:
    """Tests for resource relationship models."""

    def test_relationship_creation(self) -> None:
        rel = ResourceRelationship(
            source_id="i-123",
            source_type="ec2_instance",
            source_name="web-1",
            target_id="vpc-abc",
            target_type="vpc",
            relationship=RelationshipType.IN_VPC,
            provider="aws",
            region="us-east-1",
        )
        assert rel.relationship == RelationshipType.IN_VPC
        assert rel.source_id == "i-123"
        assert rel.target_id == "vpc-abc"

    def test_relationship_map_for_resource(self) -> None:
        rels = [
            ResourceRelationship(
                source_id="i-1",
                source_type="ec2",
                target_id="vpc-1",
                target_type="vpc",
                relationship=RelationshipType.IN_VPC,
                provider="aws",
            ),
            ResourceRelationship(
                source_id="i-1",
                source_type="ec2",
                target_id="sg-1",
                target_type="sg",
                relationship=RelationshipType.SECURED_BY,
                provider="aws",
            ),
            ResourceRelationship(
                source_id="i-2",
                source_type="ec2",
                target_id="vpc-1",
                target_type="vpc",
                relationship=RelationshipType.IN_VPC,
                provider="aws",
            ),
        ]
        rel_map = RelationshipMap(provider="aws", relationships=rels)

        # i-1 appears in 2 relationships
        assert len(rel_map.for_resource("i-1")) == 2

        # vpc-1 appears as target in 2 relationships
        assert len(rel_map.for_resource("vpc-1")) == 2

        # sg-1 appears as target in 1 relationship
        assert len(rel_map.for_resource("sg-1")) == 1

        # unknown resource
        assert len(rel_map.for_resource("unknown")) == 0


class TestRateLimiter:
    """Tests for the rate limiter utility."""

    def test_import(self) -> None:
        from spancloud.utils.throttle import RateLimiter, run_in_batches

        limiter = RateLimiter(calls_per_second=10.0, max_concurrency=5)
        assert limiter is not None
        assert run_in_batches is not None
