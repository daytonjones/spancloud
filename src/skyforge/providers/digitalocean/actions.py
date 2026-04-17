"""DigitalOcean droplet actions — power_on, power_off, reboot, shutdown."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.digitalocean.auth import DigitalOceanAuth

logger = get_logger(__name__)


class ActionVerb(StrEnum):
    """Supported DO droplet actions."""

    START = "power_on"
    STOP = "power_off"
    SHUTDOWN = "shutdown"
    REBOOT = "reboot"


class ActionResult(BaseModel):
    """Result of a resource action."""

    success: bool
    action: str
    resource_id: str
    resource_type: str = "droplet"
    provider: str = "digitalocean"
    previous_state: str = ""
    current_state: str = ""
    message: str = ""


_VALID_STATES: dict[ActionVerb, set[str]] = {
    ActionVerb.START: {"off"},
    ActionVerb.STOP: {"active"},
    ActionVerb.SHUTDOWN: {"active"},
    ActionVerb.REBOOT: {"active"},
}


class DropletActions:
    """Execute actions on DO droplets."""

    def __init__(self, auth: DigitalOceanAuth) -> None:
        self._auth = auth

    async def get_droplet_state(self, droplet_id: str) -> dict[str, Any]:
        """Get the current state of a droplet."""
        try:
            data = await self._auth.get(f"/droplets/{droplet_id}")
            d = data.get("droplet", {})
            return {
                "state": d.get("status", "unknown"),
                "name": d.get("name", droplet_id),
                "size": (d.get("size") or {}).get("slug", ""),
            }
        except Exception as exc:
            logger.debug("Could not get droplet state: %s", exc)
            return {"state": "unknown", "name": droplet_id, "size": ""}

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    async def execute(
        self, action: ActionVerb, droplet_id: str
    ) -> ActionResult:
        """Execute an action on a droplet."""
        info = await self.get_droplet_state(droplet_id)
        current_state = info["state"]

        valid_states = _VALID_STATES.get(action, set())
        if current_state not in valid_states:
            return ActionResult(
                success=False,
                action=action.value,
                resource_id=droplet_id,
                previous_state=current_state,
                current_state=current_state,
                message=(
                    f"Cannot {action.value} droplet '{info['name']}' — "
                    f"current state is '{current_state}', "
                    f"must be one of: {', '.join(valid_states)}"
                ),
            )

        try:
            await self._auth.post(
                f"/droplets/{droplet_id}/actions",
                json_data={"type": action.value},
            )

            new_info = await self.get_droplet_state(droplet_id)

            return ActionResult(
                success=True,
                action=action.value,
                resource_id=droplet_id,
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
                resource_id=droplet_id,
                previous_state=current_state,
                message=f"Failed to {action.value} droplet: {exc}",
            )
