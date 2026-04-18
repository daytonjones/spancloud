"""AWS RDS instance and cluster resource discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.aws.auth import AWSAuth

logger = get_logger(__name__)

_RDS_STATE_MAP: dict[str, ResourceState] = {
    "available": ResourceState.RUNNING,
    "creating": ResourceState.PENDING,
    "deleting": ResourceState.PENDING,
    "failed": ResourceState.ERROR,
    "modifying": ResourceState.PENDING,
    "rebooting": ResourceState.PENDING,
    "starting": ResourceState.PENDING,
    "stopped": ResourceState.STOPPED,
    "stopping": ResourceState.PENDING,
    "storage-optimization": ResourceState.RUNNING,
    "backing-up": ResourceState.RUNNING,
}


def _parse_tags(tag_list: list[dict[str, str]] | None) -> dict[str, str]:
    """Convert AWS tag format to flat dict."""
    if not tag_list:
        return {}
    return {tag["Key"]: tag["Value"] for tag in tag_list}


class RDSResources:
    """Handles RDS instance and Aurora cluster discovery."""

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_instances(self, region: str | None = None) -> list[Resource]:
        """List all RDS instances in the given region.

        Args:
            region: AWS region.

        Returns:
            List of Resource objects representing RDS instances.
        """
        rds = self._auth.client("rds", region=region)
        paginator = rds.get_paginator("describe_db_instances")

        pages = await asyncio.to_thread(lambda: list(paginator.paginate()))

        resources: list[Resource] = []
        for page in pages:
            for db in page.get("DBInstances", []):
                resources.append(self._map_instance(db, region or ""))

        logger.debug("Found %d RDS instances in %s", len(resources), region or "default region")
        return resources

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_clusters(self, region: str | None = None) -> list[Resource]:
        """List all Aurora DB clusters in the given region.

        Args:
            region: AWS region.

        Returns:
            List of Resource objects representing Aurora clusters.
        """
        rds = self._auth.client("rds", region=region)
        paginator = rds.get_paginator("describe_db_clusters")

        pages = await asyncio.to_thread(lambda: list(paginator.paginate()))

        resources: list[Resource] = []
        for page in pages:
            for cluster in page.get("DBClusters", []):
                resources.append(self._map_cluster(cluster, region or ""))

        logger.debug("Found %d Aurora clusters in %s", len(resources), region or "default region")
        return resources

    def _map_instance(self, db: dict[str, Any], region: str) -> Resource:
        """Map an RDS instance to a unified Resource."""
        tags = _parse_tags(db.get("TagList"))
        status = db.get("DBInstanceStatus", "unknown")

        return Resource(
            id=db["DBInstanceIdentifier"],
            name=db["DBInstanceIdentifier"],
            resource_type=ResourceType.DATABASE,
            provider="aws",
            region=db.get("AvailabilityZone", region),
            state=_RDS_STATE_MAP.get(status, ResourceState.UNKNOWN),
            created_at=db.get("InstanceCreateTime"),
            tags=tags,
            metadata={
                "engine": db.get("Engine", ""),
                "engine_version": db.get("EngineVersion", ""),
                "instance_class": db.get("DBInstanceClass", ""),
                "storage_gb": str(db.get("AllocatedStorage", "")),
                "multi_az": str(db.get("MultiAZ", False)),
                "endpoint": db.get("Endpoint", {}).get("Address", ""),
                "port": str(db.get("Endpoint", {}).get("Port", "")),
                "cluster_id": db.get("DBClusterIdentifier", ""),
                "resource_subtype": "rds_instance",
            },
        )

    def _map_cluster(self, cluster: dict[str, Any], region: str) -> Resource:
        """Map an Aurora cluster to a unified Resource."""
        tags = _parse_tags(cluster.get("TagList"))
        status = cluster.get("Status", "unknown")
        members = cluster.get("DBClusterMembers", [])

        return Resource(
            id=cluster["DBClusterIdentifier"],
            name=cluster["DBClusterIdentifier"],
            resource_type=ResourceType.DATABASE,
            provider="aws",
            region=region,
            state=_RDS_STATE_MAP.get(status, ResourceState.UNKNOWN),
            created_at=cluster.get("ClusterCreateTime"),
            tags=tags,
            metadata={
                "engine": cluster.get("Engine", ""),
                "engine_version": cluster.get("EngineVersion", ""),
                "member_count": str(len(members)),
                "endpoint": cluster.get("Endpoint", ""),
                "reader_endpoint": cluster.get("ReaderEndpoint", ""),
                "port": str(cluster.get("Port", "")),
                "multi_az": str(cluster.get("MultiAZ", False)),
                "resource_subtype": "aurora_cluster",
            },
        )
