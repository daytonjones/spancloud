"""GCP security audit — scans for common misconfigurations.

Checks:
- Firewall rules allowing 0.0.0.0/0 on sensitive ports
- GCS buckets with allUsers/allAuthenticatedUsers
- Cloud SQL instances with public IP and no IP restrictions
- Unencrypted persistent disks
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from google.cloud import compute_v1, storage

from spancloud.analysis.models import SecurityAuditResult, SecurityFinding, Severity
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff
from spancloud.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from spancloud.providers.gcp.auth import GCPAuth

logger = get_logger(__name__)

_GCP_LIMITER = RateLimiter(calls_per_second=8.0, max_concurrency=10)

# Ports that are especially dangerous when open to the internet
_SENSITIVE_PORTS: dict[int, str] = {
    22: "SSH",
    3389: "RDP",
    3306: "MySQL",
    5432: "PostgreSQL",
    1433: "MSSQL",
    27017: "MongoDB",
    6379: "Redis",
    9200: "Elasticsearch",
}


class GCPSecurityAuditor:
    """Scans GCP resources for security misconfigurations.

    Fetches resources with rate limiting, analyzes locally.
    """

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def run_audit(self, region: str | None = None) -> SecurityAuditResult:
        """Run a full security audit.

        Args:
            region: Ignored for most global checks but passed for consistency.

        Returns:
            SecurityAuditResult with all findings.
        """
        project = self._auth.project_id
        if not project:
            return SecurityAuditResult(provider="gcp")

        tasks = [
            self._check_firewall_rules(project),
            self._check_gcs_public_access(project),
            self._check_cloudsql_public(project),
            self._check_disk_encryption(project),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        findings: list[SecurityFinding] = []
        for result in results:
            if isinstance(result, list):
                findings.extend(result)
            elif isinstance(result, Exception):
                logger.warning("GCP security check failed: %s", result)

        return SecurityAuditResult(
            provider="gcp",
            findings=findings,
            regions_scanned=[region or "global"],
        )

    async def _check_firewall_rules(self, project: str) -> list[SecurityFinding]:
        """Flag firewall rules allowing 0.0.0.0/0 on sensitive ports."""
        client = compute_v1.FirewallsClient(credentials=self._auth.credentials)

        async with _GCP_LIMITER:
            firewalls = await asyncio.to_thread(lambda: list(client.list(project=project)))

        findings: list[SecurityFinding] = []
        for fw in firewalls:
            if fw.disabled:
                continue

            if fw.direction != "INGRESS":
                continue

            source_ranges = list(fw.source_ranges) if fw.source_ranges else []
            if "0.0.0.0/0" not in source_ranges:
                continue

            allowed = fw.allowed or []
            for rule in allowed:
                protocol = rule.I_p_protocol if hasattr(rule, "I_p_protocol") else ""
                ports = list(rule.ports) if rule.ports else []

                # All traffic
                if protocol == "all" or (not ports and protocol in ("tcp", "udp")):
                    findings.append(
                        SecurityFinding(
                            severity=Severity.CRITICAL,
                            resource_id=fw.name or str(fw.id),
                            resource_type="firewall_rule",
                            provider="gcp",
                            region="global",
                            title=(
                                f"Firewall '{fw.name}' allows ALL {protocol} "
                                f"traffic from internet"
                            ),
                            description=(
                                f"Firewall rule {fw.name} allows {protocol} on all "
                                f"ports from 0.0.0.0/0."
                            ),
                            recommendation="Restrict to specific ports and source IP ranges.",
                        )
                    )
                    continue

                # Check specific ports
                for port_spec in ports:
                    port_range = self._parse_port_range(port_spec)
                    for port, service in _SENSITIVE_PORTS.items():
                        if port_range[0] <= port <= port_range[1]:
                            severity = (
                                Severity.CRITICAL
                                if port in (22, 3389, 3306, 5432)
                                else Severity.HIGH
                            )
                            findings.append(
                                SecurityFinding(
                                    severity=severity,
                                    resource_id=fw.name or str(fw.id),
                                    resource_type="firewall_rule",
                                    provider="gcp",
                                    region="global",
                                    title=(
                                        f"Firewall '{fw.name}' exposes {service} "
                                        f"(port {port}) to internet"
                                    ),
                                    description=(
                                        f"Firewall rule {fw.name} allows {protocol} on "
                                        f"port {port} ({service}) from 0.0.0.0/0."
                                    ),
                                    recommendation=(
                                        f"Restrict port {port} to specific source IPs "
                                        f"or use IAP for SSH/RDP."
                                    ),
                                )
                            )

        return findings

    def _parse_port_range(self, port_spec: str) -> tuple[int, int]:
        """Parse a port spec like '80', '8080-8090' into (start, end)."""
        if "-" in port_spec:
            parts = port_spec.split("-", 1)
            return int(parts[0]), int(parts[1])
        return int(port_spec), int(port_spec)

    async def _check_gcs_public_access(self, project: str) -> list[SecurityFinding]:
        """Flag GCS buckets accessible to allUsers or allAuthenticatedUsers."""
        client = storage.Client(
            project=project,
            credentials=self._auth.credentials,
        )

        async with _GCP_LIMITER:
            buckets = await asyncio.to_thread(lambda: list(client.list_buckets()))

        findings: list[SecurityFinding] = []
        for bucket in buckets:
            try:
                async with _GCP_LIMITER:
                    policy = await asyncio.to_thread(bucket.get_iam_policy)

                for binding in policy.bindings:
                    members = binding.get("members", set())
                    if "allUsers" in members or "allAuthenticatedUsers" in members:
                        principal = (
                            "allUsers (anonymous)"
                            if "allUsers" in members
                            else "allAuthenticatedUsers"
                        )
                        findings.append(
                            SecurityFinding(
                                severity=Severity.HIGH,
                                resource_id=bucket.name,
                                resource_type="gcs_bucket",
                                provider="gcp",
                                title=(
                                    f"GCS bucket '{bucket.name}' grants "
                                    f"'{binding['role']}' to {principal}"
                                ),
                                description=(
                                    f"Bucket {bucket.name} has IAM binding granting "
                                    f"role '{binding['role']}' to {principal}."
                                ),
                                recommendation=(
                                    "Remove public access unless intentionally needed. "
                                    "Use uniform bucket-level access."
                                ),
                            )
                        )
            except Exception as exc:
                logger.debug("Could not check bucket %s IAM: %s", bucket.name, exc)

        return findings

    async def _check_cloudsql_public(self, project: str) -> list[SecurityFinding]:
        """Flag Cloud SQL instances with public IP and weak IP restrictions."""
        from googleapiclient.discovery import build

        def _fetch() -> list[dict[str, Any]]:
            service = build(
                "sqladmin", "v1",
                credentials=self._auth.credentials,
                cache_discovery=False,
            )
            try:
                response = service.instances().list(project=project).execute()
                return response.get("items", [])
            except Exception as exc:
                logger.debug("Could not list Cloud SQL instances: %s", exc)
                return []

        async with _GCP_LIMITER:
            instances = await asyncio.to_thread(_fetch)

        findings: list[SecurityFinding] = []
        for inst in instances:
            name = inst.get("name", "")
            ip_addrs = inst.get("ipAddresses", [])
            settings = inst.get("settings", {})
            ip_config = settings.get("ipConfiguration", {})

            has_public_ip = any(
                a.get("type") == "PRIMARY" for a in ip_addrs
            )
            authorized_nets = ip_config.get("authorizedNetworks", [])
            require_ssl = ip_config.get("requireSsl", False)

            if has_public_ip:
                # Check for 0.0.0.0/0 in authorized networks
                wide_open = any(
                    n.get("value") in ("0.0.0.0/0", "0.0.0.0")
                    for n in authorized_nets
                )

                if wide_open:
                    findings.append(
                        SecurityFinding(
                            severity=Severity.CRITICAL,
                            resource_id=name,
                            resource_type="cloudsql_instance",
                            provider="gcp",
                            region=inst.get("region", ""),
                            title=(
                                f"Cloud SQL '{name}' is open to the entire internet"
                            ),
                            description=(
                                f"Instance {name} has a public IP with 0.0.0.0/0 "
                                "in authorized networks."
                            ),
                            recommendation=(
                                "Remove 0.0.0.0/0 from authorized networks. "
                                "Use Cloud SQL Proxy or Private IP."
                            ),
                        )
                    )
                elif not require_ssl:
                    findings.append(
                        SecurityFinding(
                            severity=Severity.MEDIUM,
                            resource_id=name,
                            resource_type="cloudsql_instance",
                            provider="gcp",
                            region=inst.get("region", ""),
                            title=f"Cloud SQL '{name}' has public IP without SSL required",
                            description=(
                                f"Instance {name} has a public IP but doesn't require SSL."
                            ),
                            recommendation="Enable 'Require SSL' in IP configuration.",
                        )
                    )

        return findings

    async def _check_disk_encryption(self, project: str) -> list[SecurityFinding]:
        """Flag persistent disks without customer-managed encryption keys.

        Note: All GCP disks are encrypted at rest by default with Google-managed keys.
        This check flags disks not using CMEK (a stricter compliance requirement).
        """
        client = compute_v1.DisksClient(credentials=self._auth.credentials)

        def _fetch() -> list[dict[str, Any]]:
            disks: list[dict[str, Any]] = []
            request = compute_v1.AggregatedListDisksRequest(project=project)
            for _zone, scoped_list in client.aggregated_list(request=request):
                for disk in scoped_list.disks or []:
                    disks.append({
                        "name": disk.name,
                        "id": str(disk.id),
                        "zone": (disk.zone or "").rsplit("/", 1)[-1],
                        "size_gb": disk.size_gb,
                        "has_cmek": bool(
                            disk.disk_encryption_key
                            and disk.disk_encryption_key.kms_key_name
                        ),
                    })
            return disks

        async with _GCP_LIMITER:
            disks = await asyncio.to_thread(_fetch)

        findings: list[SecurityFinding] = []
        for disk in disks:
            if not disk["has_cmek"]:
                findings.append(
                    SecurityFinding(
                        severity=Severity.LOW,
                        resource_id=disk["name"],
                        resource_type="persistent_disk",
                        provider="gcp",
                        region=disk["zone"],
                        title=(
                            f"Disk '{disk['name']}' ({disk['size_gb']} GB) "
                            f"uses Google-managed encryption"
                        ),
                        description=(
                            f"Disk {disk['name']} is encrypted with Google-managed keys "
                            "rather than customer-managed encryption keys (CMEK)."
                        ),
                        recommendation=(
                            "If compliance requires CMEK, recreate the disk with "
                            "a Cloud KMS key. Google-managed encryption is still "
                            "encrypted at rest."
                        ),
                    )
                )

        return findings
