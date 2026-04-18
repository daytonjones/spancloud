"""GCP resource actions — start, stop, reset GCE instances.

All mutating actions require explicit confirmation. Actions are rate-limited
and include pre-flight validation (instance state checks).
"""

from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from google.cloud import compute_v1
from pydantic import BaseModel

from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff
from spancloud.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from spancloud.providers.gcp.auth import GCPAuth

logger = get_logger(__name__)

_GCE_LIMITER = RateLimiter(calls_per_second=8.0, max_concurrency=5)


class ActionVerb(StrEnum):
    """Supported GCE instance actions."""

    START = "start"
    STOP = "stop"
    RESET = "reset"


class ActionResult(BaseModel):
    """Result of a resource action."""

    success: bool
    action: str
    resource_id: str
    resource_type: str = "gce_instance"
    provider: str = "gcp"
    previous_state: str = ""
    current_state: str = ""
    message: str = ""


# Valid state transitions for each action
_VALID_STATES: dict[ActionVerb, set[str]] = {
    ActionVerb.START: {"TERMINATED", "SUSPENDED"},
    ActionVerb.STOP: {"RUNNING"},
    ActionVerb.RESET: {"RUNNING"},
}


class GCEActions:
    """Execute actions on GCE instances.

    Pre-validates instance state before acting. All actions
    return ActionResult with before/after state.
    """

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    async def get_instance_state(
        self, instance_name: str, zone: str
    ) -> dict[str, Any]:
        """Get the current state and metadata of a GCE instance.

        Args:
            instance_name: GCE instance name.
            zone: Zone where the instance lives.

        Returns:
            Dict with 'state', 'name', and 'machine_type'.
        """
        project = self._auth.project_id
        client = compute_v1.InstancesClient(credentials=self._auth.credentials)

        try:
            async with _GCE_LIMITER:
                instance = await asyncio.to_thread(
                    client.get, project=project, zone=zone, instance=instance_name
                )
            return {
                "state": instance.status or "UNKNOWN",
                "name": instance.name or instance_name,
                "machine_type": (instance.machine_type or "").rsplit("/", 1)[-1],
            }
        except Exception as exc:
            logger.debug("Could not get instance state: %s", exc)
            return {
                "state": "UNKNOWN",
                "name": instance_name,
                "machine_type": "",
            }

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    async def execute(
        self,
        action: ActionVerb,
        instance_name: str,
        zone: str,
    ) -> ActionResult:
        """Execute an action on a GCE instance.

        Validates the instance is in a valid state before proceeding.

        Args:
            action: The action to perform.
            instance_name: GCE instance name.
            zone: Zone where the instance lives.

        Returns:
            ActionResult with outcome details.
        """
        project = self._auth.project_id
        if not project:
            return ActionResult(
                success=False,
                action=action.value,
                resource_id=instance_name,
                message="No GCP project configured.",
            )

        # Pre-flight: check current state
        info = await self.get_instance_state(instance_name, zone)
        current_state = info["state"]

        valid_states = _VALID_STATES.get(action, set())
        if current_state not in valid_states:
            return ActionResult(
                success=False,
                action=action.value,
                resource_id=instance_name,
                previous_state=current_state,
                current_state=current_state,
                message=(
                    f"Cannot {action.value} instance '{info['name']}' — "
                    f"current state is '{current_state}', "
                    f"must be one of: {', '.join(valid_states)}"
                ),
            )

        client = compute_v1.InstancesClient(credentials=self._auth.credentials)

        try:
            async with _GCE_LIMITER:
                match action:
                    case ActionVerb.START:
                        await asyncio.to_thread(
                            client.start,
                            project=project, zone=zone, instance=instance_name,
                        )
                    case ActionVerb.STOP:
                        await asyncio.to_thread(
                            client.stop,
                            project=project, zone=zone, instance=instance_name,
                        )
                    case ActionVerb.RESET:
                        await asyncio.to_thread(
                            client.reset,
                            project=project, zone=zone, instance=instance_name,
                        )

            # Fetch new state
            new_info = await self.get_instance_state(instance_name, zone)

            return ActionResult(
                success=True,
                action=action.value,
                resource_id=instance_name,
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
                resource_id=instance_name,
                previous_state=current_state,
                message=f"Failed to {action.value} instance: {exc}",
            )
