"""Azure relationship mapper — wires VMs to VNets, NSGs, disks, LBs."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from skyforge.analysis.models import (
    RelationshipMap,
    RelationshipType,
    ResourceRelationship,
)
from skyforge.utils.logging import get_logger

if TYPE_CHECKING:
    from skyforge.providers.azure.auth import AzureAuth

logger = get_logger(__name__)


class AzureRelationshipMapper:
    """Builds a relationship graph for Azure resources."""

    def __init__(self, auth: AzureAuth) -> None:
        self._auth = auth

    async def map_relationships(
        self, region: str | None = None
    ) -> RelationshipMap:
        """Compute the full relationship map concurrently.

        Args:
            region: Optional location filter (currently advisory).
        """
        _ = region
        results = await asyncio.gather(
            asyncio.to_thread(self._vm_to_network),
            asyncio.to_thread(self._lb_to_backends),
            asyncio.to_thread(self._subnet_to_vnet_and_nsg),
        )
        rels: list[ResourceRelationship] = []
        for group in results:
            rels.extend(group)
        return RelationshipMap(provider="azure", relationships=rels)

    def _vm_to_network(self) -> list[ResourceRelationship]:
        """VM → NIC → Subnet/VNet, NIC → NSG, VM → Disks."""
        from azure.mgmt.compute import ComputeManagementClient
        from azure.mgmt.network import NetworkManagementClient

        rels: list[ResourceRelationship] = []
        try:
            compute = ComputeManagementClient(
                self._auth.get_credential(), self._auth.subscription_id
            )
            network = NetworkManagementClient(
                self._auth.get_credential(), self._auth.subscription_id
            )

            # Cache NICs by id for lookup
            nic_cache = {n.id: n for n in network.network_interfaces.list_all()}

            for vm in compute.virtual_machines.list_all():
                # VM → NIC → Subnet
                nics = (
                    vm.network_profile.network_interfaces
                    if vm.network_profile else []
                ) or []
                for nic_ref in nics:
                    nic = nic_cache.get(nic_ref.id)
                    if nic is None:
                        continue
                    for ipcfg in nic.ip_configurations or []:
                        subnet = getattr(ipcfg, "subnet", None)
                        subnet_id = getattr(subnet, "id", None) if subnet else None
                        if subnet_id:
                            rels.append(
                                ResourceRelationship(
                                    source_id=vm.id or "",
                                    source_type="virtual_machine",
                                    source_name=vm.name,
                                    target_id=subnet_id,
                                    target_type="subnet",
                                    target_name=subnet_id.rsplit("/", 1)[-1],
                                    relationship=RelationshipType.IN_SUBNET,
                                    provider="azure",
                                    region=vm.location or "",
                                )
                            )
                    # NIC → NSG
                    if nic.network_security_group and nic.network_security_group.id:
                        rels.append(
                            ResourceRelationship(
                                source_id=vm.id or "",
                                source_type="virtual_machine",
                                source_name=vm.name,
                                target_id=nic.network_security_group.id,
                                target_type="nsg",
                                target_name=nic.network_security_group.id.rsplit("/", 1)[-1],
                                relationship=RelationshipType.SECURED_BY,
                                provider="azure",
                                region=vm.location or "",
                            )
                        )

                # VM → data disks
                storage = vm.storage_profile
                if storage:
                    for disk in storage.data_disks or []:
                        managed = getattr(disk, "managed_disk", None)
                        if managed and getattr(managed, "id", None):
                            rels.append(
                                ResourceRelationship(
                                    source_id=managed.id,
                                    source_type="managed_disk",
                                    source_name=managed.id.rsplit("/", 1)[-1],
                                    target_id=vm.id or "",
                                    target_type="virtual_machine",
                                    target_name=vm.name,
                                    relationship=RelationshipType.ATTACHED_TO,
                                    provider="azure",
                                    region=vm.location or "",
                                )
                            )
        except Exception as exc:
            logger.debug("VM relationship scan skipped: %s", exc)
        return rels

    def _lb_to_backends(self) -> list[ResourceRelationship]:
        """LB backend pool → NICs / VMs."""
        from azure.mgmt.network import NetworkManagementClient

        rels: list[ResourceRelationship] = []
        try:
            network = NetworkManagementClient(
                self._auth.get_credential(), self._auth.subscription_id
            )
            for lb in network.load_balancers.list_all():
                for pool in lb.backend_address_pools or []:
                    for ipcfg in pool.backend_ip_configurations or []:
                        if not getattr(ipcfg, "id", None):
                            continue
                        # ipcfg.id looks like: .../networkInterfaces/<nic>/ipConfigurations/<cfg>
                        parts = ipcfg.id.split("/")
                        nic_id = ""
                        if "networkInterfaces" in parts:
                            idx = parts.index("networkInterfaces")
                            nic_id = "/".join(parts[: idx + 2])
                        target_name = nic_id.rsplit("/", 1)[-1] if nic_id else "(unknown)"
                        rels.append(
                            ResourceRelationship(
                                source_id=lb.id or "",
                                source_type="load_balancer",
                                source_name=lb.name,
                                target_id=nic_id or ipcfg.id,
                                target_type="network_interface",
                                target_name=target_name,
                                relationship=RelationshipType.TARGETS,
                                provider="azure",
                                region=lb.location or "",
                            )
                        )
        except Exception as exc:
            logger.debug("LB relationship scan skipped: %s", exc)
        return rels

    def _subnet_to_vnet_and_nsg(self) -> list[ResourceRelationship]:
        """Subnet → VNet, Subnet → NSG."""
        from azure.mgmt.network import NetworkManagementClient

        rels: list[ResourceRelationship] = []
        try:
            network = NetworkManagementClient(
                self._auth.get_credential(), self._auth.subscription_id
            )
            for vnet in network.virtual_networks.list_all():
                for subnet in vnet.subnets or []:
                    rels.append(
                        ResourceRelationship(
                            source_id=subnet.id or "",
                            source_type="subnet",
                            source_name=subnet.name,
                            target_id=vnet.id or "",
                            target_type="vnet",
                            target_name=vnet.name,
                            relationship=RelationshipType.IN_VPC,
                            provider="azure",
                            region=vnet.location or "",
                        )
                    )
                    nsg = getattr(subnet, "network_security_group", None)
                    if nsg and getattr(nsg, "id", None):
                        rels.append(
                            ResourceRelationship(
                                source_id=subnet.id or "",
                                source_type="subnet",
                                source_name=subnet.name,
                                target_id=nsg.id,
                                target_type="nsg",
                                target_name=nsg.id.rsplit("/", 1)[-1],
                                relationship=RelationshipType.SECURED_BY,
                                provider="azure",
                                region=vnet.location or "",
                            )
                        )
        except Exception as exc:
            logger.debug("Subnet relationship scan skipped: %s", exc)
        return rels
