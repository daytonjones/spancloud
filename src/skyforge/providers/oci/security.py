"""OCI security auditor — common misconfigurations."""

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
    from skyforge.providers.oci.auth import OCIAuth

logger = get_logger(__name__)

_SENSITIVE_PORTS = {22, 3389, 3306, 5432, 1433, 6379, 27017, 5984}


class OCISecurityAuditor:
    """Scans OCI for common security issues."""

    def __init__(self, auth: OCIAuth) -> None:
        self._auth = auth

    async def run_audit(
        self, region: str | None = None
    ) -> SecurityAuditResult:
        _ = region
        findings_list = await asyncio.gather(
            asyncio.to_thread(self._check_security_lists),
            asyncio.to_thread(self._check_buckets_public),
        )
        all_findings: list[SecurityFinding] = []
        for group in findings_list:
            all_findings.extend(group)
        return SecurityAuditResult(
            provider="oci",
            findings=all_findings,
            regions_scanned=[self._auth.region or "default"],
        )

    def _check_security_lists(self) -> list[SecurityFinding]:
        """Flag security-list ingress rules that allow sensitive ports from 0.0.0.0/0."""
        import oci

        findings: list[SecurityFinding] = []
        compartment = self._auth.compartment_id
        if not compartment:
            return findings

        try:
            client = oci.core.VirtualNetworkClient(self._auth.config)
            page: str | None = None
            while True:
                result = client.list_security_lists(
                    compartment_id=compartment, page=page
                )
                for sl in result.data or []:
                    for rule in sl.ingress_security_rules or []:
                        finding = self._check_rule(sl, rule)
                        if finding:
                            findings.append(finding)
                page = result.next_page
                if not page:
                    break
        except Exception as exc:
            logger.debug("Security-list audit skipped: %s", exc)
        return findings

    def _check_rule(self, sl: Any, rule: Any) -> SecurityFinding | None:
        source = getattr(rule, "source", "") or ""
        if source != "0.0.0.0/0":
            return None

        tcp_opts = getattr(rule, "tcp_options", None)
        udp_opts = getattr(rule, "udp_options", None)

        sensitive_hits: list[int] = []
        for opts in (tcp_opts, udp_opts):
            if not opts:
                continue
            dest = getattr(opts, "destination_port_range", None)
            if not dest:
                # No port restriction = all ports = include all sensitive
                sensitive_hits.extend(_SENSITIVE_PORTS)
                break
            low = getattr(dest, "min", 0)
            high = getattr(dest, "max", 0)
            for port in _SENSITIVE_PORTS:
                if low <= port <= high:
                    sensitive_hits.append(port)

        if not sensitive_hits:
            return None

        severity = (
            Severity.CRITICAL
            if tcp_opts and not getattr(tcp_opts, "destination_port_range", None)
            else Severity.HIGH
        )
        return SecurityFinding(
            severity=severity,
            resource_id=sl.id,
            resource_type="security_list",
            provider="oci",
            region=self._auth.region or "",
            title=f"Security list '{sl.display_name}' exposes sensitive ports to the internet",
            description=(
                f"Ingress rule allows {sorted(set(sensitive_hits))} "
                "from 0.0.0.0/0."
            ),
            recommendation=(
                "Restrict source CIDRs or place the resource behind a bastion."
            ),
        )

    def _check_buckets_public(self) -> list[SecurityFinding]:
        """Flag buckets with PublicAccessType != NoPublicAccess."""
        import oci

        findings: list[SecurityFinding] = []
        compartment = self._auth.compartment_id
        if not compartment:
            return findings

        try:
            client = oci.object_storage.ObjectStorageClient(self._auth.config)
            namespace = client.get_namespace().data
        except Exception as exc:
            logger.debug("Namespace fetch failed: %s", exc)
            return findings

        try:
            buckets_result = client.list_buckets(
                namespace_name=namespace, compartment_id=compartment
            )
            for b in buckets_result.data or []:
                try:
                    detail = client.get_bucket(
                        namespace_name=namespace, bucket_name=b.name
                    ).data
                except Exception:
                    continue
                access = str(getattr(detail, "public_access_type", "") or "")
                if access and access != "NoPublicAccess":
                    findings.append(
                        SecurityFinding(
                            severity=Severity.HIGH,
                            resource_id=f"{namespace}/{b.name}",
                            resource_type="object_storage_bucket",
                            provider="oci",
                            region=self._auth.region or "",
                            title=f"Bucket '{b.name}' allows public access",
                            description=f"public_access_type = {access}",
                            recommendation=(
                                "Set to NoPublicAccess unless serving public content."
                            ),
                        )
                    )
        except Exception as exc:
            logger.debug("Bucket audit skipped: %s", exc)
        return findings
