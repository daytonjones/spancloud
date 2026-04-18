"""Azure VM lifecycle actions — start, stop (deallocate), restart."""

from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from spancloud.providers.azure.compute import _parse_resource_group
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.azure.auth import AzureAuth

logger = get_logger(__name__)


class ActionVerb(StrEnum):
    """Supported Azure VM actions."""

    START = "start"
    STOP = "deallocate"  # Azure "stop" still bills compute; deallocate is the cost-saver
    RESTART = "restart"
    POWEROFF = "poweroff"  # Stop-only (VM still billed for compute)


class ActionResult(BaseModel):
    """Result of a VM action."""

    success: bool
    action: str
    resource_id: str
    resource_type: str = "virtual_machine"
    provider: str = "azure"
    previous_state: str = ""
    current_state: str = ""
    message: str = ""


# Valid "PowerState/*" codes required before each action is allowed.
_VALID_STATES: dict[ActionVerb, set[str]] = {
    ActionVerb.START: {"PowerState/stopped", "PowerState/deallocated"},
    ActionVerb.STOP: {"PowerState/running"},
    ActionVerb.POWEROFF: {"PowerState/running"},
    ActionVerb.RESTART: {"PowerState/running"},
}


class VMActions:
    """Execute lifecycle actions on Azure VMs."""

    def __init__(self, auth: AzureAuth) -> None:
        self._auth = auth

    async def get_instance_state(
        self, vm_name: str, resource_group: str | None = None
    ) -> dict[str, Any]:
        """Get the current power state + metadata for a VM.

        Args:
            vm_name: The VM name (or full resource ID).
            resource_group: Required unless `vm_name` is a full resource ID.
        """
        return await asyncio.to_thread(
            self._sync_get_state, vm_name, resource_group
        )

    def _sync_get_state(
        self, vm_name: str, resource_group: str | None
    ) -> dict[str, Any]:
        from azure.mgmt.compute import ComputeManagementClient

        client = ComputeManagementClient(
            self._auth.get_credential(), self._auth.subscription_id
        )

        rg, name = _resolve_rg_name(vm_name, resource_group)
        vm = client.virtual_machines.get(rg, name)
        iv = client.virtual_machines.instance_view(rg, name)
        power = "PowerState/unknown"
        for s in iv.statuses or []:
            if s.code and s.code.startswith("PowerState/"):
                power = s.code
                break

        return {
            "state": power,
            "name": vm.name,
            "machine_type": (
                vm.hardware_profile.vm_size if vm.hardware_profile else ""
            ),
            "resource_group": rg,
        }

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    async def execute(
        self,
        action: ActionVerb,
        vm_name: str,
        resource_group: str | None = None,
    ) -> ActionResult:
        """Execute an action on a VM."""
        info = await self.get_instance_state(vm_name, resource_group)
        current_state = info["state"]
        rg = info["resource_group"]
        actual_name = info["name"]

        valid_states = _VALID_STATES.get(action, set())
        if current_state not in valid_states:
            return ActionResult(
                success=False,
                action=action.value,
                resource_id=actual_name,
                previous_state=current_state,
                current_state=current_state,
                message=(
                    f"Cannot {action.value} VM '{actual_name}' — "
                    f"current state is '{current_state}', "
                    f"must be one of: {', '.join(valid_states)}"
                ),
            )

        try:
            await asyncio.to_thread(self._sync_execute, action, rg, actual_name)
            new_info = await self.get_instance_state(actual_name, rg)
            return ActionResult(
                success=True,
                action=action.value,
                resource_id=actual_name,
                previous_state=current_state,
                current_state=new_info["state"],
                message=(
                    f"Successfully sent {action.value} to '{actual_name}' "
                    f"({current_state} → {new_info['state']})"
                ),
            )
        except Exception as exc:
            return ActionResult(
                success=False,
                action=action.value,
                resource_id=actual_name,
                previous_state=current_state,
                message=f"Failed to {action.value} VM: {exc}",
            )

    def _sync_execute(self, action: ActionVerb, rg: str, name: str) -> None:
        from azure.mgmt.compute import ComputeManagementClient

        client = ComputeManagementClient(
            self._auth.get_credential(), self._auth.subscription_id
        )

        if action == ActionVerb.START:
            client.virtual_machines.begin_start(rg, name).wait(timeout=120)
        elif action == ActionVerb.STOP:
            # "deallocate" — releases compute + stops billing
            client.virtual_machines.begin_deallocate(rg, name).wait(timeout=120)
        elif action == ActionVerb.POWEROFF:
            # "power_off" — VM stopped but still allocated (compute still billed)
            client.virtual_machines.begin_power_off(rg, name).wait(timeout=120)
        elif action == ActionVerb.RESTART:
            client.virtual_machines.begin_restart(rg, name).wait(timeout=120)


def _resolve_rg_name(
    vm_name: str, resource_group: str | None
) -> tuple[str, str]:
    """Return (resource_group, name) from either a bare name or full ID."""
    if vm_name.startswith("/subscriptions/"):
        rg = _parse_resource_group(vm_name)
        name = vm_name.rsplit("/", 1)[-1]
        return rg, name
    if not resource_group:
        raise ValueError(
            "resource_group is required when vm_name is not a full resource ID"
        )
    return resource_group, vm_name
