"""AWS resource relationship mapping.

Maps connections between:
- EC2 → VPC, Subnet, Security Groups, EBS volumes
- RDS → VPC, Subnet Group, Security Groups
- ELB → VPC, Target Groups, instances
- EKS → VPC, Subnets, Node Groups
- Lambda → VPC (if configured)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from spancloud.analysis.models import RelationshipMap, RelationshipType, ResourceRelationship
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff
from spancloud.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from spancloud.providers.aws.auth import AWSAuth

logger = get_logger(__name__)

_EC2_LIMITER = RateLimiter(calls_per_second=10.0, max_concurrency=10)


class AWSRelationshipMapper:
    """Maps relationships between AWS resources.

    Fetches resources in bulk then cross-references locally
    to minimize API calls.
    """

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def map_relationships(
        self, region: str | None = None
    ) -> RelationshipMap:
        """Build a complete resource relationship map.

        Args:
            region: AWS region to scan.

        Returns:
            RelationshipMap with all discovered relationships.
        """
        tasks = [
            self._map_ec2_relationships(region),
            self._map_rds_relationships(region),
            self._map_elb_relationships(region),
            self._map_eks_relationships(region),
            self._map_lambda_relationships(region),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        relationships: list[ResourceRelationship] = []
        for result in results:
            if isinstance(result, list):
                relationships.extend(result)
            elif isinstance(result, Exception):
                logger.warning("Relationship mapping failed: %s", result)

        return RelationshipMap(provider="aws", relationships=relationships)

    async def _map_ec2_relationships(
        self, region: str | None = None
    ) -> list[ResourceRelationship]:
        """Map EC2 instance relationships: VPC, subnet, SGs, EBS."""
        ec2 = self._auth.client("ec2", region=region)

        async with _EC2_LIMITER:
            paginator = ec2.get_paginator("describe_instances")
            pages = await asyncio.to_thread(lambda: list(paginator.paginate()))

        rels: list[ResourceRelationship] = []
        for page in pages:
            for res in page.get("Reservations", []):
                for inst in res.get("Instances", []):
                    inst_id = inst["InstanceId"]
                    tags = {
                        t["Key"]: t["Value"] for t in inst.get("Tags", [])
                    }
                    inst_name = tags.get("Name", inst_id)

                    # VPC
                    vpc_id = inst.get("VpcId", "")
                    if vpc_id:
                        rels.append(ResourceRelationship(
                            source_id=inst_id,
                            source_type="ec2_instance",
                            source_name=inst_name,
                            target_id=vpc_id,
                            target_type="vpc",
                            relationship=RelationshipType.IN_VPC,
                            provider="aws",
                            region=region or "",
                        ))

                    # Subnet
                    subnet_id = inst.get("SubnetId", "")
                    if subnet_id:
                        rels.append(ResourceRelationship(
                            source_id=inst_id,
                            source_type="ec2_instance",
                            source_name=inst_name,
                            target_id=subnet_id,
                            target_type="subnet",
                            relationship=RelationshipType.IN_SUBNET,
                            provider="aws",
                            region=region or "",
                        ))

                    # Security Groups
                    for sg in inst.get("SecurityGroups", []):
                        rels.append(ResourceRelationship(
                            source_id=inst_id,
                            source_type="ec2_instance",
                            source_name=inst_name,
                            target_id=sg["GroupId"],
                            target_type="security_group",
                            target_name=sg.get("GroupName", ""),
                            relationship=RelationshipType.SECURED_BY,
                            provider="aws",
                            region=region or "",
                        ))

                    # EBS volumes
                    for bdm in inst.get("BlockDeviceMappings", []):
                        ebs = bdm.get("Ebs", {})
                        vol_id = ebs.get("VolumeId", "")
                        if vol_id:
                            rels.append(ResourceRelationship(
                                source_id=inst_id,
                                source_type="ec2_instance",
                                source_name=inst_name,
                                target_id=vol_id,
                                target_type="ebs_volume",
                                relationship=RelationshipType.ATTACHED_TO,
                                provider="aws",
                                region=region or "",
                            ))

        return rels

    async def _map_rds_relationships(
        self, region: str | None = None
    ) -> list[ResourceRelationship]:
        """Map RDS instance relationships: VPC, security groups."""
        rds = self._auth.client("rds", region=region)

        async with _EC2_LIMITER:
            paginator = rds.get_paginator("describe_db_instances")
            pages = await asyncio.to_thread(lambda: list(paginator.paginate()))

        rels: list[ResourceRelationship] = []
        for page in pages:
            for db in page.get("DBInstances", []):
                db_id = db["DBInstanceIdentifier"]

                # VPC
                vpc_sgs = db.get("VpcSecurityGroups", [])
                subnet_group = db.get("DBSubnetGroup", {})
                vpc_id = subnet_group.get("VpcId", "")

                if vpc_id:
                    rels.append(ResourceRelationship(
                        source_id=db_id,
                        source_type="rds_instance",
                        target_id=vpc_id,
                        target_type="vpc",
                        relationship=RelationshipType.IN_VPC,
                        provider="aws",
                        region=region or "",
                    ))

                # Security groups
                for sg in vpc_sgs:
                    sg_id = sg.get("VpcSecurityGroupId", "")
                    if sg_id:
                        rels.append(ResourceRelationship(
                            source_id=db_id,
                            source_type="rds_instance",
                            target_id=sg_id,
                            target_type="security_group",
                            relationship=RelationshipType.SECURED_BY,
                            provider="aws",
                            region=region or "",
                        ))

                # Subnets
                for subnet in subnet_group.get("Subnets", []):
                    subnet_id = subnet.get("SubnetIdentifier", "")
                    if subnet_id:
                        rels.append(ResourceRelationship(
                            source_id=db_id,
                            source_type="rds_instance",
                            target_id=subnet_id,
                            target_type="subnet",
                            relationship=RelationshipType.IN_SUBNET,
                            provider="aws",
                            region=region or "",
                        ))

        return rels

    async def _map_elb_relationships(
        self, region: str | None = None
    ) -> list[ResourceRelationship]:
        """Map ELB relationships: VPC, target groups."""
        elbv2 = self._auth.client("elbv2", region=region)

        async with _EC2_LIMITER:
            paginator = elbv2.get_paginator("describe_load_balancers")
            pages = await asyncio.to_thread(lambda: list(paginator.paginate()))

        rels: list[ResourceRelationship] = []
        for page in pages:
            for lb in page.get("LoadBalancers", []):
                lb_name = lb.get("LoadBalancerName", "")
                lb_arn = lb["LoadBalancerArn"]

                # VPC
                vpc_id = lb.get("VpcId", "")
                if vpc_id:
                    rels.append(ResourceRelationship(
                        source_id=lb_name,
                        source_type="load_balancer",
                        target_id=vpc_id,
                        target_type="vpc",
                        relationship=RelationshipType.IN_VPC,
                        provider="aws",
                        region=region or "",
                    ))

                # Target groups and their targets
                try:
                    async with _EC2_LIMITER:
                        tg_resp = await asyncio.to_thread(
                            elbv2.describe_target_groups,
                            LoadBalancerArn=lb_arn,
                        )

                    for tg in tg_resp.get("TargetGroups", []):
                        tg_arn = tg["TargetGroupArn"]
                        tg_name = tg.get("TargetGroupName", "")

                        rels.append(ResourceRelationship(
                            source_id=lb_name,
                            source_type="load_balancer",
                            target_id=tg_name,
                            target_type="target_group",
                            relationship=RelationshipType.ROUTES_TO,
                            provider="aws",
                            region=region or "",
                        ))

                        # Get targets (instances) in this group
                        async with _EC2_LIMITER:
                            health = await asyncio.to_thread(
                                elbv2.describe_target_health,
                                TargetGroupArn=tg_arn,
                            )
                        for desc in health.get("TargetHealthDescriptions", []):
                            target_id = desc.get("Target", {}).get("Id", "")
                            if target_id:
                                rels.append(ResourceRelationship(
                                    source_id=lb_name,
                                    source_type="load_balancer",
                                    target_id=target_id,
                                    target_type="ec2_instance",
                                    relationship=RelationshipType.TARGETS,
                                    provider="aws",
                                    region=region or "",
                                ))
                except Exception as exc:
                    logger.debug("Could not map LB targets for %s: %s", lb_name, exc)

        return rels

    async def _map_eks_relationships(
        self, region: str | None = None
    ) -> list[ResourceRelationship]:
        """Map EKS cluster relationships: VPC, subnets, node groups."""
        eks = self._auth.client("eks", region=region)

        async with _EC2_LIMITER:
            paginator = eks.get_paginator("list_clusters")
            pages = await asyncio.to_thread(lambda: list(paginator.paginate()))

        cluster_names: list[str] = []
        for page in pages:
            cluster_names.extend(page.get("clusters", []))

        rels: list[ResourceRelationship] = []
        for name in cluster_names:
            try:
                async with _EC2_LIMITER:
                    resp = await asyncio.to_thread(eks.describe_cluster, name=name)
                cluster = resp.get("cluster", {})

                vpc_config = cluster.get("resourcesVpcConfig", {})
                vpc_id = vpc_config.get("vpcId", "")
                subnets = vpc_config.get("subnetIds", [])

                if vpc_id:
                    rels.append(ResourceRelationship(
                        source_id=name,
                        source_type="eks_cluster",
                        target_id=vpc_id,
                        target_type="vpc",
                        relationship=RelationshipType.IN_VPC,
                        provider="aws",
                        region=region or "",
                    ))

                for subnet_id in subnets:
                    rels.append(ResourceRelationship(
                        source_id=name,
                        source_type="eks_cluster",
                        target_id=subnet_id,
                        target_type="subnet",
                        relationship=RelationshipType.IN_SUBNET,
                        provider="aws",
                        region=region or "",
                    ))

                for sg_id in vpc_config.get("securityGroupIds", []):
                    rels.append(ResourceRelationship(
                        source_id=name,
                        source_type="eks_cluster",
                        target_id=sg_id,
                        target_type="security_group",
                        relationship=RelationshipType.SECURED_BY,
                        provider="aws",
                        region=region or "",
                    ))

            except Exception as exc:
                logger.debug("Could not map EKS cluster %s: %s", name, exc)

        return rels

    async def _map_lambda_relationships(
        self, region: str | None = None
    ) -> list[ResourceRelationship]:
        """Map Lambda function relationships: VPC config."""
        client = self._auth.client("lambda", region=region)

        async with _EC2_LIMITER:
            paginator = client.get_paginator("list_functions")
            pages = await asyncio.to_thread(lambda: list(paginator.paginate()))

        rels: list[ResourceRelationship] = []
        for page in pages:
            for fn in page.get("Functions", []):
                fn_name = fn["FunctionName"]
                vpc_config = fn.get("VpcConfig", {})
                vpc_id = vpc_config.get("VpcId", "")

                if vpc_id:
                    rels.append(ResourceRelationship(
                        source_id=fn_name,
                        source_type="lambda_function",
                        target_id=vpc_id,
                        target_type="vpc",
                        relationship=RelationshipType.IN_VPC,
                        provider="aws",
                        region=region or "",
                    ))

                    for subnet_id in vpc_config.get("SubnetIds", []):
                        rels.append(ResourceRelationship(
                            source_id=fn_name,
                            source_type="lambda_function",
                            target_id=subnet_id,
                            target_type="subnet",
                            relationship=RelationshipType.IN_SUBNET,
                            provider="aws",
                            region=region or "",
                        ))

                    for sg_id in vpc_config.get("SecurityGroupIds", []):
                        rels.append(ResourceRelationship(
                            source_id=fn_name,
                            source_type="lambda_function",
                            target_id=sg_id,
                            target_type="security_group",
                            relationship=RelationshipType.SECURED_BY,
                            provider="aws",
                            region=region or "",
                        ))

        return rels
