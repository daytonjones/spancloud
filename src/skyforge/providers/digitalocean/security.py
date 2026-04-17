"""DigitalOcean security audit."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from skyforge.analysis.models import SecurityAuditResult, SecurityFinding, Severity
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.digitalocean.auth import DigitalOceanAuth

logger = get_logger(__name__)

_SENSITIVE_PORTS: dict[int, str] = {
    22: "SSH",
    3389: "RDP",
    3306: "MySQL",
    5432: "PostgreSQL",
    27017: "MongoDB",
    6379: "Redis",
}


class DigitalOceanSecurityAuditor:
    """Scans DigitalOcean resources for security misconfigurations."""

    def __init__(self, auth: DigitalOceanAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def run_audit(self, region: str | None = None) -> SecurityAuditResult:
        """Run a full security audit."""
        tasks = [
            self._check_firewalls(),
            self._check_unprotected_droplets(),
            self._check_database_access(),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        findings: list[SecurityFinding] = []
        for result in results:
            if isinstance(result, list):
                findings.extend(result)
            elif isinstance(result, Exception):
                logger.warning("DO security check failed: %s", result)

        return SecurityAuditResult(
            provider="digitalocean",
            findings=findings,
            regions_scanned=[region or "all"],
        )

    async def _check_firewalls(self) -> list[SecurityFinding]:
        """Flag firewalls with open inbound rules on sensitive ports."""
        firewalls = await self._auth.get_paginated("/firewalls", "firewalls")

        findings: list[SecurityFinding] = []
        for fw in firewalls:
            fw_id = fw.get("id", "")
            fw_name = fw.get("name", fw_id)

            for rule in fw.get("inbound_rules") or []:
                protocol = rule.get("protocol", "")
                ports = rule.get("ports", "")
                sources = rule.get("sources", {})
                addresses = sources.get("addresses") or []

                # Check for 0.0.0.0/0 or ::/0
                wide_open = any(
                    a in ("0.0.0.0/0", "::/0") for a in addresses
                )
                if not wide_open:
                    continue

                # All traffic
                if protocol == "icmp" or ports in ("0", "all", ""):
                    findings.append(SecurityFinding(
                        severity=Severity.CRITICAL,
                        resource_id=fw_id,
                        resource_type="firewall",
                        provider="digitalocean",
                        title=(
                            f"Firewall '{fw_name}' allows ALL {protocol} "
                            f"from internet"
                        ),
                        description=(
                            f"Firewall {fw_id} has an inbound rule for "
                            f"{protocol} from 0.0.0.0/0."
                        ),
                        recommendation="Restrict to specific source IPs.",
                    ))
                    continue

                # Parse port range
                try:
                    if "-" in str(ports):
                        parts = str(ports).split("-")
                        from_port, to_port = int(parts[0]), int(parts[1])
                    else:
                        from_port = to_port = int(ports)
                except ValueError:
                    continue

                for port, service in _SENSITIVE_PORTS.items():
                    if from_port <= port <= to_port:
                        severity = (
                            Severity.CRITICAL
                            if port in (22, 3389, 3306, 5432)
                            else Severity.HIGH
                        )
                        findings.append(SecurityFinding(
                            severity=severity,
                            resource_id=fw_id,
                            resource_type="firewall",
                            provider="digitalocean",
                            title=(
                                f"Firewall '{fw_name}' exposes {service} "
                                f"(port {port}) to internet"
                            ),
                            description=(
                                f"Firewall {fw_id} allows {protocol} port "
                                f"{port} ({service}) from 0.0.0.0/0."
                            ),
                            recommendation=(
                                f"Restrict port {port} to specific source IPs."
                            ),
                        ))

        return findings

    async def _check_unprotected_droplets(self) -> list[SecurityFinding]:
        """Flag droplets not attached to any firewall."""
        # Get all droplets with firewalls
        droplets = await self._auth.get_paginated("/droplets", "droplets")
        firewalls = await self._auth.get_paginated("/firewalls", "firewalls")

        # Build set of droplet IDs that have firewalls
        protected: set[int] = set()
        for fw in firewalls:
            for did in fw.get("droplet_ids") or []:
                protected.add(did)

        findings: list[SecurityFinding] = []
        for d in droplets:
            did = d.get("id")
            if did and did not in protected:
                name = d.get("name", str(did))
                findings.append(SecurityFinding(
                    severity=Severity.MEDIUM,
                    resource_id=str(did),
                    resource_type="droplet",
                    provider="digitalocean",
                    region=(d.get("region") or {}).get("slug", ""),
                    title=f"Droplet '{name}' has no firewall",
                    description=(
                        f"Droplet {did} is not attached to any cloud firewall. "
                        "All ports may be exposed."
                    ),
                    recommendation=(
                        "Attach a cloud firewall to restrict inbound traffic."
                    ),
                ))

        return findings

    async def _check_database_access(self) -> list[SecurityFinding]:
        """Flag managed databases with overly permissive trusted sources."""
        try:
            dbs = await self._auth.get_paginated("/databases", "databases")
        except Exception:
            return []

        findings: list[SecurityFinding] = []
        for db in dbs:
            db_id = db.get("id", "")
            name = db.get("name", db_id)

            # Check firewall rules for the database
            try:
                fw_data = await self._auth.get(f"/databases/{db_id}/firewall")
            except Exception:
                continue

            rules = fw_data.get("rules") or []
            for rule in rules:
                rule_type = rule.get("type", "")
                value = rule.get("value", "")
                # Wide-open IP
                if rule_type == "ip_addr" and value in ("0.0.0.0/0", "0.0.0.0"):
                    findings.append(SecurityFinding(
                        severity=Severity.CRITICAL,
                        resource_id=db_id,
                        resource_type="managed_database",
                        provider="digitalocean",
                        region=db.get("region", ""),
                        title=f"Database '{name}' allows connections from all IPs",
                        description=(
                            f"Managed database {db_id} has 0.0.0.0/0 in "
                            "trusted sources."
                        ),
                        recommendation=(
                            "Remove 0.0.0.0/0 and restrict to specific IPs/droplets."
                        ),
                    ))

        return findings
