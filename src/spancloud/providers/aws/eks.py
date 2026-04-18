"""AWS EKS cluster and node group resource discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.aws.auth import AWSAuth

logger = get_logger(__name__)

_EKS_CLUSTER_STATE_MAP: dict[str, ResourceState] = {
    "CREATING": ResourceState.PENDING,
    "ACTIVE": ResourceState.RUNNING,
    "DELETING": ResourceState.PENDING,
    "FAILED": ResourceState.ERROR,
    "UPDATING": ResourceState.PENDING,
    "PENDING": ResourceState.PENDING,
}

_EKS_NODEGROUP_STATE_MAP: dict[str, ResourceState] = {
    "CREATING": ResourceState.PENDING,
    "ACTIVE": ResourceState.RUNNING,
    "UPDATING": ResourceState.PENDING,
    "DELETING": ResourceState.PENDING,
    "CREATE_FAILED": ResourceState.ERROR,
    "DELETE_FAILED": ResourceState.ERROR,
    "DEGRADED": ResourceState.ERROR,
}


class EKSResources:
    """Handles EKS cluster and node group discovery."""

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_clusters(self, region: str | None = None) -> list[Resource]:
        """List all EKS clusters in the given region, with details.

        Args:
            region: AWS region.

        Returns:
            List of Resource objects representing EKS clusters.
        """
        client = self._auth.client("eks", region=region)

        # First, list cluster names
        cluster_names: list[str] = []
        paginator = client.get_paginator("list_clusters")
        pages = await asyncio.to_thread(lambda: list(paginator.paginate()))
        for page in pages:
            cluster_names.extend(page.get("clusters", []))

        if not cluster_names:
            return []

        # Then describe each cluster for full details
        resources: list[Resource] = []
        for name in cluster_names:
            try:
                response = await asyncio.to_thread(
                    client.describe_cluster, name=name
                )
                cluster = response.get("cluster", {})
                resources.append(self._map_cluster(cluster, region or ""))
            except Exception as exc:
                logger.warning("Failed to describe EKS cluster %s: %s", name, exc)

        logger.debug("Found %d EKS clusters in %s", len(resources), region or "default region")
        return resources

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_nodegroups(self, region: str | None = None) -> list[Resource]:
        """List all EKS node groups across all clusters in the given region.

        Args:
            region: AWS region.

        Returns:
            List of Resource objects representing EKS node groups.
        """
        client = self._auth.client("eks", region=region)

        # Get all cluster names first
        cluster_names: list[str] = []
        paginator = client.get_paginator("list_clusters")
        pages = await asyncio.to_thread(lambda: list(paginator.paginate()))
        for page in pages:
            cluster_names.extend(page.get("clusters", []))

        resources: list[Resource] = []
        for cluster_name in cluster_names:
            try:
                ng_paginator = client.get_paginator("list_nodegroups")
                ng_pages = await asyncio.to_thread(
                    lambda cn=cluster_name, p=ng_paginator: list(p.paginate(clusterName=cn))
                )
                for ng_page in ng_pages:
                    for ng_name in ng_page.get("nodegroups", []):
                        try:
                            response = await asyncio.to_thread(
                                client.describe_nodegroup,
                                clusterName=cluster_name,
                                nodegroupName=ng_name,
                            )
                            ng = response.get("nodegroup", {})
                            resources.append(
                                self._map_nodegroup(ng, cluster_name, region or "")
                            )
                        except Exception as exc:
                            logger.warning(
                                "Failed to describe nodegroup %s/%s: %s",
                                cluster_name,
                                ng_name,
                                exc,
                            )
            except Exception as exc:
                logger.warning(
                    "Failed to list nodegroups for cluster %s: %s", cluster_name, exc
                )

        logger.debug("Found %d EKS node groups in %s", len(resources), region or "default region")
        return resources

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_fargate_profiles(self, region: str | None = None) -> list[Resource]:
        """List all EKS Fargate profiles across all clusters.

        Args:
            region: AWS region.

        Returns:
            List of Resource objects representing Fargate profiles.
        """
        client = self._auth.client("eks", region=region)

        cluster_names: list[str] = []
        paginator = client.get_paginator("list_clusters")
        pages = await asyncio.to_thread(lambda: list(paginator.paginate()))
        for page in pages:
            cluster_names.extend(page.get("clusters", []))

        resources: list[Resource] = []
        for cluster_name in cluster_names:
            try:
                fp_paginator = client.get_paginator("list_fargate_profiles")
                fp_pages = await asyncio.to_thread(
                    lambda cn=cluster_name, p=fp_paginator: list(p.paginate(clusterName=cn))
                )
                for fp_page in fp_pages:
                    for fp_name in fp_page.get("fargateProfileNames", []):
                        try:
                            response = await asyncio.to_thread(
                                client.describe_fargate_profile,
                                clusterName=cluster_name,
                                fargateProfileName=fp_name,
                            )
                            fp = response.get("fargateProfile", {})
                            resources.append(
                                self._map_fargate_profile(fp, cluster_name, region or "")
                            )
                        except Exception as exc:
                            logger.warning(
                                "Failed to describe Fargate profile %s/%s: %s",
                                cluster_name,
                                fp_name,
                                exc,
                            )
            except Exception as exc:
                logger.warning(
                    "Failed to list Fargate profiles for cluster %s: %s",
                    cluster_name,
                    exc,
                )

        logger.debug(
            "Found %d EKS Fargate profiles in %s", len(resources), region or "default region"
        )
        return resources

    def _map_cluster(self, cluster: dict[str, Any], region: str) -> Resource:
        """Map an EKS cluster to a unified Resource."""
        status = cluster.get("status", "UNKNOWN")
        tags = cluster.get("tags", {})

        return Resource(
            id=cluster.get("name", ""),
            name=cluster.get("name", ""),
            resource_type=ResourceType.CONTAINER,
            provider="aws",
            region=region,
            state=_EKS_CLUSTER_STATE_MAP.get(status, ResourceState.UNKNOWN),
            created_at=cluster.get("createdAt"),
            tags=tags,
            metadata={
                "kubernetes_version": cluster.get("version", ""),
                "platform_version": cluster.get("platformVersion", ""),
                "endpoint": cluster.get("endpoint", ""),
                "role_arn": cluster.get("roleArn", ""),
                "vpc_id": cluster.get("resourcesVpcConfig", {}).get("vpcId", ""),
                "resource_subtype": "eks_cluster",
            },
        )

    def _map_nodegroup(
        self, ng: dict[str, Any], cluster_name: str, region: str
    ) -> Resource:
        """Map an EKS node group to a unified Resource."""
        status = ng.get("status", "UNKNOWN")
        tags = ng.get("tags", {})
        scaling = ng.get("scalingConfig", {})

        return Resource(
            id=f"{cluster_name}/{ng.get('nodegroupName', '')}",
            name=ng.get("nodegroupName", ""),
            resource_type=ResourceType.CONTAINER,
            provider="aws",
            region=region,
            state=_EKS_NODEGROUP_STATE_MAP.get(status, ResourceState.UNKNOWN),
            created_at=ng.get("createdAt"),
            tags=tags,
            metadata={
                "cluster": cluster_name,
                "instance_types": ", ".join(ng.get("instanceTypes", [])),
                "ami_type": ng.get("amiType", ""),
                "capacity_type": ng.get("capacityType", ""),
                "desired_size": str(scaling.get("desiredSize", "")),
                "min_size": str(scaling.get("minSize", "")),
                "max_size": str(scaling.get("maxSize", "")),
                "resource_subtype": "eks_nodegroup",
            },
        )

    def _map_fargate_profile(
        self, fp: dict[str, Any], cluster_name: str, region: str
    ) -> Resource:
        """Map an EKS Fargate profile to a unified Resource."""
        status = fp.get("status", "UNKNOWN")
        tags = fp.get("tags", {})
        selectors = fp.get("selectors", [])

        namespaces = [s.get("namespace", "") for s in selectors if s.get("namespace")]

        return Resource(
            id=f"{cluster_name}/{fp.get('fargateProfileName', '')}",
            name=fp.get("fargateProfileName", ""),
            resource_type=ResourceType.CONTAINER,
            provider="aws",
            region=region,
            state=_EKS_CLUSTER_STATE_MAP.get(status, ResourceState.UNKNOWN),
            created_at=fp.get("createdAt"),
            tags=tags,
            metadata={
                "cluster": cluster_name,
                "pod_execution_role": fp.get("podExecutionRoleArn", ""),
                "namespaces": ", ".join(namespaces),
                "selector_count": str(len(selectors)),
                "resource_subtype": "eks_fargate_profile",
            },
        )
