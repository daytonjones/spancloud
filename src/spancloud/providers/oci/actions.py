"""OCI compute instance lifecycle actions."""

from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.oci.auth import OCIAuth

logger = get_logger(__name__)


class ActionVerb(StrEnum):
    """Supported OCI instance actions."""

    START = "START"
    STOP = "STOP"
    RESET = "RESET"
    SOFTRESET = "SOFTRESET"
    SOFTSTOP = "SOFTSTOP"


class ActionResult(BaseModel):
    success: bool
    action: str
    resource_id: str
    resource_type: str = "compute_instance"
    provider: str = "oci"
    previous_state: str = ""
    current_state: str = ""
    message: str = ""


_VALID_STATES: dict[ActionVerb, set[str]] = {
    ActionVerb.START: {"STOPPED"},
    ActionVerb.STOP: {"RUNNING"},
    ActionVerb.SOFTSTOP: {"RUNNING"},
    ActionVerb.RESET: {"RUNNING", "STOPPED"},
    ActionVerb.SOFTRESET: {"RUNNING"},
}


class InstanceActions:
    """Execute lifecycle actions on OCI compute instances."""

    def __init__(self, auth: OCIAuth) -> None:
        self._auth = auth

    async def get_instance_state(
        self, instance_id: str, region: str | None = None
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._sync_get_state, instance_id, region
        )

    def _sync_get_state(
        self, instance_id: str, region: str | None
    ) -> dict[str, Any]:
        import oci

        config = dict(self._auth.config)
        if region:
            config["region"] = region
        client = oci.core.ComputeClient(config)
        inst = client.get_instance(instance_id).data
        return {
            "state": str(inst.lifecycle_state),
            "name": getattr(inst, "display_name", "") or instance_id,
            "shape": getattr(inst, "shape", "") or "",
        }

    @retry_with_backoff(max_retries=2, base_delay=1.0)
    async def execute(
        self,
        action: ActionVerb,
        instance_id: str,
        region: str | None = None,
    ) -> ActionResult:
        info = await self.get_instance_state(instance_id, region)
        current_state = info["state"]

        valid = _VALID_STATES.get(action, set())
        if current_state not in valid:
            return ActionResult(
                success=False,
                action=action.value,
                resource_id=instance_id,
                previous_state=current_state,
                current_state=current_state,
                message=(
                    f"Cannot {action.value} '{info['name']}' — "
                    f"current state is '{current_state}', "
                    f"must be one of: {', '.join(valid)}"
                ),
            )

        try:
            await asyncio.to_thread(
                self._sync_execute, action, instance_id, region
            )
            new_info = await self.get_instance_state(instance_id, region)
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

    def _sync_execute(
        self, action: ActionVerb, instance_id: str, region: str | None
    ) -> None:
        import oci

        config = dict(self._auth.config)
        if region:
            config["region"] = region
        client = oci.core.ComputeClient(config)
        client.instance_action(instance_id, action.value)
