"""Azure security auditor — finds common misconfigurations."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from skyforge.analysis.models import (
    SecurityAuditResult,
    SecurityFinding,
    Severity,
)
from skyforge.utils.logging import get_logger

if TYPE_CHECKING:
    from skyforge.providers.azure.auth import AzureAuth

logger = get_logger(__name__)

# Ports that should never be open to 0.0.0.0/0 in an NSG rule
_SENSITIVE_PORTS = {"22", "3389", "3306", "5432", "1433", "6379", "27017", "5984"}


class AzureSecurityAuditor:
    """Scans Azure for common security issues."""

    def __init__(self, auth: AzureAuth) -> None:
        self._auth = auth

    async def run_audit(
        self, region: str | None = None
    ) -> SecurityAuditResult:
        """Run all Azure security checks concurrently.

        Args:
            region: Optional Azure location filter — currently advisory.
        """
        _ = region
        findings_list = await asyncio.gather(
            asyncio.to_thread(self._check_nsgs),
            asyncio.to_thread(self._check_storage_public_access),
            asyncio.to_thread(self._check_storage_https_only),
            asyncio.to_thread(self._check_sql_public_access),
        )
        all_findings: list[SecurityFinding] = []
        for flist in findings_list:
            all_findings.extend(flist)

        return SecurityAuditResult(
            provider="azure",
            findings=all_findings,
            regions_scanned=[self._auth.subscription_id],
        )

    def _check_nsgs(self) -> list[SecurityFinding]:
        """Flag NSG rules that allow sensitive ports from the internet."""
        from azure.mgmt.network import NetworkManagementClient

        findings: list[SecurityFinding] = []
        try:
            client = NetworkManagementClient(
                self._auth.get_credential(), self._auth.subscription_id
            )
            for nsg in client.network_security_groups.list_all():
                for rule in nsg.security_rules or []:
                    finding = self._nsg_rule_finding(nsg, rule)
                    if finding:
                        findings.append(finding)
        except Exception as exc:
            logger.debug("NSG audit skipped: %s", exc)
        return findings

    def _nsg_rule_finding(self, nsg: Any, rule: Any) -> SecurityFinding | None:
        if str(rule.access) not in ("Allow", "SecurityRuleAccess.ALLOW"):
            return None
        if str(rule.direction) not in ("Inbound", "SecurityRuleDirection.INBOUND"):
            return None

        source = rule.source_address_prefix or ""
        if source not in ("*", "0.0.0.0/0", "Internet"):
            return None

        # Ports can be in port_range or port_ranges
        ports: list[str] = []
        if rule.destination_port_range:
            ports.append(rule.destination_port_range)
        if rule.destination_port_ranges:
            ports.extend(rule.destination_port_ranges)

        sensitive_hits = [p for p in ports if p in _SENSITIVE_PORTS or p == "*"]
        if not sensitive_hits:
            return None

        severity = (
            Severity.CRITICAL if "*" in sensitive_hits else Severity.HIGH
        )
        return SecurityFinding(
            severity=severity,
            resource_id=nsg.id or nsg.name,
            resource_type="nsg",
            provider="azure",
            region=nsg.location or "",
            title=f"NSG '{nsg.name}' allows internet to sensitive ports",
            description=(
                f"Rule '{rule.name}' on NSG '{nsg.name}' allows "
                f"{', '.join(sensitive_hits)} from {source}."
            ),
            recommendation=(
                "Restrict source to specific IP ranges or use Azure Bastion "
                "for remote access."
            ),
        )

    def _check_storage_public_access(self) -> list[SecurityFinding]:
        """Flag storage accounts with blob public access enabled."""
        from azure.mgmt.storage import StorageManagementClient

        findings: list[SecurityFinding] = []
        try:
            client = StorageManagementClient(
                self._auth.get_credential(), self._auth.subscription_id
            )
            for sa in client.storage_accounts.list():
                if getattr(sa, "allow_blob_public_access", False):
                    findings.append(
                        SecurityFinding(
                            severity=Severity.HIGH,
                            resource_id=sa.id or sa.name,
                            resource_type="storage_account",
                            provider="azure",
                            region=sa.location or "",
                            title=f"Storage account '{sa.name}' allows blob public access",
                            description=(
                                "allow_blob_public_access is True — any container "
                                "could be made publicly readable."
                            ),
                            recommendation=(
                                "Disable public access at the account level "
                                "unless explicitly required."
                            ),
                        )
                    )
        except Exception as exc:
            logger.debug("Storage public-access audit skipped: %s", exc)
        return findings

    def _check_storage_https_only(self) -> list[SecurityFinding]:
        """Flag storage accounts that allow HTTP traffic."""
        from azure.mgmt.storage import StorageManagementClient

        findings: list[SecurityFinding] = []
        try:
            client = StorageManagementClient(
                self._auth.get_credential(), self._auth.subscription_id
            )
            for sa in client.storage_accounts.list():
                if not getattr(sa, "enable_https_traffic_only", True):
                    findings.append(
                        SecurityFinding(
                            severity=Severity.MEDIUM,
                            resource_id=sa.id or sa.name,
                            resource_type="storage_account",
                            provider="azure",
                            region=sa.location or "",
                            title=f"Storage account '{sa.name}' allows HTTP",
                            description="HTTPS-only transfer is disabled.",
                            recommendation="Enable 'Secure transfer required'.",
                        )
                    )
        except Exception as exc:
            logger.debug("Storage HTTPS audit skipped: %s", exc)
        return findings

    def _check_sql_public_access(self) -> list[SecurityFinding]:
        """Flag SQL servers with Allow-Azure-services-or-0.0.0.0/0 firewall rules."""
        from azure.mgmt.sql import SqlManagementClient

        findings: list[SecurityFinding] = []
        try:
            client = SqlManagementClient(
                self._auth.get_credential(), self._auth.subscription_id
            )
            for server in client.servers.list():
                rg = _parse_rg(server.id or "")
                try:
                    for rule in client.firewall_rules.list_by_server(rg, server.name):
                        if rule.start_ip_address == "0.0.0.0" and \
                                rule.end_ip_address == "255.255.255.255":
                            findings.append(
                                SecurityFinding(
                                    severity=Severity.CRITICAL,
                                    resource_id=server.id or server.name,
                                    resource_type="sql_server",
                                    provider="azure",
                                    region=server.location or "",
                                    title=(
                                        f"SQL server '{server.name}' allows "
                                        "all IPs"
                                    ),
                                    description=(
                                        f"Firewall rule '{rule.name}' permits "
                                        "0.0.0.0 – 255.255.255.255."
                                    ),
                                    recommendation=(
                                        "Remove broad firewall rules; use "
                                        "Private Endpoints or narrow CIDRs."
                                    ),
                                )
                            )
                except Exception:
                    continue
        except Exception as exc:
            logger.debug("SQL firewall audit skipped: %s", exc)
        return findings


def _parse_rg(resource_id: str) -> str:
    parts = resource_id.split("/")
    for i, p in enumerate(parts):
        if p.lower() == "resourcegroups" and i + 1 < len(parts):
            return parts[i + 1]
    return ""
