"""Alibaba ECS instance lifecycle actions."""

from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel

from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.alibaba.auth import AlibabaAuth

logger = get_logger(__name__)


class ActionVerb(StrEnum):
    """Supported Alibaba ECS actions."""

    START = "start"
    STOP = "stop"
    REBOOT = "reboot"


class ActionResult(BaseModel):
    success: bool
    action: str
    resource_id: str
    resource_type: str = "ecs_instance"
    provider: str = "alibaba"
    previous_state: str = ""
    current_state: str = ""
    message: str = ""


_VALID_STATES: dict[ActionVerb, set[str]] = {
    ActionVerb.START: {"Stopped"},
    ActionVerb.STOP: {"Running"},
    ActionVerb.REBOOT: {"Running"},
}


class ECSActions:
    """Execute lifecycle actions on Alibaba ECS instances."""

    def __init__(self, auth: AlibabaAuth) -> None:
        self._auth = auth

    async def get_instance_state(
        self, instance_id: str, region: str | None = None
    ) -> dict[str, str]:
        return await asyncio.to_thread(
            self._sync_get_state, instance_id, region
        )

    def _sync_get_state(
        self, instance_id: str, region: str | None
    ) -> dict[str, str]:
        from alibabacloud_ecs20140526 import models as ecs_models
        from alibabacloud_ecs20140526.client import Client as EcsClient

        region_id = region or self._auth.region
        client = EcsClient(self._auth.ecs_config(region_id))
        response = client.describe_instances(
            ecs_models.DescribeInstancesRequest(
                region_id=region_id,
                instance_ids=f'["{instance_id}"]',
            )
        )
        body = response.body
        holder = getattr(body, "instances", None)
        inst_list = getattr(holder, "instance", []) or [] if holder else []
        if not inst_list:
            return {"state": "Unknown", "name": instance_id, "instance_type": ""}
        inst = inst_list[0]
        return {
            "state": str(getattr(inst, "status", "") or ""),
            "name": getattr(inst, "instance_name", "") or instance_id,
            "instance_type": getattr(inst, "instance_type", "") or "",
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
        from alibabacloud_ecs20140526 import models as ecs_models
        from alibabacloud_ecs20140526.client import Client as EcsClient

        region_id = region or self._auth.region
        client = EcsClient(self._auth.ecs_config(region_id))

        if action == ActionVerb.START:
            client.start_instance(
                ecs_models.StartInstanceRequest(instance_id=instance_id)
            )
        elif action == ActionVerb.STOP:
            client.stop_instance(
                ecs_models.StopInstanceRequest(instance_id=instance_id)
            )
        elif action == ActionVerb.REBOOT:
            client.reboot_instance(
                ecs_models.RebootInstanceRequest(instance_id=instance_id)
            )
