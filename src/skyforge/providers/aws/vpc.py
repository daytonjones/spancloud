"""AWS VPC, Subnet, and Security Group resource discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.aws.auth import AWSAuth

logger = get_logger(__name__)


def _parse_tags(tag_list: list[dict[str, str]] | None) -> dict[str, str]:
    """Convert AWS tag format to flat dict."""
    if not tag_list:
        return {}
    return {tag["Key"]: tag["Value"] for tag in tag_list}


def _name_from_tags(tags: dict[str, str], fallback: str) -> str:
    """Extract Name tag or fall back to the given ID."""
    return tags.get("Name", fallback)


class VPCResources:
    """Handles VPC discovery."""

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_vpcs(self, region: str | None = None) -> list[Resource]:
        """List all VPCs in the given region.

        Args:
            region: AWS region.

        Returns:
            List of Resource objects representing VPCs.
        """
        ec2 = self._auth.client("ec2", region=region)
        response = await asyncio.to_thread(ec2.describe_vpcs)

        resources: list[Resource] = []
        for vpc in response.get("Vpcs", []):
            tags = _parse_tags(vpc.get("Tags"))
            resources.append(
                Resource(
                    id=vpc["VpcId"],
                    name=_name_from_tags(tags, vpc["VpcId"]),
                    resource_type=ResourceType.NETWORK,
                    provider="aws",
                    region=region or "",
                    state=(
                        ResourceState.RUNNING
                        if vpc.get("State") == "available"
                        else ResourceState.PENDING
                    ),
                    tags=tags,
                    metadata={
                        "cidr_block": vpc.get("CidrBlock", ""),
                        "is_default": str(vpc.get("IsDefault", False)),
                        "resource_subtype": "vpc",
                    },
                )
            )

        logger.debug("Found %d VPCs in %s", len(resources), region or "default region")
        return resources


class SubnetResources:
    """Handles Subnet discovery."""

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_subnets(self, region: str | None = None) -> list[Resource]:
        """List all subnets in the given region.

        Args:
            region: AWS region.

        Returns:
            List of Resource objects representing subnets.
        """
        ec2 = self._auth.client("ec2", region=region)
        response = await asyncio.to_thread(ec2.describe_subnets)

        resources: list[Resource] = []
        for subnet in response.get("Subnets", []):
            tags = _parse_tags(subnet.get("Tags"))
            resources.append(
                Resource(
                    id=subnet["SubnetId"],
                    name=_name_from_tags(tags, subnet["SubnetId"]),
                    resource_type=ResourceType.NETWORK,
                    provider="aws",
                    region=subnet.get("AvailabilityZone", region or ""),
                    state=(
                        ResourceState.RUNNING
                        if subnet.get("State") == "available"
                        else ResourceState.PENDING
                    ),
                    tags=tags,
                    metadata={
                        "vpc_id": subnet.get("VpcId", ""),
                        "cidr_block": subnet.get("CidrBlock", ""),
                        "available_ips": str(subnet.get("AvailableIpAddressCount", "")),
                        "resource_subtype": "subnet",
                    },
                )
            )

        logger.debug("Found %d subnets in %s", len(resources), region or "default region")
        return resources


class SecurityGroupResources:
    """Handles Security Group discovery."""

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_security_groups(self, region: str | None = None) -> list[Resource]:
        """List all security groups in the given region.

        Args:
            region: AWS region.

        Returns:
            List of Resource objects representing security groups.
        """
        ec2 = self._auth.client("ec2", region=region)
        response = await asyncio.to_thread(ec2.describe_security_groups)

        resources: list[Resource] = []
        for sg in response.get("SecurityGroups", []):
            tags = _parse_tags(sg.get("Tags"))
            ingress_count = len(sg.get("IpPermissions", []))
            egress_count = len(sg.get("IpPermissionsEgress", []))

            resources.append(
                Resource(
                    id=sg["GroupId"],
                    name=sg.get("GroupName", sg["GroupId"]),
                    resource_type=ResourceType.NETWORK,
                    provider="aws",
                    region=region or "",
                    state=ResourceState.RUNNING,
                    tags=tags,
                    metadata={
                        "vpc_id": sg.get("VpcId", ""),
                        "description": sg.get("Description", ""),
                        "ingress_rules": str(ingress_count),
                        "egress_rules": str(egress_count),
                        "resource_subtype": "security_group",
                    },
                )
            )

        logger.debug("Found %d security groups in %s", len(resources), region or "default region")
        return resources
