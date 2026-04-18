"""Azure Virtual Network, subnet, NSG, public IP resource discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.providers.azure.compute import _parse_resource_group
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.azure.auth import AzureAuth

logger = get_logger(__name__)


class VNetResources:
    """Handles Azure Virtual Network + NSG + Public IP discovery."""

    def __init__(self, auth: AzureAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_all(self, region: str | None = None) -> list[Resource]:
        """List VNets, subnets, NSGs, and public IPs in one batch."""
        vnets, subnets, nsgs, public_ips = await asyncio.gather(
            asyncio.to_thread(self._sync_list_vnets, region),
            asyncio.to_thread(self._sync_list_subnets, region),
            asyncio.to_thread(self._sync_list_nsgs, region),
            asyncio.to_thread(self._sync_list_public_ips, region),
        )
        combined = vnets + subnets + nsgs + public_ips
        logger.debug("Found %d Azure network resources", len(combined))
        return combined

    # ---- VNets ----

    def _sync_list_vnets(self, region: str | None) -> list[Resource]:
        from azure.mgmt.network import NetworkManagementClient

        credential = self._auth.get_credential()
        client = NetworkManagementClient(credential, self._auth.subscription_id)

        resources: list[Resource] = []
        for vnet in client.virtual_networks.list_all():
            if region and vnet.location != region:
                continue
            resources.append(self._map_vnet(vnet))
        return resources

    def _map_vnet(self, vnet: Any) -> Resource:
        address_space = getattr(vnet, "address_space", None)
        cidrs = address_space.address_prefixes if address_space else []
        subnets = getattr(vnet, "subnets", []) or []

        return Resource(
            id=vnet.id or vnet.name,
            name=vnet.name,
            resource_type=ResourceType.NETWORK,
            provider="azure",
            region=vnet.location,
            state=ResourceState.RUNNING,
            tags=dict(vnet.tags or {}),
            metadata={
                "address_prefixes": ", ".join(cidrs) if cidrs else "",
                "subnet_count": str(len(subnets)),
                "resource_group": _parse_resource_group(vnet.id or ""),
                "resource_subtype": "vnet",
            },
        )

    # ---- Subnets ----

    def _sync_list_subnets(self, region: str | None) -> list[Resource]:
        from azure.mgmt.network import NetworkManagementClient

        credential = self._auth.get_credential()
        client = NetworkManagementClient(credential, self._auth.subscription_id)

        resources: list[Resource] = []
        for vnet in client.virtual_networks.list_all():
            if region and vnet.location != region:
                continue
            for subnet in vnet.subnets or []:
                resources.append(self._map_subnet(subnet, vnet))
        return resources

    def _map_subnet(self, subnet: Any, parent_vnet: Any) -> Resource:
        return Resource(
            id=subnet.id or subnet.name,
            name=subnet.name,
            resource_type=ResourceType.NETWORK,
            provider="azure",
            region=parent_vnet.location,
            state=ResourceState.RUNNING,
            metadata={
                "cidr": getattr(subnet, "address_prefix", "") or "",
                "vnet": parent_vnet.name,
                "nsg": _resource_name_from_id(
                    getattr(subnet, "network_security_group", None)
                ),
                "resource_group": _parse_resource_group(parent_vnet.id or ""),
                "resource_subtype": "subnet",
            },
        )

    # ---- NSGs ----

    def _sync_list_nsgs(self, region: str | None) -> list[Resource]:
        from azure.mgmt.network import NetworkManagementClient

        credential = self._auth.get_credential()
        client = NetworkManagementClient(credential, self._auth.subscription_id)

        resources: list[Resource] = []
        for nsg in client.network_security_groups.list_all():
            if region and nsg.location != region:
                continue
            resources.append(self._map_nsg(nsg))
        return resources

    def _map_nsg(self, nsg: Any) -> Resource:
        rules = getattr(nsg, "security_rules", []) or []
        default_rules = getattr(nsg, "default_security_rules", []) or []

        return Resource(
            id=nsg.id or nsg.name,
            name=nsg.name,
            resource_type=ResourceType.NETWORK,
            provider="azure",
            region=nsg.location,
            state=ResourceState.RUNNING,
            tags=dict(nsg.tags or {}),
            metadata={
                "custom_rule_count": str(len(rules)),
                "default_rule_count": str(len(default_rules)),
                "resource_group": _parse_resource_group(nsg.id or ""),
                "resource_subtype": "nsg",
            },
        )

    # ---- Public IPs ----

    def _sync_list_public_ips(self, region: str | None) -> list[Resource]:
        from azure.mgmt.network import NetworkManagementClient

        credential = self._auth.get_credential()
        client = NetworkManagementClient(credential, self._auth.subscription_id)

        resources: list[Resource] = []
        for pip in client.public_ip_addresses.list_all():
            if region and pip.location != region:
                continue
            resources.append(self._map_public_ip(pip))
        return resources

    def _map_public_ip(self, pip: Any) -> Resource:
        allocation = str(getattr(pip, "public_ip_allocation_method", ""))
        sku = getattr(pip, "sku", None)
        attached = getattr(pip, "ip_configuration", None) is not None

        return Resource(
            id=pip.id or pip.name,
            name=pip.name,
            resource_type=ResourceType.NETWORK,
            provider="azure",
            region=pip.location,
            state=ResourceState.RUNNING if attached else ResourceState.STOPPED,
            tags=dict(pip.tags or {}),
            metadata={
                "ip_address": getattr(pip, "ip_address", "") or "",
                "allocation_method": allocation,
                "sku": str(getattr(sku, "name", "") or ""),
                "attached": str(attached),
                "resource_group": _parse_resource_group(pip.id or ""),
                "resource_subtype": "public_ip",
            },
        )


def _resource_name_from_id(sub_resource: Any) -> str:
    """Extract the resource name from a nested Azure SubResource."""
    if sub_resource is None:
        return ""
    rid = getattr(sub_resource, "id", "") or ""
    return rid.rsplit("/", 1)[-1] if rid else ""
