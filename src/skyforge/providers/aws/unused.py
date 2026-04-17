"""AWS unused resource detection.

Finds:
- Unattached EBS volumes
- Unused Elastic IPs
- Idle load balancers (no healthy targets)
- Old snapshots without associated AMIs
- EC2 instances stopped for extended periods
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from skyforge.analysis.models import UnusedResource, UnusedResourceReport
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff
from skyforge.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from skyforge.providers.aws.auth import AWSAuth

logger = get_logger(__name__)

_EC2_LIMITER = RateLimiter(calls_per_second=10.0, max_concurrency=10)


class AWSUnusedDetector:
    """Finds unused or idle AWS resources that may be wasting money.

    All checks use rate limiting and pagination to avoid throttling.
    """

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def scan(
        self,
        region: str | None = None,
        stopped_days_threshold: int = 30,
        snapshot_days_threshold: int = 90,
    ) -> UnusedResourceReport:
        """Scan for unused resources.

        Args:
            region: AWS region to scan.
            stopped_days_threshold: Days an instance must be stopped to flag.
            snapshot_days_threshold: Days since snapshot creation without AMI.

        Returns:
            UnusedResourceReport with all identified waste.
        """
        tasks = [
            self._find_unattached_volumes(region),
            self._find_unused_eips(region),
            self._find_idle_load_balancers(region),
            self._find_old_snapshots(region, snapshot_days_threshold),
            self._find_long_stopped_instances(region, stopped_days_threshold),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        resources: list[UnusedResource] = []
        for result in results:
            if isinstance(result, list):
                resources.extend(result)
            elif isinstance(result, Exception):
                logger.warning("Unused detection check failed: %s", result)

        return UnusedResourceReport(provider="aws", resources=resources)

    async def _find_unattached_volumes(
        self, region: str | None = None
    ) -> list[UnusedResource]:
        """Find EBS volumes not attached to any instance."""
        ec2 = self._auth.client("ec2", region=region)

        async with _EC2_LIMITER:
            paginator = ec2.get_paginator("describe_volumes")
            pages = await asyncio.to_thread(
                lambda: list(paginator.paginate(
                    Filters=[{"Name": "status", "Values": ["available"]}]
                ))
            )

        resources: list[UnusedResource] = []
        for page in pages:
            for vol in page.get("Volumes", []):
                vol_id = vol["VolumeId"]
                size = vol.get("Size", 0)
                # Rough cost estimate: $0.08/GB/month for gp3
                est_monthly = f"~${size * 0.08:,.2f}/mo (gp3 rate)"

                resources.append(
                    UnusedResource(
                        resource_id=vol_id,
                        resource_name=vol_id,
                        resource_type="ebs_volume",
                        provider="aws",
                        region=region or "",
                        reason=f"Unattached {size} GB EBS volume",
                        estimated_monthly_savings=est_monthly,
                    )
                )

        return resources

    async def _find_unused_eips(
        self, region: str | None = None
    ) -> list[UnusedResource]:
        """Find Elastic IPs not associated with any instance or ENI."""
        ec2 = self._auth.client("ec2", region=region)

        async with _EC2_LIMITER:
            response = await asyncio.to_thread(ec2.describe_addresses)

        resources: list[UnusedResource] = []
        for addr in response.get("Addresses", []):
            if not addr.get("AssociationId"):
                eip = addr.get("PublicIp", addr.get("AllocationId", ""))
                resources.append(
                    UnusedResource(
                        resource_id=addr.get("AllocationId", eip),
                        resource_name=eip,
                        resource_type="elastic_ip",
                        provider="aws",
                        region=region or "",
                        reason=f"Elastic IP {eip} not associated with any resource",
                        estimated_monthly_savings="~$3.65/mo (idle EIP charge)",
                    )
                )

        return resources

    async def _find_idle_load_balancers(
        self, region: str | None = None
    ) -> list[UnusedResource]:
        """Find ALBs/NLBs with no healthy targets."""
        elbv2 = self._auth.client("elbv2", region=region)

        async with _EC2_LIMITER:
            paginator = elbv2.get_paginator("describe_load_balancers")
            pages = await asyncio.to_thread(lambda: list(paginator.paginate()))

        resources: list[UnusedResource] = []
        for page in pages:
            for lb in page.get("LoadBalancers", []):
                lb_arn = lb["LoadBalancerArn"]
                lb_name = lb.get("LoadBalancerName", "")
                lb_type = lb.get("Type", "application")

                # Check target groups for this LB
                try:
                    async with _EC2_LIMITER:
                        tg_resp = await asyncio.to_thread(
                            elbv2.describe_target_groups,
                            LoadBalancerArn=lb_arn,
                        )

                    target_groups = tg_resp.get("TargetGroups", [])
                    if not target_groups:
                        resources.append(
                            UnusedResource(
                                resource_id=lb_name,
                                resource_name=lb_name,
                                resource_type="load_balancer",
                                provider="aws",
                                region=region or "",
                                reason=(
                                    f"Load balancer '{lb_name}' ({lb_type}) "
                                    f"has no target groups"
                                ),
                                estimated_monthly_savings="~$16-22/mo (ALB/NLB base charge)",
                            )
                        )
                        continue

                    # Check if any targets are healthy
                    all_empty = True
                    for tg in target_groups:
                        async with _EC2_LIMITER:
                            health = await asyncio.to_thread(
                                elbv2.describe_target_health,
                                TargetGroupArn=tg["TargetGroupArn"],
                            )
                        if health.get("TargetHealthDescriptions"):
                            all_empty = False
                            break

                    if all_empty:
                        resources.append(
                            UnusedResource(
                                resource_id=lb_name,
                                resource_name=lb_name,
                                resource_type="load_balancer",
                                provider="aws",
                                region=region or "",
                                reason=(
                                    f"Load balancer '{lb_name}' ({lb_type}) "
                                    f"has no registered targets"
                                ),
                                estimated_monthly_savings="~$16-22/mo (ALB/NLB base charge)",
                            )
                        )
                except Exception as exc:
                    logger.debug("Could not check LB targets for %s: %s", lb_name, exc)

        return resources

    async def _find_old_snapshots(
        self, region: str | None = None, days_threshold: int = 90
    ) -> list[UnusedResource]:
        """Find snapshots older than threshold with no associated AMI."""
        ec2 = self._auth.client("ec2", region=region)
        cutoff = datetime.now(UTC) - timedelta(days=days_threshold)

        # Get owned snapshots
        async with _EC2_LIMITER:
            paginator = ec2.get_paginator("describe_snapshots")
            pages = await asyncio.to_thread(
                lambda: list(paginator.paginate(OwnerIds=["self"]))
            )

        # Get AMI snapshot IDs for cross-reference
        async with _EC2_LIMITER:
            ami_paginator = ec2.get_paginator("describe_images")
            ami_pages = await asyncio.to_thread(
                lambda: list(ami_paginator.paginate(Owners=["self"]))
            )

        ami_snapshot_ids: set[str] = set()
        for page in ami_pages:
            for image in page.get("Images", []):
                for bdm in image.get("BlockDeviceMappings", []):
                    ebs = bdm.get("Ebs", {})
                    if ebs.get("SnapshotId"):
                        ami_snapshot_ids.add(ebs["SnapshotId"])

        resources: list[UnusedResource] = []
        for page in pages:
            for snap in page.get("Snapshots", []):
                snap_id = snap["SnapshotId"]
                start_time = snap.get("StartTime")

                if not start_time or start_time > cutoff:
                    continue

                if snap_id in ami_snapshot_ids:
                    continue

                size = snap.get("VolumeSize", 0)
                est_monthly = f"~${size * 0.05:,.2f}/mo (snapshot storage)"

                resources.append(
                    UnusedResource(
                        resource_id=snap_id,
                        resource_name=snap.get("Description", snap_id)[:80],
                        resource_type="ebs_snapshot",
                        provider="aws",
                        region=region or "",
                        reason=(
                            f"Snapshot {snap_id} ({size} GB) is {days_threshold}+ days old "
                            f"with no AMI reference"
                        ),
                        last_used=start_time,
                        estimated_monthly_savings=est_monthly,
                    )
                )

        return resources

    async def _find_long_stopped_instances(
        self, region: str | None = None, days_threshold: int = 30
    ) -> list[UnusedResource]:
        """Find EC2 instances that have been stopped for an extended period."""
        ec2 = self._auth.client("ec2", region=region)

        async with _EC2_LIMITER:
            paginator = ec2.get_paginator("describe_instances")
            pages = await asyncio.to_thread(
                lambda: list(paginator.paginate(
                    Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
                ))
            )

        cutoff = datetime.now(UTC) - timedelta(days=days_threshold)
        resources: list[UnusedResource] = []

        for page in pages:
            for reservation in page.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    inst_id = inst["InstanceId"]
                    launch_time = inst.get("LaunchTime")

                    # If we can't determine when it stopped, use launch time
                    if launch_time and launch_time < cutoff:
                        tags = {
                            t["Key"]: t["Value"]
                            for t in inst.get("Tags", [])
                        }
                        name = tags.get("Name", inst_id)
                        inst_type = inst.get("InstanceType", "")

                        resources.append(
                            UnusedResource(
                                resource_id=inst_id,
                                resource_name=name,
                                resource_type="ec2_instance",
                                provider="aws",
                                region=region or "",
                                reason=(
                                    f"Instance '{name}' ({inst_type}) stopped for "
                                    f"{days_threshold}+ days"
                                ),
                                last_used=launch_time,
                                estimated_monthly_savings=(
                                    "EBS charges still apply for attached volumes"
                                ),
                            )
                        )

        return resources
