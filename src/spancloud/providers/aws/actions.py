"""AWS resource actions — start, stop, reboot, terminate EC2 instances.

All mutating actions require explicit confirmation. Actions are rate-limited
and include pre-flight validation (instance state checks).
"""

from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff
from skyforge.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from skyforge.providers.aws.auth import AWSAuth

logger = get_logger(__name__)

_EC2_LIMITER = RateLimiter(calls_per_second=10.0, max_concurrency=5)


class ActionVerb(StrEnum):
    """Supported resource actions."""

    START = "start"
    STOP = "stop"
    REBOOT = "reboot"
    TERMINATE = "terminate"


class ActionResult(BaseModel):
    """Result of a resource action."""

    success: bool
    action: str
    resource_id: str
    resource_type: str
    provider: str
    previous_state: str = ""
    current_state: str = ""
    message: str = ""


# Valid state transitions for each action
_VALID_STATES: dict[ActionVerb, set[str]] = {
    ActionVerb.START: {"stopped"},
    ActionVerb.STOP: {"running"},
    ActionVerb.REBOOT: {"running"},
    ActionVerb.TERMINATE: {"running", "stopped"},
}


class EC2Actions:
    """Execute actions on EC2 instances.

    Pre-validates instance state before acting. All actions
    return ActionResult with before/after state.
    """

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    async def get_instance_state(
        self, instance_id: str, region: str | None = None
    ) -> dict[str, Any]:
        """Get the current state and name of an EC2 instance.

        Args:
            instance_id: EC2 instance ID.
            region: AWS region.

        Returns:
            Dict with 'state', 'name', and 'instance_type'.
        """
        ec2 = self._auth.client("ec2", region=region)

        async with _EC2_LIMITER:
            resp = await asyncio.to_thread(
                ec2.describe_instances, InstanceIds=[instance_id]
            )

        for reservation in resp.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                return {
                    "state": inst["State"]["Name"],
                    "name": tags.get("Name", instance_id),
                    "instance_type": inst.get("InstanceType", ""),
                }

        return {"state": "unknown", "name": instance_id, "instance_type": ""}

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    async def execute(
        self,
        action: ActionVerb,
        instance_id: str,
        region: str | None = None,
    ) -> ActionResult:
        """Execute an action on an EC2 instance.

        Validates the instance is in a valid state for the action before proceeding.

        Args:
            action: The action to perform.
            instance_id: EC2 instance ID.
            region: AWS region.

        Returns:
            ActionResult with outcome details.
        """
        # Pre-flight: check current state
        info = await self.get_instance_state(instance_id, region)
        current_state = info["state"]

        valid_states = _VALID_STATES.get(action, set())
        if current_state not in valid_states:
            return ActionResult(
                success=False,
                action=action.value,
                resource_id=instance_id,
                resource_type="ec2_instance",
                provider="aws",
                previous_state=current_state,
                current_state=current_state,
                message=(
                    f"Cannot {action.value} instance '{info['name']}' — "
                    f"current state is '{current_state}', "
                    f"must be one of: {', '.join(valid_states)}"
                ),
            )

        ec2 = self._auth.client("ec2", region=region)

        try:
            async with _EC2_LIMITER:
                match action:
                    case ActionVerb.START:
                        await asyncio.to_thread(
                            ec2.start_instances, InstanceIds=[instance_id]
                        )
                    case ActionVerb.STOP:
                        await asyncio.to_thread(
                            ec2.stop_instances, InstanceIds=[instance_id]
                        )
                    case ActionVerb.REBOOT:
                        await asyncio.to_thread(
                            ec2.reboot_instances, InstanceIds=[instance_id]
                        )
                    case ActionVerb.TERMINATE:
                        await asyncio.to_thread(
                            ec2.terminate_instances, InstanceIds=[instance_id]
                        )

            # Fetch new state
            new_info = await self.get_instance_state(instance_id, region)

            return ActionResult(
                success=True,
                action=action.value,
                resource_id=instance_id,
                resource_type="ec2_instance",
                provider="aws",
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
                resource_type="ec2_instance",
                provider="aws",
                previous_state=current_state,
                message=f"Failed to {action.value} instance: {exc}",
            )
