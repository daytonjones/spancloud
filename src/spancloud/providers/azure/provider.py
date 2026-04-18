"""Azure provider implementation."""

from __future__ import annotations

from spancloud.core.exceptions import ProviderError
from spancloud.core.provider import BaseProvider
from spancloud.core.resource import Resource, ResourceType
from spancloud.providers.azure.aks import AKSResources
from spancloud.providers.azure.app_service import AppServiceResources
from spancloud.providers.azure.auth import AzureAuth
from spancloud.providers.azure.compute import VMResources
from spancloud.providers.azure.database import CosmosDBResources, SQLResources
from spancloud.providers.azure.dns import DNSResources
from spancloud.providers.azure.loadbalancer import LoadBalancerResources
from spancloud.providers.azure.monitoring import AzureMonitoringAnalyzer, ResourceMetrics
from spancloud.providers.azure.network import VNetResources
from spancloud.providers.azure.storage import StorageAccountResources
from spancloud.utils.logging import get_logger

logger = get_logger(__name__)


class AzureProvider(BaseProvider):
    """Microsoft Azure provider.

    Uses DefaultAzureCredential — reads from env vars, managed identity,
    Azure CLI, or interactive browser. Subscription ID is supplied via
    SPANCLOUD_AZURE_SUBSCRIPTION_ID or 'spancloud auth login azure'.
    """

    def __init__(self) -> None:
        self._auth = AzureAuth()
        self._vms = VMResources(self._auth)
        self._storage = StorageAccountResources(self._auth)
        self._monitoring = AzureMonitoringAnalyzer(self._auth)
        self._network = VNetResources(self._auth)
        self._sql = SQLResources(self._auth)
        self._cosmos = CosmosDBResources(self._auth)
        self._app_service = AppServiceResources(self._auth)
        self._aks = AKSResources(self._auth)
        self._loadbalancers = LoadBalancerResources(self._auth)
        self._dns = DNSResources(self._auth)
        self._authenticated = False

    @property
    def name(self) -> str:
        return "azure"

    @property
    def display_name(self) -> str:
        return "Microsoft Azure"

    @property
    def supported_resource_types(self) -> list[ResourceType]:
        return [
            ResourceType.COMPUTE,
            ResourceType.STORAGE,
            ResourceType.NETWORK,
            ResourceType.DATABASE,
            ResourceType.SERVERLESS,
            ResourceType.CONTAINER,
            ResourceType.LOAD_BALANCER,
            ResourceType.DNS,
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
        """List Azure resources of the given type."""
        match resource_type:
            case ResourceType.COMPUTE:
                resources = await self._vms.list_vms(region=region)
            case ResourceType.STORAGE:
                resources = await self._storage.list_accounts(region=region)
            case ResourceType.NETWORK:
                resources = await self._network.list_all(region=region)
            case ResourceType.DATABASE:
                sql = await self._sql.list_databases(region=region)
                cosmos = await self._cosmos.list_accounts(region=region)
                resources = sql + cosmos
            case ResourceType.SERVERLESS:
                resources = await self._app_service.list_sites(region=region)
            case ResourceType.CONTAINER:
                resources = await self._aks.list_clusters(region=region)
            case ResourceType.LOAD_BALANCER:
                resources = await self._loadbalancers.list_load_balancers(
                    region=region
                )
            case ResourceType.DNS:
                resources = await self._dns.list_zones(region=region)
            case _:
                raise ProviderError(
                    "azure",
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
            "azure",
            f"get_resource not yet supported for '{resource_type}' on Azure",
        )

    async def get_instance_metrics(
        self,
        resource_id: str,
        region: str | None = None,
        hours: int = 1,
    ) -> ResourceMetrics:
        """Fetch Azure Monitor metrics for a virtual machine."""
        return await self._monitoring.get_instance_metrics(
            resource_id, hours=hours
        )

    async def get_status(self) -> dict[str, str]:
        base = await super().get_status()
        if self._authenticated:
            identity = await self._auth.get_identity()
            base.update(identity)
        return base
