"""AWS provider implementation."""

from __future__ import annotations

from skyforge.core.exceptions import ProviderError
from skyforge.core.provider import BaseProvider
from skyforge.core.resource import Resource, ResourceType
from skyforge.providers.aws.auth import AWSAuth
from skyforge.providers.aws.eks import EKSResources
from skyforge.providers.aws.elb import ELBResources
from skyforge.providers.aws.iam import IAMPolicyResources, IAMRoleResources, IAMUserResources
from skyforge.providers.aws.lambda_ import LambdaResources
from skyforge.providers.aws.rds import RDSResources
from skyforge.providers.aws.regions import scan_all_regions
from skyforge.providers.aws.resources import EC2Resources, S3Resources
from skyforge.providers.aws.route53 import Route53Resources
from skyforge.providers.aws.vpc import SecurityGroupResources, SubnetResources, VPCResources
from skyforge.utils.logging import get_logger

logger = get_logger(__name__)


class AWSProvider(BaseProvider):
    """Amazon Web Services provider.

    Uses the native AWS credential chain (environment variables,
    ~/.aws/credentials, IAM roles, SSO, instance metadata).

    Supports multi-region scanning when region="*" is passed.
    """

    # Sentinel value to trigger all-regions scan.
    ALL_REGIONS = "*"

    def __init__(self) -> None:
        self._auth = AWSAuth()
        self._ec2 = EC2Resources(self._auth)
        self._s3 = S3Resources(self._auth)
        self._vpc = VPCResources(self._auth)
        self._subnets = SubnetResources(self._auth)
        self._security_groups = SecurityGroupResources(self._auth)
        self._rds = RDSResources(self._auth)
        self._lambda = LambdaResources(self._auth)
        self._elb = ELBResources(self._auth)
        self._eks = EKSResources(self._auth)
        self._route53 = Route53Resources(self._auth)
        self._iam_users = IAMUserResources(self._auth)
        self._iam_roles = IAMRoleResources(self._auth)
        self._iam_policies = IAMPolicyResources(self._auth)
        self._authenticated = False

    @property
    def name(self) -> str:
        return "aws"

    @property
    def display_name(self) -> str:
        return "Amazon Web Services"

    @property
    def supported_resource_types(self) -> list[ResourceType]:
        return [
            ResourceType.COMPUTE,
            ResourceType.STORAGE,
            ResourceType.NETWORK,
            ResourceType.DATABASE,
            ResourceType.SERVERLESS,
            ResourceType.LOAD_BALANCER,
            ResourceType.CONTAINER,
            ResourceType.DNS,
            ResourceType.IAM,
        ]

    async def authenticate(self) -> bool:
        """Verify AWS credentials via STS."""
        self._authenticated = await self._auth.verify()
        return self._authenticated

    async def is_authenticated(self) -> bool:
        return self._authenticated

    async def list_resources(
        self,
        resource_type: ResourceType,
        region: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> list[Resource]:
        """List AWS resources of the given type.

        Args:
            resource_type: Category of resources to list.
            region: AWS region. Use "*" to scan all enabled regions.
            tags: Optional tag filter. Resources must match all specified tags.

        Returns:
            List of unified Resource objects.

        Raises:
            ProviderError: If the resource type is not supported.
        """
        # Multi-region: scan all regions in parallel
        if region == self.ALL_REGIONS:
            return await self._list_all_regions(resource_type, tags)

        resources = await self._list_single_region(resource_type, region)

        # Client-side tag filtering
        if tags:
            resources = [
                r for r in resources
                if all(r.tags.get(k) == v for k, v in tags.items())
            ]

        return resources

    async def _list_single_region(
        self,
        resource_type: ResourceType,
        region: str | None = None,
    ) -> list[Resource]:
        """List resources in a single region."""
        match resource_type:
            case ResourceType.COMPUTE:
                return await self._ec2.list_instances(region=region)
            case ResourceType.STORAGE:
                return await self._s3.list_buckets()
            case ResourceType.NETWORK:
                vpcs = await self._vpc.list_vpcs(region=region)
                subnets = await self._subnets.list_subnets(region=region)
                sgs = await self._security_groups.list_security_groups(region=region)
                return vpcs + subnets + sgs
            case ResourceType.DATABASE:
                instances = await self._rds.list_instances(region=region)
                clusters = await self._rds.list_clusters(region=region)
                return instances + clusters
            case ResourceType.SERVERLESS:
                return await self._lambda.list_functions(region=region)
            case ResourceType.LOAD_BALANCER:
                return await self._elb.list_load_balancers(region=region)
            case ResourceType.CONTAINER:
                clusters = await self._eks.list_clusters(region=region)
                nodegroups = await self._eks.list_nodegroups(region=region)
                fargate = await self._eks.list_fargate_profiles(region=region)
                return clusters + nodegroups + fargate
            case ResourceType.DNS:
                zones = await self._route53.list_hosted_zones()
                records = await self._route53.list_records()
                return zones + records
            case ResourceType.IAM:
                users = await self._iam_users.list_users()
                roles = await self._iam_roles.list_roles()
                policies = await self._iam_policies.list_policies()
                return users + roles + policies
            case _:
                raise ProviderError(
                    "aws",
                    f"Resource type '{resource_type}' is not yet supported for AWS. "
                    f"Supported: {', '.join(rt.value for rt in self.supported_resource_types)}",
                )

    async def _list_all_regions(
        self,
        resource_type: ResourceType,
        tags: dict[str, str] | None = None,
    ) -> list[Resource]:
        """List resources across all enabled AWS regions in parallel.

        S3 is global and only scanned once. Other resource types are
        scanned per-region with concurrency limiting.
        """
        # S3 is global — no need to scan per-region
        if resource_type == ResourceType.STORAGE:
            resources = await self._s3.list_buckets()
        else:

            async def _fetch(rgn: str) -> list[Resource]:
                return await self._list_single_region(resource_type, region=rgn)

            resources = await scan_all_regions(self._auth, _fetch)

        if tags:
            resources = [
                r for r in resources
                if all(r.tags.get(k) == v for k, v in tags.items())
            ]

        return resources

    async def get_resource(
        self,
        resource_type: ResourceType,
        resource_id: str,
        region: str | None = None,
    ) -> Resource:
        """Fetch a single AWS resource by ID.

        Args:
            resource_type: COMPUTE for EC2.
            resource_id: The provider-specific ID.
            region: AWS region hint.

        Returns:
            A unified Resource.

        Raises:
            ProviderError: If the resource type is not supported.
            ResourceNotFoundError: If the resource doesn't exist.
        """
        match resource_type:
            case ResourceType.COMPUTE:
                return await self._ec2.get_instance(resource_id, region=region)
            case _:
                raise ProviderError(
                    "aws",
                    f"get_resource not supported for '{resource_type}' on AWS",
                )

    async def get_status(self) -> dict[str, str]:
        """Return AWS connection status and identity info."""
        base = await super().get_status()
        if self._authenticated:
            identity = await self._auth.get_identity()
            base.update(identity)
        return base
