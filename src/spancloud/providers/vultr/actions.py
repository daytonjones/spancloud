"""Vultr resource actions — start, stop, reboot, reinstall instances.

All mutating actions require explicit confirmation. Actions use the
Vultr REST API with rate limiting and state validation.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.vultr.auth import VultrAuth

logger = get_logger(__name__)


class ActionVerb(StrEnum):
    """Supported Vultr instance actions."""

    START = "start"
    STOP = "halt"
    REBOOT = "reboot"


class ActionResult(BaseModel):
    """Result of a resource action."""

    success: bool
    action: str
    resource_id: str
    resource_type: str = "instance"
    provider: str = "vultr"
    previous_state: str = ""
    current_state: str = ""
    message: str = ""


_VALID_STATES: dict[ActionVerb, set[str]] = {
    ActionVerb.START: {"halted", "suspended"},
    ActionVerb.STOP: {"active"},
    ActionVerb.REBOOT: {"active"},
}


class VultrActions:
    """Execute actions on Vultr instances.

    Pre-validates instance state before acting.
    """

    def __init__(self, auth: VultrAuth) -> None:
        self._auth = auth

    async def get_instance_state(self, instance_id: str) -> dict[str, Any]:
        """Get the current state of a Vultr instance.

        Args:
            instance_id: Vultr instance ID.

        Returns:
            Dict with 'state', 'name', and 'plan'.
        """
        try:
            data = await self._auth.get(f"/instances/{instance_id}")
            inst = data.get("instance", {})
            return {
                "state": inst.get("status", "unknown"),
                "power_status": inst.get("power_status", ""),
                "name": inst.get("label", instance_id),
                "plan": inst.get("plan", ""),
            }
        except Exception as exc:
            logger.debug("Could not get instance state: %s", exc)
            return {"state": "unknown", "name": instance_id, "plan": ""}

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    async def execute(
        self,
        action: ActionVerb,
        instance_id: str,
    ) -> ActionResult:
        """Execute an action on a Vultr instance.

        Args:
            action: The action to perform (start, halt, reboot).
            instance_id: Vultr instance ID.

        Returns:
            ActionResult with outcome details.
        """
        info = await self.get_instance_state(instance_id)
        current_state = info["state"]

        valid_states = _VALID_STATES.get(action, set())
        if current_state not in valid_states:
            return ActionResult(
                success=False,
                action=action.value,
                resource_id=instance_id,
                previous_state=current_state,
                current_state=current_state,
                message=(
                    f"Cannot {action.value} instance '{info['name']}' — "
                    f"current state is '{current_state}', "
                    f"must be one of: {', '.join(valid_states)}"
                ),
            )

        try:
            await self._auth.post(f"/instances/{instance_id}/{action.value}")

            # Fetch new state
            new_info = await self.get_instance_state(instance_id)

            return ActionResult(
                success=True,
                action=action.value,
                resource_id=instance_id,
                previous_state=current_state,
                current_state=new_info["state"],
                message=(
                    f"Successfully sent {action.value} to '{info['name']}' "
                    f"({current_state} → {new_info['state']})"
                ),
            )

        except Exception as exc:
            return ActionResult(
                success=False,
                action=action.value,
                resource_id=instance_id,
                previous_state=current_state,
                message=f"Failed to {action.value} instance: {exc}",
            )
