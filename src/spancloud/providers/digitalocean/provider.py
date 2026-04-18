"""DigitalOcean provider implementation."""

from __future__ import annotations

from typing import Any

from spancloud.core.exceptions import ProviderError
from spancloud.core.provider import BaseProvider
from spancloud.core.resource import Resource, ResourceType
from spancloud.providers.digitalocean.auth import DigitalOceanAuth
from spancloud.providers.digitalocean.database import DatabaseResources
from spancloud.providers.digitalocean.dns import DNSResources
from spancloud.providers.digitalocean.droplets import DropletResources
from spancloud.providers.digitalocean.kubernetes import KubernetesResources
from spancloud.providers.digitalocean.loadbalancer import LoadBalancerResources
from spancloud.providers.digitalocean.storage import (
    SpacesResources,
    VolumeResources,
)
from spancloud.providers.digitalocean.serverless import ServerlessResources
from spancloud.providers.digitalocean.vpc import FirewallResources, VPCResources
from spancloud.utils.logging import get_logger

logger = get_logger(__name__)


class DigitalOceanProvider(BaseProvider):
    """DigitalOcean provider.

    Uses Personal Access Token auth via SPANCLOUD_DIGITALOCEAN_TOKEN.
    """

    def __init__(self) -> None:
        self._auth = DigitalOceanAuth()
        self._droplets = DropletResources(self._auth)
        self._volumes = VolumeResources(self._auth)
        self._spaces = SpacesResources(self._auth)
        self._vpcs = VPCResources(self._auth)
        self._firewalls = FirewallResources(self._auth)
        self._databases = DatabaseResources(self._auth)
        self._kubernetes = KubernetesResources(self._auth)
        self._loadbalancers = LoadBalancerResources(self._auth)
        self._dns = DNSResources(self._auth)
        self._serverless = ServerlessResources(self._auth)
        self._authenticated = False

    @property
    def name(self) -> str:
        return "digitalocean"

    @property
    def display_name(self) -> str:
        return "Digital Ocean"

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
        """List DO resources of the given type."""
        match resource_type:
            case ResourceType.COMPUTE:
                resources = await self._droplets.list_droplets(region=region)
            case ResourceType.STORAGE:
                volumes = await self._volumes.list_volumes(region=region)
                cdn = await self._spaces.list_cdn_endpoints(region=region)
                resources = volumes + cdn
            case ResourceType.NETWORK:
                vpcs = await self._vpcs.list_vpcs(region=region)
                firewalls = await self._firewalls.list_firewalls(region=region)
                resources = vpcs + firewalls
            case ResourceType.DATABASE:
                resources = await self._databases.list_databases(region=region)
            case ResourceType.CONTAINER:
                resources = await self._kubernetes.list_clusters(region=region)
            case ResourceType.LOAD_BALANCER:
                resources = await self._loadbalancers.list_load_balancers(
                    region=region
                )
            case ResourceType.DNS:
                domains = await self._dns.list_domains()
                records = await self._dns.list_records()
                resources = domains + records
            case ResourceType.SERVERLESS:
                resources = await self._serverless.list_serverless(region=region)
            case _:
                raise ProviderError(
                    "digitalocean",
                    f"Resource type '{resource_type}' is not supported. "
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
        raise ProviderError(
            "digitalocean",
            f"get_resource not yet supported for '{resource_type}' on DigitalOcean",
        )

    async def get_instance_metrics(
        self,
        resource_id: str,
        region: str | None = None,
        hours: int = 1,
    ) -> Any:
        """Get monitoring metrics for a Droplet.

        Args:
            resource_id: Droplet ID (numeric string).
            region: Ignored — DO metrics API uses host_id, not region.
            hours: Hours of data to retrieve (default 1).

        Returns:
            ResourceMetrics with per-metric time series.
        """
        from spancloud.providers.digitalocean.monitoring import (
            DigitalOceanMonitoringAnalyzer,
        )

        analyzer = DigitalOceanMonitoringAnalyzer(self._auth)
        return await analyzer.get_instance_metrics(resource_id, hours=hours)

    async def get_status(self) -> dict[str, str]:
        base = await super().get_status()
        if self._authenticated:
            identity = await self._auth.get_identity()
            base.update(identity)
        return base
