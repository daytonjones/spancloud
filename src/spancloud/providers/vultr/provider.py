"""Vultr provider implementation.

Uses the Vultr API v2 with Bearer token authentication.
All API calls are rate-limited and use exponential backoff retries.
"""

from __future__ import annotations

from spancloud.core.exceptions import ProviderError
from spancloud.core.provider import BaseProvider
from spancloud.core.resource import Resource, ResourceType
from spancloud.providers.vultr.auth import VultrAuth
from spancloud.providers.vultr.database import DatabaseResources
from spancloud.providers.vultr.dns import DNSResources
from spancloud.providers.vultr.instances import BareMetalResources, InstanceResources
from spancloud.providers.vultr.kubernetes import KubernetesResources
from spancloud.providers.vultr.loadbalancer import LoadBalancerResources
from spancloud.providers.vultr.storage import BlockStorageResources, ObjectStorageResources
from spancloud.providers.vultr.vpc import FirewallResources, VPCResources
from spancloud.utils.logging import get_logger

logger = get_logger(__name__)


class VultrProvider(BaseProvider):
    """Vultr cloud provider.

    Uses API key authentication via SPANCLOUD_VULTR_API_KEY.
    Supports instances, bare metal, block/object storage, VPCs,
    firewalls, managed databases, Kubernetes, load balancers, and DNS.
    """

    def __init__(self) -> None:
        self._auth = VultrAuth()
        self._instances = InstanceResources(self._auth)
        self._bare_metal = BareMetalResources(self._auth)
        self._block_storage = BlockStorageResources(self._auth)
        self._object_storage = ObjectStorageResources(self._auth)
        self._vpcs = VPCResources(self._auth)
        self._firewalls = FirewallResources(self._auth)
        self._databases = DatabaseResources(self._auth)
        self._kubernetes = KubernetesResources(self._auth)
        self._loadbalancers = LoadBalancerResources(self._auth)
        self._dns = DNSResources(self._auth)
        self._authenticated = False

    @property
    def name(self) -> str:
        return "vultr"

    @property
    def display_name(self) -> str:
        return "Vultr"

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
        ]

    async def authenticate(self) -> bool:
        """Verify Vultr API key."""
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
        """List Vultr resources of the given type.

        Args:
            resource_type: Category of resources to list.
            region: Optional region filter (e.g., 'ewr', 'lax').
            tags: Optional tag filter (client-side).

        Returns:
            List of unified Resource objects.

        Raises:
            ProviderError: If the resource type is not supported.
        """
        match resource_type:
            case ResourceType.COMPUTE:
                instances = await self._instances.list_instances(region=region)
                bare_metal = await self._bare_metal.list_bare_metals(region=region)
                resources = instances + bare_metal
            case ResourceType.STORAGE:
                blocks = await self._block_storage.list_blocks(region=region)
                objects = await self._object_storage.list_object_stores(region=region)
                resources = blocks + objects
            case ResourceType.NETWORK:
                vpcs = await self._vpcs.list_vpcs(region=region)
                firewalls = await self._firewalls.list_firewall_groups(region=region)
                resources = vpcs + firewalls
            case ResourceType.DATABASE:
                resources = await self._databases.list_databases(region=region)
            case ResourceType.CONTAINER:
                resources = await self._kubernetes.list_clusters(region=region)
            case ResourceType.LOAD_BALANCER:
                resources = await self._loadbalancers.list_load_balancers(region=region)
            case ResourceType.DNS:
                domains = await self._dns.list_domains()
                records = await self._dns.list_records()
                resources = domains + records
            case _:
                raise ProviderError(
                    "vultr",
                    f"Resource type '{resource_type}' is not supported for Vultr. "
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
        """Fetch a single Vultr resource by ID."""
        raise ProviderError(
            "vultr",
            f"get_resource not yet supported for '{resource_type}' on Vultr",
        )

    async def get_status(self) -> dict[str, str]:
        """Return Vultr connection status and account info."""
        base = await super().get_status()
        if self._authenticated:
            identity = await self._auth.get_identity()
            base.update(identity)
        return base
