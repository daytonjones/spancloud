"""Alibaba security auditor — common misconfigurations."""

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
    from skyforge.providers.alibaba.auth import AlibabaAuth

logger = get_logger(__name__)

_SENSITIVE_PORTS = {"22", "3389", "3306", "5432", "1433", "6379", "27017", "5984"}


class AlibabaSecurityAuditor:
    """Scans Alibaba Cloud for common security issues."""

    def __init__(self, auth: AlibabaAuth) -> None:
        self._auth = auth

    async def run_audit(
        self, region: str | None = None
    ) -> SecurityAuditResult:
        findings_list = await asyncio.gather(
            asyncio.to_thread(self._check_security_groups, region),
            asyncio.to_thread(self._check_public_oss, region),
        )
        all_findings: list[SecurityFinding] = []
        for group in findings_list:
            all_findings.extend(group)
        return SecurityAuditResult(
            provider="alibaba",
            findings=all_findings,
            regions_scanned=[region or self._auth.region],
        )

    def _check_security_groups(
        self, region: str | None
    ) -> list[SecurityFinding]:
        """Flag security-group ingress rules allowing sensitive ports from 0.0.0.0/0."""
        from alibabacloud_ecs20140526 import models as ecs_models
        from alibabacloud_ecs20140526.client import Client as EcsClient

        findings: list[SecurityFinding] = []
        region_id = region or self._auth.region
        try:
            client = EcsClient(self._auth.ecs_config(region_id))

            # List SGs, then describe each one's rules
            page_number = 1
            sg_ids: list[tuple[str, str]] = []
            while True:
                req = ecs_models.DescribeSecurityGroupsRequest(
                    region_id=region_id,
                    page_number=page_number,
                    page_size=50,
                )
                response = client.describe_security_groups(req)
                body = response.body
                holder = getattr(body, "security_groups", None)
                sg_list = (
                    getattr(holder, "security_group", []) or []
                    if holder
                    else []
                )
                if not sg_list:
                    break
                for sg in sg_list:
                    sg_ids.append(
                        (
                            getattr(sg, "security_group_id", "") or "",
                            getattr(sg, "security_group_name", "") or "",
                        )
                    )
                total = getattr(body, "total_count", 0) or 0
                if page_number * 50 >= total:
                    break
                page_number += 1

            for sg_id, sg_name in sg_ids:
                try:
                    attr_resp = client.describe_security_group_attribute(
                        ecs_models.DescribeSecurityGroupAttributeRequest(
                            region_id=region_id,
                            security_group_id=sg_id,
                        )
                    )
                except Exception:
                    continue
                permissions = getattr(attr_resp.body, "permissions", None)
                rules = (
                    getattr(permissions, "permission", []) or []
                    if permissions
                    else []
                )
                for rule in rules:
                    finding = self._rule_finding(sg_id, sg_name, rule, region_id)
                    if finding:
                        findings.append(finding)
        except Exception as exc:
            logger.debug("SG audit skipped: %s", exc)
        return findings

    def _rule_finding(
        self, sg_id: str, sg_name: str, rule: Any, region: str
    ) -> SecurityFinding | None:
        direction = str(getattr(rule, "direction", "") or "")
        if direction.lower() != "ingress":
            return None
        policy = str(getattr(rule, "policy", "") or "")
        if policy.lower() != "accept":
            return None
        source = str(getattr(rule, "source_cidr_ip", "") or "")
        if source not in ("0.0.0.0/0", "::/0"):
            return None

        port_range = str(getattr(rule, "port_range", "") or "")
        hits: list[str] = []
        for port in _SENSITIVE_PORTS:
            if _port_in_range(port, port_range):
                hits.append(port)

        if not hits:
            return None

        severity = (
            Severity.CRITICAL if port_range in ("-1/-1", "1/65535") else Severity.HIGH
        )
        return SecurityFinding(
            severity=severity,
            resource_id=sg_id,
            resource_type="security_group",
            provider="alibaba",
            region=region,
            title=f"Security group '{sg_name or sg_id}' exposes sensitive ports to internet",
            description=(
                f"Rule allows {', '.join(sorted(hits))} (port range {port_range}) "
                f"from {source}."
            ),
            recommendation="Restrict source CIDR or use a bastion/VPN.",
        )

    def _check_public_oss(self, region: str | None) -> list[SecurityFinding]:
        """Flag OSS buckets with public ACL (public-read / public-read-write)."""
        findings: list[SecurityFinding] = []
        try:
            import oss2

            self._auth._ensure_credentials()  # noqa: SLF001
            if not self._auth.access_key_id:
                return findings

            region_id = region or self._auth.region
            endpoint = f"https://oss-{region_id}.aliyuncs.com"
            auth = oss2.Auth(
                self._auth.access_key_id,
                self._auth._access_key_secret,  # noqa: SLF001
            )
            service = oss2.Service(auth, endpoint)

            for bucket_info in oss2.BucketIterator(service):
                try:
                    bucket = oss2.Bucket(
                        auth,
                        f"https://{bucket_info.extranet_endpoint}",
                        bucket_info.name,
                    )
                    acl = bucket.get_bucket_acl().acl
                except Exception:
                    continue
                if str(acl).lower() in ("public-read", "public-read-write"):
                    severity = (
                        Severity.CRITICAL
                        if str(acl).lower() == "public-read-write"
                        else Severity.HIGH
                    )
                    findings.append(
                        SecurityFinding(
                            severity=severity,
                            resource_id=bucket_info.name,
                            resource_type="oss_bucket",
                            provider="alibaba",
                            region=bucket_info.location or region_id,
                            title=f"OSS bucket '{bucket_info.name}' has public ACL ({acl})",
                            description=(
                                f"Bucket ACL is '{acl}'. Any client can read "
                                + ("and write " if "write" in str(acl).lower() else "")
                                + "objects."
                            ),
                            recommendation="Set ACL to private unless hosting public content.",
                        )
                    )
        except Exception as exc:
            logger.debug("OSS ACL audit skipped: %s", exc)
        return findings


def _port_in_range(port_str: str, rule_range: str) -> bool:
    """Return True if `port_str` falls within `rule_range` (e.g. '22/22', '-1/-1')."""
    if rule_range in ("-1/-1", "1/65535"):
        return True
    try:
        low, high = rule_range.split("/", 1)
        port = int(port_str)
        return int(low) <= port <= int(high)
    except (ValueError, AttributeError):
        return False
