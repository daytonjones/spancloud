"""Azure Virtual Machine (compute) resource discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.azure.auth import AzureAuth

logger = get_logger(__name__)

_VM_STATE_MAP: dict[str, ResourceState] = {
    "PowerState/running": ResourceState.RUNNING,
    "PowerState/stopped": ResourceState.STOPPED,
    "PowerState/deallocated": ResourceState.STOPPED,
    "PowerState/starting": ResourceState.PENDING,
    "PowerState/stopping": ResourceState.PENDING,
    "PowerState/deallocating": ResourceState.PENDING,
    "PowerState/unknown": ResourceState.UNKNOWN,
}


class VMResources:
    """Handles Azure Virtual Machine discovery."""

    def __init__(self, auth: AzureAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_vms(self, region: str | None = None) -> list[Resource]:
        """List all VMs in the active subscription.

        Args:
            region: Optional Azure region filter (e.g., 'eastus').
        """
        raw = await asyncio.to_thread(self._sync_list_vms, region)
        logger.debug("Found %d Azure VMs", len(raw))
        return raw

    def _sync_list_vms(self, region: str | None) -> list[Resource]:
        from azure.mgmt.compute import ComputeManagementClient

        credential = self._auth.get_credential()
        client = ComputeManagementClient(credential, self._auth.subscription_id)

        resources: list[Resource] = []
        for vm in client.virtual_machines.list_all():
            if region and vm.location != region:
                continue

            # Fetch power state via instance view
            rg = _parse_resource_group(vm.id or "")
            power_state = "PowerState/unknown"
            try:
                iv = client.virtual_machines.instance_view(rg, vm.name)
                for s in iv.statuses or []:
                    if s.code and s.code.startswith("PowerState/"):
                        power_state = s.code
                        break
            except Exception:
                pass

            resources.append(self._map_vm(vm, power_state, rg))

        return resources

    def _map_vm(self, vm: Any, power_state: str, rg: str) -> Resource:
        """Map an Azure VM to a unified Resource."""
        tags = dict(vm.tags or {})
        hw = getattr(vm, "hardware_profile", None)
        os_profile = getattr(vm, "os_profile", None)
        storage = getattr(vm, "storage_profile", None)
        image_ref = getattr(storage, "image_reference", None) if storage else None

        return Resource(
            id=vm.id or vm.name,
            name=vm.name,
            resource_type=ResourceType.COMPUTE,
            provider="azure",
            region=vm.location,
            state=_VM_STATE_MAP.get(power_state, ResourceState.UNKNOWN),
            tags=tags,
            metadata={
                "vm_size": hw.vm_size if hw else "",
                "resource_group": rg,
                "os_type": (
                    str(storage.os_disk.os_type)
                    if storage and storage.os_disk
                    else ""
                ),
                "computer_name": getattr(os_profile, "computer_name", "") or "",
                "image_publisher": getattr(image_ref, "publisher", "") or "",
                "image_offer": getattr(image_ref, "offer", "") or "",
                "image_sku": getattr(image_ref, "sku", "") or "",
                "power_state": power_state,
                "resource_subtype": "virtual_machine",
            },
        )


def _parse_resource_group(resource_id: str) -> str:
    """Extract the resource group name from an Azure resource ID."""
    # Format: /subscriptions/{sub}/resourceGroups/{rg}/providers/...
    parts = resource_id.split("/")
    for i, p in enumerate(parts):
        if p.lower() == "resourcegroups" and i + 1 < len(parts):
            return parts[i + 1]
    return ""
