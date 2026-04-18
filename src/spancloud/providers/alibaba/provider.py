"""Alibaba Cloud provider implementation."""

from __future__ import annotations

from spancloud.core.exceptions import ProviderError
from spancloud.core.provider import BaseProvider
from spancloud.core.resource import Resource, ResourceType
from spancloud.providers.alibaba.auth import AlibabaAuth
from spancloud.providers.alibaba.compute import ECSResources
from spancloud.providers.alibaba.container import ACKResources
from spancloud.providers.alibaba.database import RDSResources
from spancloud.providers.alibaba.dns import DNSResources
from spancloud.providers.alibaba.loadbalancer import SLBResources
from spancloud.providers.alibaba.network import NetworkResources
from spancloud.providers.alibaba.storage import DiskResources, OSSResources
from spancloud.utils.logging import get_logger

logger = get_logger(__name__)


class AlibabaCloudProvider(BaseProvider):
    """Alibaba Cloud provider.

    Uses AccessKey ID + Secret authentication. Credentials are read from
    SPANCLOUD_ALIBABA_ACCESS_KEY_ID / _SECRET environment variables or the
    Spancloud encrypted credential store (OS keychain by default).
    """

    def __init__(self) -> None:
        self._auth = AlibabaAuth()
        self._ecs = ECSResources(self._auth)
        self._oss = OSSResources(self._auth)
        self._disks = DiskResources(self._auth)
        self._network = NetworkResources(self._auth)
        self._rds = RDSResources(self._auth)
        self._ack = ACKResources(self._auth)
        self._slb = SLBResources(self._auth)
        self._dns = DNSResources(self._auth)
        self._authenticated = False

    @property
    def name(self) -> str:
        return "alibaba"

    @property
    def display_name(self) -> str:
        return "Alibaba Cloud"

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
                resources = await self._ecs.list_instances(region=region)
            case ResourceType.STORAGE:
                buckets = await self._oss.list_buckets(region=region)
                disks = await self._disks.list_disks(region=region)
                resources = buckets + disks
            case ResourceType.NETWORK:
                resources = await self._network.list_all(region=region)
            case ResourceType.DATABASE:
                resources = await self._rds.list_instances(region=region)
            case ResourceType.CONTAINER:
                resources = await self._ack.list_clusters(region=region)
            case ResourceType.LOAD_BALANCER:
                resources = await self._slb.list_load_balancers(region=region)
            case ResourceType.DNS:
                resources = await self._dns.list_domains(region=region)
            case _:
                raise ProviderError(
                    "alibaba",
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
            "alibaba",
            f"get_resource not yet supported for '{resource_type}' on Alibaba",
        )

    async def get_status(self) -> dict[str, str]:
        base = await super().get_status()
        if self._authenticated:
            identity = await self._auth.get_identity()
            base.update(identity)
        return base
