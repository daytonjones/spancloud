"""Vultr security audit — scans for common misconfigurations.

Checks:
- Firewall groups with 0.0.0.0/0 rules on sensitive ports
- Instances without firewall groups attached
- Databases with public trusted IPs
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from skyforge.analysis.models import SecurityAuditResult, SecurityFinding, Severity
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.vultr.auth import VultrAuth

logger = get_logger(__name__)

_SENSITIVE_PORTS: dict[int, str] = {
    22: "SSH",
    3389: "RDP",
    3306: "MySQL",
    5432: "PostgreSQL",
    27017: "MongoDB",
    6379: "Redis",
}


class VultrSecurityAuditor:
    """Scans Vultr resources for security misconfigurations."""

    def __init__(self, auth: VultrAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def run_audit(self, region: str | None = None) -> SecurityAuditResult:
        """Run a full security audit.

        Args:
            region: Optional region filter.

        Returns:
            SecurityAuditResult with all findings.
        """
        tasks = [
            self._check_firewall_rules(),
            self._check_unprotected_instances(),
            self._check_database_access(),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        findings: list[SecurityFinding] = []
        for result in results:
            if isinstance(result, list):
                findings.extend(result)
            elif isinstance(result, Exception):
                logger.warning("Vultr security check failed: %s", result)

        return SecurityAuditResult(
            provider="vultr",
            findings=findings,
            regions_scanned=[region or "all"],
        )

    async def _check_firewall_rules(self) -> list[SecurityFinding]:
        """Flag firewall groups with open rules on sensitive ports."""
        groups = await self._auth.get_paginated("/firewalls", "firewall_groups")

        findings: list[SecurityFinding] = []
        for group in groups:
            group_id = group.get("id", "")
            group_name = group.get("description", group_id)

            try:
                rules = await self._auth.get_paginated(
                    f"/firewalls/{group_id}/rules", "firewall_rules"
                )
            except Exception as exc:
                logger.debug("Could not fetch rules for %s: %s", group_id, exc)
                continue

            for rule in rules:
                subnet = rule.get("subnet", "")
                subnet_size = rule.get("subnet_size", 0)
                port = rule.get("port", "")
                protocol = rule.get("protocol", "")
                action = rule.get("action", "")

                # Check for 0.0.0.0/0 (subnet=0.0.0.0, size=0)
                if subnet == "0.0.0.0" and subnet_size == 0 and action == "accept":
                    if not port or port == "0":
                        findings.append(SecurityFinding(
                            severity=Severity.CRITICAL,
                            resource_id=group_id,
                            resource_type="firewall_group",
                            provider="vultr",
                            title=(
                                f"Firewall '{group_name}' allows ALL {protocol} "
                                f"traffic from internet"
                            ),
                            description=(
                                f"Firewall group {group_id} has a rule accepting "
                                f"all {protocol} ports from 0.0.0.0/0."
                            ),
                            recommendation="Restrict to specific ports and source IPs.",
                        ))
                        continue

                    # Check specific sensitive ports
                    try:
                        port_num = int(port)
                    except ValueError:
                        continue

                    if port_num in _SENSITIVE_PORTS:
                        service = _SENSITIVE_PORTS[port_num]
                        findings.append(SecurityFinding(
                            severity=(
                                Severity.CRITICAL
                                if port_num in (22, 3389, 3306, 5432)
                                else Severity.HIGH
                            ),
                            resource_id=group_id,
                            resource_type="firewall_group",
                            provider="vultr",
                            title=(
                                f"Firewall '{group_name}' exposes {service} "
                                f"(port {port_num}) to internet"
                            ),
                            description=(
                                f"Firewall group {group_id} accepts {protocol} "
                                f"port {port_num} ({service}) from 0.0.0.0/0."
                            ),
                            recommendation=(
                                f"Restrict port {port_num} to specific source IPs."
                            ),
                        ))

        return findings

    async def _check_unprotected_instances(self) -> list[SecurityFinding]:
        """Flag instances without a firewall group attached."""
        instances = await self._auth.get_paginated("/instances", "instances")

        findings: list[SecurityFinding] = []
        for inst in instances:
            fw_group = inst.get("firewall_group_id", "")
            if not fw_group:
                inst_id = inst.get("id", "")
                label = inst.get("label", inst_id)
                findings.append(SecurityFinding(
                    severity=Severity.MEDIUM,
                    resource_id=inst_id,
                    resource_type="instance",
                    provider="vultr",
                    region=inst.get("region", ""),
                    title=f"Instance '{label}' has no firewall group",
                    description=(
                        f"Instance {inst_id} is not attached to any firewall group. "
                        "All ports may be exposed."
                    ),
                    recommendation="Attach a firewall group to restrict inbound traffic.",
                ))

        return findings

    async def _check_database_access(self) -> list[SecurityFinding]:
        """Flag managed databases with overly permissive trusted IPs."""
        databases = await self._auth.get_paginated("/databases", "databases")

        findings: list[SecurityFinding] = []
        for db in databases:
            db_id = db.get("id", "")
            label = db.get("label", db_id)
            trusted = db.get("trusted_ips", [])

            for ip in trusted:
                if ip in ("0.0.0.0/0", "0.0.0.0"):
                    findings.append(SecurityFinding(
                        severity=Severity.CRITICAL,
                        resource_id=db_id,
                        resource_type="managed_database",
                        provider="vultr",
                        region=db.get("region", ""),
                        title=f"Database '{label}' allows connections from all IPs",
                        description=(
                            f"Managed database {db_id} has 0.0.0.0/0 in trusted IPs."
                        ),
                        recommendation=(
                            "Remove 0.0.0.0/0 from trusted IPs and restrict "
                            "to specific IP ranges."
                        ),
                    ))

        return findings
