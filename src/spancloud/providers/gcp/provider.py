"""GCP provider implementation."""

from __future__ import annotations

from spancloud.core.exceptions import ProviderError
from spancloud.core.provider import BaseProvider
from spancloud.core.resource import Resource, ResourceType
from spancloud.providers.gcp.auth import GCPAuth
from spancloud.providers.gcp.cloudrun import CloudRunResources
from spancloud.providers.gcp.cloudsql import CloudSQLResources
from spancloud.providers.gcp.dns import CloudDNSResources
from spancloud.providers.gcp.functions import CloudFunctionsResources
from spancloud.providers.gcp.gke import GKEResources
from spancloud.providers.gcp.loadbalancer import LoadBalancerResources
from spancloud.providers.gcp.resources import ComputeResources, StorageResources
from spancloud.providers.gcp.vpc import FirewallResources, NetworkResources, SubnetResources
from spancloud.utils.logging import get_logger

logger = get_logger(__name__)


class GCPProvider(BaseProvider):
    """Google Cloud Platform provider.

    Uses Application Default Credentials (environment variables,
    gcloud auth, service account keys, workload identity).
    """

    def __init__(self) -> None:
        self._auth = GCPAuth()
        self._compute = ComputeResources(self._auth)
        self._storage = StorageResources(self._auth)
        self._networks = NetworkResources(self._auth)
        self._subnets = SubnetResources(self._auth)
        self._firewalls = FirewallResources(self._auth)
        self._cloudsql = CloudSQLResources(self._auth)
        self._gke = GKEResources(self._auth)
        self._functions = CloudFunctionsResources(self._auth)
        self._cloudrun = CloudRunResources(self._auth)
        self._loadbalancer = LoadBalancerResources(self._auth)
        self._dns = CloudDNSResources(self._auth)
        self._authenticated = False

    @property
    def name(self) -> str:
        return "gcp"

    @property
    def display_name(self) -> str:
        return "Google Cloud Platform"

    @property
    def supported_resource_types(self) -> list[ResourceType]:
        return [
            ResourceType.COMPUTE,
            ResourceType.STORAGE,
            ResourceType.NETWORK,
            ResourceType.DATABASE,
            ResourceType.CONTAINER,
            ResourceType.SERVERLESS,
            ResourceType.LOAD_BALANCER,
            ResourceType.DNS,
        ]

    async def authenticate(self) -> bool:
        """Verify GCP credentials via Application Default Credentials."""
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
        """List GCP resources of the given type.

        Args:
            resource_type: Category of resources to list.
            region: Optional region filter.
            tags: Optional label filter (client-side).

        Returns:
            List of unified Resource objects.

        Raises:
            ProviderError: If the resource type is not supported.
        """
        match resource_type:
            case ResourceType.COMPUTE:
                resources = await self._compute.list_instances(region=region)
            case ResourceType.STORAGE:
                resources = await self._storage.list_buckets()
            case ResourceType.NETWORK:
                networks = await self._networks.list_networks(region=region)
                subnets = await self._subnets.list_subnets(region=region)
                firewalls = await self._firewalls.list_firewalls(region=region)
                resources = networks + subnets + firewalls
            case ResourceType.DATABASE:
                resources = await self._cloudsql.list_instances(region=region)
            case ResourceType.CONTAINER:
                clusters = await self._gke.list_clusters(region=region)
                node_pools = await self._gke.list_node_pools(region=region)
                resources = clusters + node_pools
            case ResourceType.SERVERLESS:
                functions = await self._functions.list_functions(region=region)
                run_services = await self._cloudrun.list_services(region=region)
                resources = functions + run_services
            case ResourceType.LOAD_BALANCER:
                resources = await self._loadbalancer.list_load_balancers(region=region)
            case ResourceType.DNS:
                zones = await self._dns.list_zones()
                records = await self._dns.list_records()
                resources = zones + records
            case _:
                raise ProviderError(
                    "gcp",
                    f"Resource type '{resource_type}' is not yet supported for GCP. "
                    f"Supported: {', '.join(rt.value for rt in self.supported_resource_types)}",
                )

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
        """Fetch a single GCP resource by ID.

        Args:
            resource_type: COMPUTE for GCE instances.
            resource_id: The resource name or ID.
            region: Zone for compute instances.

        Returns:
            A unified Resource.

        Raises:
            ProviderError: If the resource type is not supported or zone is missing.
            ResourceNotFoundError: If the resource doesn't exist.
        """
        match resource_type:
            case ResourceType.COMPUTE:
                if not region:
                    raise ProviderError(
                        "gcp",
                        "Zone (passed as region) is required to fetch a GCE instance",
                    )
                return await self._compute.get_instance(resource_id, zone=region)
            case _:
                raise ProviderError(
                    "gcp",
                    f"get_resource not supported for '{resource_type}' on GCP",
                )

    async def get_status(self) -> dict[str, str]:
        """Return GCP connection status and project info."""
        base = await super().get_status()
        if self._authenticated:
            identity = await self._auth.get_identity()
            base.update(identity)
        return base
