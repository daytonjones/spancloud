"""Data models for Tier 2 analysis features.

Unified models that all provider-specific analyzers return,
allowing the CLI to render results consistently.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field

_DOLLAR_PATTERN = re.compile(r"\$\s*([0-9,]+(?:\.[0-9]+)?)")

# ---------------------------------------------------------------------------
# Cost Summary
# ---------------------------------------------------------------------------


class DailyCost(BaseModel):
    """Single day's cost."""

    date: date
    cost: Decimal


class ServiceCost(BaseModel):
    """Cost breakdown for a single service."""

    service: str
    cost: Decimal


class CostSummary(BaseModel):
    """Aggregated cost report for a provider/account.

    Returned by cost analyzers for display in the CLI.
    """

    provider: str
    period_start: date
    period_end: date
    total_cost: Decimal = Decimal("0.00")
    currency: str = "USD"
    by_service: list[ServiceCost] = Field(default_factory=list)
    daily_costs: list[DailyCost] = Field(default_factory=list)
    account_id: str = ""
    notes: str = ""


# ---------------------------------------------------------------------------
# Security Audit
# ---------------------------------------------------------------------------


class Severity(StrEnum):
    """Severity levels for security findings."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class SecurityFinding(BaseModel):
    """A single security issue found during audit."""

    severity: Severity
    resource_id: str
    resource_type: str
    provider: str
    region: str = ""
    title: str
    description: str
    recommendation: str


class SecurityAuditResult(BaseModel):
    """Complete security audit for a provider."""

    provider: str
    findings: list[SecurityFinding] = Field(default_factory=list)
    scanned_at: datetime = Field(default_factory=datetime.now)
    regions_scanned: list[str] = Field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.HIGH)

    @property
    def medium_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.MEDIUM)

    @property
    def summary(self) -> str:
        """One-line summary of finding counts."""
        other = (
            len(self.findings)
            - self.critical_count - self.high_count - self.medium_count
        )
        return (
            f"{self.critical_count} critical, {self.high_count} high, "
            f"{self.medium_count} medium, {other} low/info"
        )


# ---------------------------------------------------------------------------
# Unused Resource Detection
# ---------------------------------------------------------------------------


class UnusedResource(BaseModel):
    """A resource identified as unused or idle."""

    resource_id: str
    resource_name: str
    resource_type: str
    provider: str
    region: str = ""
    reason: str
    last_used: datetime | None = None
    estimated_monthly_savings: str = ""


class UnusedResourceReport(BaseModel):
    """Complete unused resource report for a provider."""

    provider: str
    resources: list[UnusedResource] = Field(default_factory=list)
    scanned_at: datetime = Field(default_factory=datetime.now)

    @property
    def total_count(self) -> int:
        return len(self.resources)

    @property
    def total_estimated_monthly_savings(self) -> Decimal:
        """Sum the parseable $ amounts from each resource's savings string.

        Providers format estimates like '~$3.60/mo' or '$1,234.56/mo (est)' —
        this property extracts the first dollar figure from each and sums
        them. Resources with non-numeric estimates (e.g. 'varies by disk size')
        are skipped; see `unestimated_count` for how many.
        """
        total = Decimal("0")
        for r in self.resources:
            match = _DOLLAR_PATTERN.search(r.estimated_monthly_savings or "")
            if match:
                try:
                    total += Decimal(match.group(1).replace(",", ""))
                except Exception:
                    continue
        return total

    @property
    def unestimated_count(self) -> int:
        """Number of unused resources whose savings string is non-numeric."""
        return sum(
            1 for r in self.resources
            if not _DOLLAR_PATTERN.search(r.estimated_monthly_savings or "")
        )


# ---------------------------------------------------------------------------
# Resource Relationships
# ---------------------------------------------------------------------------


class RelationshipType(StrEnum):
    """Types of relationships between resources."""

    IN_VPC = "in_vpc"
    IN_SUBNET = "in_subnet"
    SECURED_BY = "secured_by"
    ATTACHED_TO = "attached_to"
    TARGETS = "targets"
    MEMBER_OF = "member_of"
    DEPENDS_ON = "depends_on"
    ROUTES_TO = "routes_to"


class ResourceRelationship(BaseModel):
    """A directed relationship between two resources."""

    source_id: str
    source_type: str
    source_name: str = ""
    target_id: str
    target_type: str
    target_name: str = ""
    relationship: RelationshipType
    provider: str
    region: str = ""


class RelationshipMap(BaseModel):
    """Complete relationship map for a provider."""

    provider: str
    relationships: list[ResourceRelationship] = Field(default_factory=list)
    scanned_at: datetime = Field(default_factory=datetime.now)

    def for_resource(self, resource_id: str) -> list[ResourceRelationship]:
        """Get all relationships involving a specific resource."""
        return [
            r for r in self.relationships
            if r.source_id == resource_id or r.target_id == resource_id
        ]
