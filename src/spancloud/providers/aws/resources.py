"""AWS resource discovery and mapping to the unified Resource model."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.exceptions import ResourceNotFoundError
from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.aws.auth import AWSAuth

logger = get_logger(__name__)

# Map AWS EC2 instance states to Spancloud ResourceState.
_EC2_STATE_MAP: dict[str, ResourceState] = {
    "pending": ResourceState.PENDING,
    "running": ResourceState.RUNNING,
    "shutting-down": ResourceState.PENDING,
    "terminated": ResourceState.TERMINATED,
    "stopping": ResourceState.PENDING,
    "stopped": ResourceState.STOPPED,
}


def _parse_tags(tag_list: list[dict[str, str]] | None) -> dict[str, str]:
    """Convert AWS tag format [{'Key': k, 'Value': v}] to a flat dict."""
    if not tag_list:
        return {}
    return {tag["Key"]: tag["Value"] for tag in tag_list}


def _instance_name(tags: dict[str, str], instance_id: str) -> str:
    """Extract the Name tag or fall back to instance ID."""
    return tags.get("Name", instance_id)


class EC2Resources:
    """Handles EC2 instance discovery."""

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_instances(self, region: str | None = None) -> list[Resource]:
        """List all EC2 instances in the given region.

        Args:
            region: AWS region. Uses the default if not specified.

        Returns:
            List of Resource objects representing EC2 instances.
        """
        ec2 = self._auth.client("ec2", region=region)
        paginator = ec2.get_paginator("describe_instances")
        resources: list[Resource] = []

        pages = await asyncio.to_thread(
            lambda: list(paginator.paginate())
        )

        for page in pages:
            for reservation in page.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    resources.append(self._map_instance(instance, region or ""))

        logger.debug("Found %d EC2 instances in %s", len(resources), region or "default region")
        return resources

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def get_instance(self, instance_id: str, region: str | None = None) -> Resource:
        """Fetch a single EC2 instance by ID.

        Args:
            instance_id: The EC2 instance ID (e.g., i-0abc123).
            region: AWS region.

        Returns:
            A Resource representing the instance.

        Raises:
            ResourceNotFoundError: If the instance doesn't exist.
        """
        ec2 = self._auth.client("ec2", region=region)
        try:
            response = await asyncio.to_thread(
                ec2.describe_instances, InstanceIds=[instance_id]
            )
        except Exception as exc:
            if "InvalidInstanceID.NotFound" in str(exc):
                raise ResourceNotFoundError("aws", "compute", instance_id) from exc
            raise

        reservations = response.get("Reservations", [])
        if not reservations or not reservations[0].get("Instances"):
            raise ResourceNotFoundError("aws", "compute", instance_id)

        return self._map_instance(reservations[0]["Instances"][0], region or "")

    def _map_instance(self, instance: dict[str, Any], region: str) -> Resource:
        """Map an AWS EC2 instance dict to a unified Resource."""
        tags = _parse_tags(instance.get("Tags"))
        state_name = instance.get("State", {}).get("Name", "unknown")
        launch_time = instance.get("LaunchTime")

        return Resource(
            id=instance["InstanceId"],
            name=_instance_name(tags, instance["InstanceId"]),
            resource_type=ResourceType.COMPUTE,
            provider="aws",
            region=region or instance.get("Placement", {}).get("AvailabilityZone", ""),
            state=_EC2_STATE_MAP.get(state_name, ResourceState.UNKNOWN),
            created_at=launch_time,
            tags=tags,
            metadata={
                "instance_type": instance.get("InstanceType", ""),
                "private_ip": instance.get("PrivateIpAddress", ""),
                "public_ip": instance.get("PublicIpAddress", ""),
                "vpc_id": instance.get("VpcId", ""),
                "subnet_id": instance.get("SubnetId", ""),
            },
        )


class S3Resources:
    """Handles S3 bucket discovery."""

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_buckets(self) -> list[Resource]:
        """List all S3 buckets in the account.

        Returns:
            List of Resource objects representing S3 buckets.
        """
        s3 = self._auth.client("s3")
        response = await asyncio.to_thread(s3.list_buckets)

        resources: list[Resource] = []
        for bucket in response.get("Buckets", []):
            resources.append(
                Resource(
                    id=bucket["Name"],
                    name=bucket["Name"],
                    resource_type=ResourceType.STORAGE,
                    provider="aws",
                    region="global",
                    state=ResourceState.RUNNING,
                    created_at=bucket.get("CreationDate"),
                )
            )

        logger.debug("Found %d S3 buckets", len(resources))
        return resources
