"""OCI Load Balancer discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.providers.oci._retry import OCI_RETRY, OCI_RETRY_SLOW

if TYPE_CHECKING:
    from spancloud.providers.oci.auth import OCIAuth

logger = get_logger(__name__)


class LoadBalancerResources:
    """Handles OCI Load Balancer + Network Load Balancer discovery."""

    def __init__(self, auth: OCIAuth) -> None:
        self._auth = auth

    @OCI_RETRY
    async def list_load_balancers(
        self, region: str | None = None
    ) -> list[Resource]:
        flb, nlb = await asyncio.gather(
            asyncio.to_thread(self._sync_list_flex, region),
            asyncio.to_thread(self._sync_list_network, region),
        )
        combined = flb + nlb
        logger.debug("Found %d OCI load balancers", len(combined))
        return combined

    def _sync_list_flex(self, region: str | None) -> list[Resource]:
        import oci

        config = dict(self._auth.config)
        if region:
            config["region"] = region
        compartment = self._auth.compartment_id
        if not compartment:
            return []

        client = oci.load_balancer.LoadBalancerClient(config)
        resources: list[Resource] = []
        page: str | None = None
        while True:
            result = client.list_load_balancers(
                compartment_id=compartment, page=page
            )
            for lb in result.data or []:
                resources.append(self._map_lb(lb, config["region"], "load_balancer"))
            page = result.next_page
            if not page:
                break
        return resources

    def _sync_list_network(self, region: str | None) -> list[Resource]:
        import oci

        config = dict(self._auth.config)
        if region:
            config["region"] = region
        compartment = self._auth.compartment_id
        if not compartment:
            return []

        resources: list[Resource] = []
        try:
            client = oci.network_load_balancer.NetworkLoadBalancerClient(config)
        except Exception as exc:
            logger.debug("NLB client unavailable: %s", exc)
            return []

        page: str | None = None
        while True:
            try:
                result = client.list_network_load_balancers(
                    compartment_id=compartment, page=page
                )
            except Exception as exc:
                logger.debug("list_network_load_balancers failed: %s", exc)
                break
            for lb in getattr(result.data, "items", []) or []:
                resources.append(
                    self._map_lb(lb, config["region"], "network_load_balancer")
                )
            page = result.next_page
            if not page:
                break
        return resources

    def _map_lb(self, lb: Any, region: str, subtype: str) -> Resource:
        lifecycle = str(getattr(lb, "lifecycle_state", "") or "")
        state = (
            ResourceState.RUNNING
            if lifecycle == "ACTIVE"
            else ResourceState.PENDING
            if lifecycle in ("CREATING", "UPDATING")
            else ResourceState.UNKNOWN
        )

        backends = getattr(lb, "backend_sets", None) or {}
        listeners = getattr(lb, "listeners", None) or {}

        return Resource(
            id=lb.id,
            name=getattr(lb, "display_name", "") or lb.id,
            resource_type=ResourceType.LOAD_BALANCER,
            provider="oci",
            region=region,
            state=state,
            tags=dict(getattr(lb, "freeform_tags", None) or {}),
            metadata={
                "shape_name": getattr(lb, "shape_name", "") or "",
                "is_private": str(getattr(lb, "is_private", "") or ""),
                "backend_set_count": str(len(backends)),
                "listener_count": str(len(listeners)),
                "compartment_id": getattr(lb, "compartment_id", "") or "",
                "resource_subtype": subtype,
            },
        )
