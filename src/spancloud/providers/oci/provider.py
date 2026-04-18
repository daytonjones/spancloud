"""Oracle Cloud Infrastructure provider implementation."""

from __future__ import annotations

from spancloud.core.exceptions import ProviderError
from spancloud.core.provider import BaseProvider
from spancloud.core.resource import Resource, ResourceType
from spancloud.providers.oci.auth import OCIAuth
from spancloud.providers.oci.compute import InstanceResources
from spancloud.providers.oci.container import OKEResources
from spancloud.providers.oci.database import DatabaseResources
from spancloud.providers.oci.dns import DNSResources
from spancloud.providers.oci.loadbalancer import LoadBalancerResources
from spancloud.providers.oci.monitoring import OCIMonitoringAnalyzer, ResourceMetrics
from spancloud.providers.oci.network import NetworkResources
from spancloud.providers.oci.serverless import OCIFunctionsResources
from spancloud.providers.oci.storage import (
    BlockVolumeResources,
    ObjectStorageResources,
)
from spancloud.utils.logging import get_logger

logger = get_logger(__name__)


class OCIProvider(BaseProvider):
    """Oracle Cloud Infrastructure provider.

    Uses the standard OCI SDK credential chain — ~/.oci/config with a
    selectable profile (defaults to DEFAULT). Compartment defaults to the
    tenancy root; override via SPANCLOUD_OCI_COMPARTMENT_ID.
    """

    def __init__(self) -> None:
        self._auth = OCIAuth()
        self._instances = InstanceResources(self._auth)
        self._object_storage = ObjectStorageResources(self._auth)
        self._block_volumes = BlockVolumeResources(self._auth)
        self._network = NetworkResources(self._auth)
        self._databases = DatabaseResources(self._auth)
        self._oke = OKEResources(self._auth)
        self._loadbalancers = LoadBalancerResources(self._auth)
        self._dns = DNSResources(self._auth)
        self._serverless = OCIFunctionsResources(self._auth)
        self._monitoring = OCIMonitoringAnalyzer(self._auth)
        self._authenticated = False

    @property
    def name(self) -> str:
        return "oci"

    @property
    def display_name(self) -> str:
        return "Oracle Cloud (OCI)"

    @property
    def supported_resource_types(self) -> list[ResourceType]:
        return [
            ResourceType.COMPUTE,
            ResourceType.STORAGE,
            ResourceType.NETWORK,
            ResourceType.DATABASE,
            ResourceType.CONTAINER,
            ResourceType.LOAD_BALANCER,
            ResourceType.DNS,
            ResourceType.SERVERLESS,
        ]

    async def authenticate(self) -> bool:
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
        match resource_type:
            case ResourceType.COMPUTE:
                resources = await self._instances.list_instances(region=region)
            case ResourceType.STORAGE:
                buckets = await self._object_storage.list_buckets(region=region)
                volumes = await self._block_volumes.list_volumes(region=region)
                resources = buckets + volumes
            case ResourceType.NETWORK:
                resources = await self._network.list_all(region=region)
            case ResourceType.DATABASE:
                resources = await self._databases.list_databases(region=region)
            case ResourceType.CONTAINER:
                resources = await self._oke.list_clusters(region=region)
            case ResourceType.LOAD_BALANCER:
                resources = await self._loadbalancers.list_load_balancers(
                    region=region
                )
            case ResourceType.DNS:
                resources = await self._dns.list_zones(region=region)
            case ResourceType.SERVERLESS:
                resources = await self._serverless.list_functions(region=region)
            case _:
                raise ProviderError(
                    "oci",
                    f"Resource type '{resource_type}' is not supported. "
                    f"Supported: "
                    f"{', '.join(rt.value for rt in self.supported_resource_types)}",
                )

        if tags:
            resources = [
                r
                for r in resources
                if all(r.tags.get(k) == v for k, v in tags.items())
            ]
        return resources

    async def get_resource(
        self,
        resource_type: ResourceType,
        resource_id: str,
        region: str | None = None,
    ) -> Resource:
        raise ProviderError(
            "oci",
            f"get_resource not yet supported for '{resource_type}' on OCI",
        )

    async def get_instance_metrics(
        self,
        instance_id: str,
        region: str | None = None,
        hours: int = 1,
    ) -> ResourceMetrics:
        """Fetch OCI Monitoring metrics for a compute instance.

        Args:
            instance_id: The OCID of the compute instance.
            region: Optional region override.
            hours: Number of hours of history to fetch (default 1).

        Returns:
            ResourceMetrics with CPU, memory, network, and disk time series.
        """
        return await self._monitoring.get_instance_metrics(
            instance_id=instance_id, region=region, hours=hours
        )

    async def get_status(self) -> dict[str, str]:
        base = await super().get_status()
        if self._authenticated:
            identity = await self._auth.get_identity()
            base.update(identity)
        return base
