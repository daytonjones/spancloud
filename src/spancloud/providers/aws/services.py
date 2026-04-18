"""AWS service registry — defines how to discover resources from each AWS service.

Instead of a separate module per service, each service is described by a
ServiceDef that tells the scanner which boto3 API to call, how to paginate,
and how to map the results to the unified Resource model.

This makes it trivial to add new services — just add a dict entry.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff
from skyforge.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from skyforge.providers.aws.auth import AWSAuth

logger = get_logger(__name__)

_AWS_LIMITER = RateLimiter(calls_per_second=8.0, max_concurrency=10)


class ServiceDef:
    """Definition for discovering resources from an AWS service."""

    def __init__(
        self,
        *,
        name: str,
        label: str,
        icon: str,
        boto3_service: str,
        resource_type: ResourceType,
        subtype: str,
        list_method: str,
        list_key: str,
        paginator: str | None = None,
        id_field: str,
        name_field: str = "",
        region_field: str = "",
        state_field: str = "",
        state_map: dict[str, ResourceState] | None = None,
        metadata_fields: dict[str, str] | None = None,
        tags_field: str = "",
        tags_format: str = "aws",  # "aws" = [{Key:k,Value:v}], "dict" = {k:v}
        is_global: bool = False,
    ) -> None:
        self.name = name
        self.label = label
        self.icon = icon
        self.boto3_service = boto3_service
        self.resource_type = resource_type
        self.subtype = subtype
        self.list_method = list_method
        self.list_key = list_key
        self.paginator = paginator or list_method
        self.id_field = id_field
        self.name_field = name_field or id_field
        self.region_field = region_field
        self.state_field = state_field
        self.state_map = state_map or {}
        self.metadata_fields = metadata_fields or {}
        self.tags_field = tags_field
        self.tags_format = tags_format
        self.is_global = is_global


# ---------------------------------------------------------------------------
# AWS Service Definitions
# ---------------------------------------------------------------------------

AWS_SERVICES: dict[str, ServiceDef] = {}


def _reg(**kwargs: Any) -> None:
    """Register a service definition."""
    svc = ServiceDef(**kwargs)
    AWS_SERVICES[svc.name] = svc


# --- Compute ---
_reg(
    name="ebs_volumes",
    label="EBS Volumes",
    icon="\U0001f4bf",
    boto3_service="ec2",
    resource_type=ResourceType.COMPUTE,
    subtype="ebs_volume",
    list_method="describe_volumes",
    list_key="Volumes",
    id_field="VolumeId",
    name_field="VolumeId",
    state_field="State",
    state_map={
        "available": ResourceState.STOPPED,
        "in-use": ResourceState.RUNNING,
        "creating": ResourceState.PENDING,
        "deleting": ResourceState.PENDING,
        "error": ResourceState.ERROR,
    },
    metadata_fields={
        "size_gb": "Size",
        "volume_type": "VolumeType",
        "iops": "Iops",
        "encrypted": "Encrypted",
        "availability_zone": "AvailabilityZone",
    },
    tags_field="Tags",
)

_reg(
    name="elastic_ips",
    label="Elastic IPs",
    icon="\U0001f310",
    boto3_service="ec2",
    resource_type=ResourceType.NETWORK,
    subtype="elastic_ip",
    list_method="describe_addresses",
    list_key="Addresses",
    id_field="AllocationId",
    name_field="PublicIp",
    state_field="",
    metadata_fields={
        "public_ip": "PublicIp",
        "instance_id": "InstanceId",
        "domain": "Domain",
        "network_interface_id": "NetworkInterfaceId",
    },
    tags_field="Tags",
)

_reg(
    name="auto_scaling_groups",
    label="Auto Scaling Groups",
    icon="\u2194",
    boto3_service="autoscaling",
    resource_type=ResourceType.COMPUTE,
    subtype="auto_scaling_group",
    list_method="describe_auto_scaling_groups",
    list_key="AutoScalingGroups",
    id_field="AutoScalingGroupName",
    name_field="AutoScalingGroupName",
    metadata_fields={
        "min_size": "MinSize",
        "max_size": "MaxSize",
        "desired_capacity": "DesiredCapacity",
        "launch_template": "LaunchTemplate",
        "availability_zones": "AvailabilityZones",
    },
    tags_field="Tags",
)

_reg(
    name="amis",
    label="AMIs (owned)",
    icon="\U0001f4e6",
    boto3_service="ec2",
    resource_type=ResourceType.COMPUTE,
    subtype="ami",
    list_method="describe_images",
    list_key="Images",
    id_field="ImageId",
    name_field="Name",
    state_field="State",
    state_map={
        "available": ResourceState.RUNNING,
        "pending": ResourceState.PENDING,
        "failed": ResourceState.ERROR,
    },
    metadata_fields={
        "architecture": "Architecture",
        "platform": "PlatformDetails",
        "root_device_type": "RootDeviceType",
        "creation_date": "CreationDate",
    },
    tags_field="Tags",
)

# --- Storage ---
_reg(
    name="efs",
    label="EFS File Systems",
    icon="\U0001f4c1",
    boto3_service="efs",
    resource_type=ResourceType.STORAGE,
    subtype="efs_filesystem",
    list_method="describe_file_systems",
    list_key="FileSystems",
    id_field="FileSystemId",
    name_field="Name",
    state_field="LifeCycleState",
    state_map={
        "available": ResourceState.RUNNING,
        "creating": ResourceState.PENDING,
        "deleting": ResourceState.PENDING,
        "error": ResourceState.ERROR,
    },
    metadata_fields={
        "size_bytes": "SizeInBytes",
        "performance_mode": "PerformanceMode",
        "throughput_mode": "ThroughputMode",
        "encrypted": "Encrypted",
    },
    tags_field="Tags",
    tags_format="dict",
)

# --- Database ---
_reg(
    name="dynamodb",
    label="DynamoDB Tables",
    icon="\U0001f4ca",
    boto3_service="dynamodb",
    resource_type=ResourceType.DATABASE,
    subtype="dynamodb_table",
    list_method="list_tables",
    list_key="TableNames",
    id_field="",  # Special: list returns names only
    name_field="",
    is_global=False,
)

_reg(
    name="elasticache",
    label="ElastiCache Clusters",
    icon="\u26a1",
    boto3_service="elasticache",
    resource_type=ResourceType.DATABASE,
    subtype="elasticache_cluster",
    list_method="describe_cache_clusters",
    list_key="CacheClusters",
    id_field="CacheClusterId",
    name_field="CacheClusterId",
    state_field="CacheClusterStatus",
    state_map={
        "available": ResourceState.RUNNING,
        "creating": ResourceState.PENDING,
        "deleting": ResourceState.PENDING,
        "modifying": ResourceState.PENDING,
        "snapshotting": ResourceState.RUNNING,
    },
    metadata_fields={
        "engine": "Engine",
        "engine_version": "EngineVersion",
        "cache_node_type": "CacheNodeType",
        "num_cache_nodes": "NumCacheNodes",
        "preferred_az": "PreferredAvailabilityZone",
    },
)

# --- Network ---
_reg(
    name="nat_gateways",
    label="NAT Gateways",
    icon="\U0001f6aa",
    boto3_service="ec2",
    resource_type=ResourceType.NETWORK,
    subtype="nat_gateway",
    list_method="describe_nat_gateways",
    list_key="NatGateways",
    id_field="NatGatewayId",
    name_field="NatGatewayId",
    state_field="State",
    state_map={
        "available": ResourceState.RUNNING,
        "pending": ResourceState.PENDING,
        "deleting": ResourceState.PENDING,
        "deleted": ResourceState.TERMINATED,
        "failed": ResourceState.ERROR,
    },
    metadata_fields={
        "vpc_id": "VpcId",
        "subnet_id": "SubnetId",
        "connectivity_type": "ConnectivityType",
    },
    tags_field="Tags",
)

_reg(
    name="cloudfront",
    label="CloudFront Distributions",
    icon="\U0001f310",
    boto3_service="cloudfront",
    resource_type=ResourceType.NETWORK,
    subtype="cloudfront_distribution",
    list_method="list_distributions",
    list_key="DistributionList",
    id_field="Id",
    name_field="DomainName",
    state_field="Status",
    state_map={
        "Deployed": ResourceState.RUNNING,
        "InProgress": ResourceState.PENDING,
    },
    metadata_fields={
        "domain_name": "DomainName",
        "enabled": "Enabled",
        "comment": "Comment",
        "price_class": "PriceClass",
    },
    is_global=True,
)

# --- Messaging ---
_reg(
    name="sqs",
    label="SQS Queues",
    icon="\U0001f4e8",
    boto3_service="sqs",
    resource_type=ResourceType.OTHER,
    subtype="sqs_queue",
    list_method="list_queues",
    list_key="QueueUrls",
    id_field="",  # Special: returns URLs
    name_field="",
)

_reg(
    name="sns",
    label="SNS Topics",
    icon="\U0001f514",
    boto3_service="sns",
    resource_type=ResourceType.OTHER,
    subtype="sns_topic",
    list_method="list_topics",
    list_key="Topics",
    id_field="TopicArn",
    name_field="TopicArn",
)

# --- Secrets / Config ---
_reg(
    name="secrets_manager",
    label="Secrets Manager",
    icon="\U0001f512",
    boto3_service="secretsmanager",
    resource_type=ResourceType.OTHER,
    subtype="secret",
    list_method="list_secrets",
    list_key="SecretList",
    id_field="ARN",
    name_field="Name",
    metadata_fields={
        "description": "Description",
        "last_accessed": "LastAccessedDate",
        "last_changed": "LastChangedDate",
        "rotation_enabled": "RotationEnabled",
    },
    tags_field="Tags",
)

_reg(
    name="ssm_parameters",
    label="SSM Parameters",
    icon="\u2699",
    boto3_service="ssm",
    resource_type=ResourceType.OTHER,
    subtype="ssm_parameter",
    list_method="describe_parameters",
    list_key="Parameters",
    id_field="Name",
    name_field="Name",
    metadata_fields={
        "type": "Type",
        "tier": "Tier",
        "version": "Version",
        "last_modified": "LastModifiedDate",
    },
)

# --- Container ---
_reg(
    name="ecr",
    label="ECR Repositories",
    icon="\U0001f4e6",
    boto3_service="ecr",
    resource_type=ResourceType.CONTAINER,
    subtype="ecr_repository",
    list_method="describe_repositories",
    list_key="repositories",
    id_field="repositoryArn",
    name_field="repositoryName",
    metadata_fields={
        "uri": "repositoryUri",
        "image_tag_mutability": "imageTagMutability",
        "scan_on_push": "imageScanningConfiguration",
        "created_at": "createdAt",
    },
)

_reg(
    name="ecs_clusters",
    label="ECS Clusters",
    icon="\U0001f4e6",
    boto3_service="ecs",
    resource_type=ResourceType.CONTAINER,
    subtype="ecs_cluster",
    list_method="list_clusters",
    list_key="clusterArns",
    id_field="",  # Special: returns ARNs
    name_field="",
)

# --- Serverless ---
_reg(
    name="api_gateway",
    label="API Gateway APIs",
    icon="\U0001f517",
    boto3_service="apigatewayv2",
    resource_type=ResourceType.SERVERLESS,
    subtype="api_gateway",
    list_method="get_apis",
    list_key="Items",
    id_field="ApiId",
    name_field="Name",
    metadata_fields={
        "protocol_type": "ProtocolType",
        "api_endpoint": "ApiEndpoint",
        "description": "Description",
    },
    tags_field="Tags",
    tags_format="dict",
)

_reg(
    name="step_functions",
    label="Step Functions",
    icon="\u2699",
    boto3_service="stepfunctions",
    resource_type=ResourceType.SERVERLESS,
    subtype="state_machine",
    list_method="list_state_machines",
    list_key="stateMachines",
    id_field="stateMachineArn",
    name_field="name",
    metadata_fields={
        "type": "type",
        "creation_date": "creationDate",
    },
)


# ---------------------------------------------------------------------------
# Generic scanner
# ---------------------------------------------------------------------------


class AWSServiceScanner:
    """Scans resources from any AWS service using the ServiceDef registry."""

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    async def scan_service(
        self, service_def: ServiceDef, region: str | None = None
    ) -> list[Resource]:
        """Scan a single AWS service for resources.

        Args:
            service_def: The service definition to scan.
            region: AWS region.

        Returns:
            List of Resource objects.
        """
        client = self._auth.client(service_def.boto3_service, region=region)

        try:
            raw_items = await self._fetch_items(client, service_def)
        except Exception as exc:
            logger.debug(
                "Could not scan %s: %s", service_def.name, exc
            )
            return []

        resources: list[Resource] = []
        for item in raw_items:
            resource = self._map_item(item, service_def, region)
            if resource:
                resources.append(resource)

        logger.debug(
            "Scanned %d %s resources", len(resources), service_def.name
        )
        return resources

    async def _fetch_items(
        self, client: Any, svc: ServiceDef
    ) -> list[Any]:
        """Fetch items from the API using pagination."""

        def _call() -> list[Any]:
            try:
                paginator = client.get_paginator(svc.paginator)
                items: list[Any] = []

                # Special handling for describe_images (needs owner filter)
                kwargs: dict[str, Any] = {}
                if svc.name == "amis":
                    kwargs["Owners"] = ["self"]

                for page in paginator.paginate(**kwargs):
                    page_items = page.get(svc.list_key, [])

                    # CloudFront nests items under DistributionList.Items
                    if svc.name == "cloudfront" and isinstance(page_items, dict):
                        page_items = page_items.get("Items", [])

                    if isinstance(page_items, list):
                        items.extend(page_items)
                return items
            except client.exceptions.ClientError:
                raise
            except Exception:
                # Fallback: no paginator, try direct call
                method = getattr(client, svc.list_method)
                resp = method()
                items = resp.get(svc.list_key, [])
                if isinstance(items, dict):
                    items = items.get("Items", [])
                return items if isinstance(items, list) else []

        async with _AWS_LIMITER:
            return await asyncio.to_thread(_call)

    def _map_item(
        self, item: Any, svc: ServiceDef, region: str | None
    ) -> Resource | None:
        """Map a raw API item to a Resource."""
        # Handle special cases where list returns strings (ARNs/URLs/names)
        if isinstance(item, str):
            name = item.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
            return Resource(
                id=item,
                name=name,
                resource_type=svc.resource_type,
                provider="aws",
                region=region or "global" if svc.is_global else region or "",
                state=ResourceState.RUNNING,
                metadata={"resource_subtype": svc.subtype},
            )

        if not isinstance(item, dict):
            return None

        # Extract ID and name
        res_id = str(self._get_nested(item, svc.id_field) or "")
        res_name = str(self._get_nested(item, svc.name_field) or res_id)

        if not res_id and not res_name:
            return None

        # State
        state = ResourceState.RUNNING
        if svc.state_field:
            state_val = str(self._get_nested(item, svc.state_field) or "")
            state = svc.state_map.get(state_val, ResourceState.UNKNOWN)

        # Region
        res_region = region or ""
        if svc.region_field:
            res_region = str(
                self._get_nested(item, svc.region_field) or region or ""
            )
        if svc.is_global:
            res_region = "global"

        # Metadata
        metadata: dict[str, str] = {"resource_subtype": svc.subtype}
        for meta_key, api_key in svc.metadata_fields.items():
            val = self._get_nested(item, api_key)
            if val is not None:
                metadata[meta_key] = str(val)

        # Tags
        tags: dict[str, str] = {}
        if svc.tags_field:
            raw_tags = item.get(svc.tags_field)
            if raw_tags:
                if svc.tags_format == "aws" and isinstance(raw_tags, list):
                    tags = {
                        t.get("Key", ""): t.get("Value", "")
                        for t in raw_tags
                        if isinstance(t, dict)
                    }
                elif isinstance(raw_tags, dict):
                    tags = {str(k): str(v) for k, v in raw_tags.items()}

        # Name from tags if available
        if not res_name or res_name == res_id:
            res_name = tags.get("Name", res_id)

        return Resource(
            id=res_id or res_name,
            name=res_name,
            resource_type=svc.resource_type,
            provider="aws",
            region=res_region,
            state=state,
            tags=tags,
            metadata=metadata,
        )

    def _get_nested(self, item: dict, key: str) -> Any:
        """Get a value from a dict, supporting dotted paths."""
        if not key:
            return None
        parts = key.split(".")
        val = item
        for part in parts:
            if isinstance(val, dict):
                val = val.get(part)
            else:
                return None
        return val

    async def scan_all(
        self,
        service_names: list[str] | None = None,
        region: str | None = None,
    ) -> list[Resource]:
        """Scan multiple services in parallel.

        Args:
            service_names: Services to scan (defaults to all).
            region: AWS region.

        Returns:
            Combined list of resources.
        """
        if service_names:
            services = [
                AWS_SERVICES[n] for n in service_names if n in AWS_SERVICES
            ]
        else:
            services = list(AWS_SERVICES.values())

        tasks = [self.scan_service(svc, region) for svc in services]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_resources: list[Resource] = []
        for result in results:
            if isinstance(result, list):
                all_resources.extend(result)
            elif isinstance(result, Exception):
                logger.debug("Service scan failed: %s", result)

        return all_resources
