"""AWS security audit — scans for common misconfigurations.

Checks:
- Security groups with 0.0.0.0/0 ingress on sensitive ports
- S3 buckets with public access
- RDS instances publicly accessible
- Unencrypted EBS volumes
- Default VPC in use
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from spancloud.analysis.models import SecurityAuditResult, SecurityFinding, Severity
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff
from spancloud.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from spancloud.providers.aws.auth import AWSAuth

logger = get_logger(__name__)

_EC2_LIMITER = RateLimiter(calls_per_second=10.0, max_concurrency=10)

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
    5900: "VNC",
    445: "SMB",
    23: "Telnet",
}


class AWSSecurityAuditor:
    """Scans AWS resources for security misconfigurations.

    Fetches resources in batches with rate limiting to avoid
    throttling, then analyzes them locally.
    """

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def run_audit(self, region: str | None = None) -> SecurityAuditResult:
        """Run a full security audit across configured checks.

        Args:
            region: AWS region to scan. If None, uses default.

        Returns:
            SecurityAuditResult with all findings.
        """
        regions = [region] if region else [None]

        # Run all checks in parallel
        tasks = [
            self._check_security_groups(region),
            self._check_s3_public_access(),
            self._check_rds_public(region),
            self._check_ebs_encryption(region),
            self._check_default_vpc(region),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        findings: list[SecurityFinding] = []
        for result in results:
            if isinstance(result, list):
                findings.extend(result)
            elif isinstance(result, Exception):
                logger.warning("Security check failed: %s", result)

        return SecurityAuditResult(
            provider="aws",
            findings=findings,
            regions_scanned=[r or "default" for r in regions],
        )

    async def _check_security_groups(
        self, region: str | None = None
    ) -> list[SecurityFinding]:
        """Flag security groups with 0.0.0.0/0 or ::/0 ingress on sensitive ports."""
        ec2 = self._auth.client("ec2", region=region)

        async with _EC2_LIMITER:
            response = await asyncio.to_thread(ec2.describe_security_groups)

        findings: list[SecurityFinding] = []
        for sg in response.get("SecurityGroups", []):
            sg_id = sg["GroupId"]
            sg_name = sg.get("GroupName", sg_id)

            for rule in sg.get("IpPermissions", []):
                from_port = rule.get("FromPort", 0)
                to_port = rule.get("ToPort", 65535)
                protocol = rule.get("IpProtocol", "")

                # Check for open CIDR ranges
                open_ranges = [
                    r["CidrIp"]
                    for r in rule.get("IpRanges", [])
                    if r.get("CidrIp") in ("0.0.0.0/0",)
                ] + [
                    r["CidrIpv6"]
                    for r in rule.get("Ipv6Ranges", [])
                    if r.get("CidrIpv6") in ("::/0",)
                ]

                if not open_ranges:
                    continue

                # All traffic open
                if protocol == "-1":
                    findings.append(
                        SecurityFinding(
                            severity=Severity.CRITICAL,
                            resource_id=sg_id,
                            resource_type="security_group",
                            provider="aws",
                            region=region or "",
                            title=f"SG '{sg_name}' allows ALL inbound traffic from internet",
                            description=(
                                f"Security group {sg_id} has an ingress rule allowing "
                                f"all protocols/ports from {', '.join(open_ranges)}."
                            ),
                            recommendation="Restrict ingress to specific ports and source IPs.",
                        )
                    )
                    continue

                # Check each sensitive port
                for port, service in _SENSITIVE_PORTS.items():
                    if from_port <= port <= to_port:
                        severity = (
                            Severity.CRITICAL
                            if port in (22, 3389, 3306, 5432)
                            else Severity.HIGH
                        )
                        findings.append(
                            SecurityFinding(
                                severity=severity,
                                resource_id=sg_id,
                                resource_type="security_group",
                                provider="aws",
                                region=region or "",
                                title=f"SG '{sg_name}' exposes {service} (port {port}) to internet",
                                description=(
                                    f"Security group {sg_id} allows ingress on port "
                                    f"{port} ({service}) from {', '.join(open_ranges)}."
                                ),
                                recommendation=(
                                    f"Restrict port {port} to specific IP ranges or "
                                    f"use a bastion host / VPN."
                                ),
                            )
                        )

        return findings

    async def _check_s3_public_access(self) -> list[SecurityFinding]:
        """Flag S3 buckets with public access or missing block settings."""
        s3 = self._auth.client("s3")

        async with _EC2_LIMITER:
            buckets_resp = await asyncio.to_thread(s3.list_buckets)

        findings: list[SecurityFinding] = []
        for bucket in buckets_resp.get("Buckets", []):
            name = bucket["Name"]
            try:
                async with _EC2_LIMITER:
                    pab = await asyncio.to_thread(
                        s3.get_public_access_block, Bucket=name
                    )
                config = pab.get("PublicAccessBlockConfiguration", {})
                if not all([
                    config.get("BlockPublicAcls", False),
                    config.get("IgnorePublicAcls", False),
                    config.get("BlockPublicPolicy", False),
                    config.get("RestrictPublicBuckets", False),
                ]):
                    findings.append(
                        SecurityFinding(
                            severity=Severity.HIGH,
                            resource_id=name,
                            resource_type="s3_bucket",
                            provider="aws",
                            title=f"S3 bucket '{name}' has incomplete public access block",
                            description=(
                                f"Bucket {name} does not have all four public access "
                                "block settings enabled."
                            ),
                            recommendation=(
                                "Enable all public access block settings unless "
                                "public access is intentionally required."
                            ),
                        )
                    )
            except Exception as exc:
                if "NoSuchPublicAccessBlockConfiguration" in str(exc):
                    findings.append(
                        SecurityFinding(
                            severity=Severity.HIGH,
                            resource_id=name,
                            resource_type="s3_bucket",
                            provider="aws",
                            title=f"S3 bucket '{name}' has no public access block",
                            description=f"Bucket {name} has no public access block configured.",
                            recommendation="Enable S3 Block Public Access on this bucket.",
                        )
                    )
                else:
                    logger.debug("Could not check bucket %s: %s", name, exc)

        return findings

    async def _check_rds_public(
        self, region: str | None = None
    ) -> list[SecurityFinding]:
        """Flag RDS instances that are publicly accessible."""
        rds = self._auth.client("rds", region=region)

        async with _EC2_LIMITER:
            paginator = rds.get_paginator("describe_db_instances")
            pages = await asyncio.to_thread(lambda: list(paginator.paginate()))

        findings: list[SecurityFinding] = []
        for page in pages:
            for db in page.get("DBInstances", []):
                if db.get("PubliclyAccessible", False):
                    db_id = db["DBInstanceIdentifier"]
                    engine = db.get("Engine", "unknown")
                    findings.append(
                        SecurityFinding(
                            severity=Severity.HIGH,
                            resource_id=db_id,
                            resource_type="rds_instance",
                            provider="aws",
                            region=region or "",
                            title=f"RDS instance '{db_id}' ({engine}) is publicly accessible",
                            description=(
                                f"RDS instance {db_id} has PubliclyAccessible=True, "
                                "meaning it can accept connections from the internet."
                            ),
                            recommendation=(
                                "Disable public access and use VPC peering, "
                                "a bastion host, or VPN for connectivity."
                            ),
                        )
                    )

        return findings

    async def _check_ebs_encryption(
        self, region: str | None = None
    ) -> list[SecurityFinding]:
        """Flag unencrypted EBS volumes."""
        ec2 = self._auth.client("ec2", region=region)

        async with _EC2_LIMITER:
            paginator = ec2.get_paginator("describe_volumes")
            pages = await asyncio.to_thread(lambda: list(paginator.paginate()))

        findings: list[SecurityFinding] = []
        for page in pages:
            for vol in page.get("Volumes", []):
                if not vol.get("Encrypted", False):
                    vol_id = vol["VolumeId"]
                    size = vol.get("Size", "?")
                    findings.append(
                        SecurityFinding(
                            severity=Severity.MEDIUM,
                            resource_id=vol_id,
                            resource_type="ebs_volume",
                            provider="aws",
                            region=region or "",
                            title=f"EBS volume '{vol_id}' ({size} GB) is not encrypted",
                            description=f"Volume {vol_id} does not have encryption enabled.",
                            recommendation=(
                                "Enable encryption for EBS volumes. "
                                "Create an encrypted snapshot and restore to a new volume."
                            ),
                        )
                    )

        return findings

    async def _check_default_vpc(
        self, region: str | None = None
    ) -> list[SecurityFinding]:
        """Flag usage of the default VPC (often misconfigured)."""
        ec2 = self._auth.client("ec2", region=region)

        async with _EC2_LIMITER:
            response = await asyncio.to_thread(ec2.describe_vpcs)

        findings: list[SecurityFinding] = []
        for vpc in response.get("Vpcs", []):
            if vpc.get("IsDefault", False):
                vpc_id = vpc["VpcId"]

                # Check if any instances are running in the default VPC
                async with _EC2_LIMITER:
                    instances = await asyncio.to_thread(
                        ec2.describe_instances,
                        Filters=[{"Name": "vpc-id", "Values": [vpc_id]}],
                    )

                inst_count = sum(
                    len(r.get("Instances", []))
                    for r in instances.get("Reservations", [])
                )

                if inst_count > 0:
                    findings.append(
                        SecurityFinding(
                            severity=Severity.MEDIUM,
                            resource_id=vpc_id,
                            resource_type="vpc",
                            provider="aws",
                            region=region or "",
                            title=f"Default VPC '{vpc_id}' has {inst_count} running instance(s)",
                            description=(
                                f"The default VPC {vpc_id} contains {inst_count} instances. "
                                "Default VPCs have overly permissive default security settings."
                            ),
                            recommendation=(
                                "Migrate workloads to a purpose-built VPC with "
                                "tighter network controls."
                            ),
                        )
                    )

        return findings
