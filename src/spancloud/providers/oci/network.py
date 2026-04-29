"""OCI network — VCNs, Subnets, Security Lists, NSGs."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.providers.oci._retry import OCI_RETRY as retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.oci.auth import OCIAuth

logger = get_logger(__name__)


class NetworkResources:
    """Handles OCI VCN/Subnet/SecurityList/NSG discovery."""

    def __init__(self, auth: OCIAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=0.5)
    async def list_all(self, region: str | None = None) -> list[Resource]:
        vcns, subnets, sec_lists, nsgs = await asyncio.gather(
            asyncio.to_thread(self._sync_list_vcns, region),
            asyncio.to_thread(self._sync_list_subnets, region),
            asyncio.to_thread(self._sync_list_security_lists, region),
            asyncio.to_thread(self._sync_list_nsgs, region),
        )
        combined = vcns + subnets + sec_lists + nsgs
        logger.debug("Found %d OCI network resources", len(combined))
        return combined

    def _client(self, region: str | None) -> Any:
        import oci

        config = dict(self._auth.config)
        if region:
            config["region"] = region
        return oci.core.VirtualNetworkClient(config), config["region"]

    def _sync_list_vcns(self, region: str | None) -> list[Resource]:
        client, region_str = self._client(region)
        compartment = self._auth.compartment_id
        if not compartment:
            return []
        resources: list[Resource] = []
        page: str | None = None
        while True:
            result = client.list_vcns(compartment_id=compartment, page=page)
            for vcn in result.data or []:
                resources.append(self._map_vcn(vcn, region_str))
            page = result.next_page
            if not page:
                break
        return resources

    def _map_vcn(self, vcn: Any, region: str) -> Resource:
        cidrs = getattr(vcn, "cidr_blocks", None) or []
        return Resource(
            id=vcn.id,
            name=getattr(vcn, "display_name", "") or vcn.id,
            resource_type=ResourceType.NETWORK,
            provider="oci",
            region=region,
            state=ResourceState.RUNNING,
            tags=dict(getattr(vcn, "freeform_tags", None) or {}),
            metadata={
                "cidr_blocks": ", ".join(cidrs) if cidrs else "",
                "dns_label": getattr(vcn, "dns_label", "") or "",
                "compartment_id": getattr(vcn, "compartment_id", "") or "",
                "resource_subtype": "vcn",
            },
        )

    def _sync_list_subnets(self, region: str | None) -> list[Resource]:
        client, region_str = self._client(region)
        compartment = self._auth.compartment_id
        if not compartment:
            return []
        resources: list[Resource] = []
        page: str | None = None
        while True:
            result = client.list_subnets(compartment_id=compartment, page=page)
            for s in result.data or []:
                resources.append(self._map_subnet(s, region_str))
            page = result.next_page
            if not page:
                break
        return resources

    def _map_subnet(self, s: Any, region: str) -> Resource:
        return Resource(
            id=s.id,
            name=getattr(s, "display_name", "") or s.id,
            resource_type=ResourceType.NETWORK,
            provider="oci",
            region=region,
            state=ResourceState.RUNNING,
            tags=dict(getattr(s, "freeform_tags", None) or {}),
            metadata={
                "cidr": getattr(s, "cidr_block", "") or "",
                "vcn_id": getattr(s, "vcn_id", "") or "",
                "availability_domain": getattr(s, "availability_domain", "") or "",
                "resource_subtype": "subnet",
            },
        )

    def _sync_list_security_lists(self, region: str | None) -> list[Resource]:
        client, region_str = self._client(region)
        compartment = self._auth.compartment_id
        if not compartment:
            return []
        resources: list[Resource] = []
        page: str | None = None
        while True:
            result = client.list_security_lists(
                compartment_id=compartment, page=page
            )
            for sl in result.data or []:
                resources.append(self._map_security_list(sl, region_str))
            page = result.next_page
            if not page:
                break
        return resources

    def _map_security_list(self, sl: Any, region: str) -> Resource:
        return Resource(
            id=sl.id,
            name=getattr(sl, "display_name", "") or sl.id,
            resource_type=ResourceType.NETWORK,
            provider="oci",
            region=region,
            state=ResourceState.RUNNING,
            tags=dict(getattr(sl, "freeform_tags", None) or {}),
            metadata={
                "ingress_rule_count": str(len(getattr(sl, "ingress_security_rules", []) or [])),
                "egress_rule_count": str(len(getattr(sl, "egress_security_rules", []) or [])),
                "vcn_id": getattr(sl, "vcn_id", "") or "",
                "resource_subtype": "security_list",
            },
        )

    def _sync_list_nsgs(self, region: str | None) -> list[Resource]:
        client, region_str = self._client(region)
        compartment = self._auth.compartment_id
        if not compartment:
            return []
        resources: list[Resource] = []
        page: str | None = None
        while True:
            result = client.list_network_security_groups(
                compartment_id=compartment, page=page
            )
            for nsg in result.data or []:
                resources.append(self._map_nsg(nsg, region_str))
            page = result.next_page
            if not page:
                break
        return resources

    def _map_nsg(self, nsg: Any, region: str) -> Resource:
        return Resource(
            id=nsg.id,
            name=getattr(nsg, "display_name", "") or nsg.id,
            resource_type=ResourceType.NETWORK,
            provider="oci",
            region=region,
            state=ResourceState.RUNNING,
            tags=dict(getattr(nsg, "freeform_tags", None) or {}),
            metadata={
                "vcn_id": getattr(nsg, "vcn_id", "") or "",
                "compartment_id": getattr(nsg, "compartment_id", "") or "",
                "resource_subtype": "nsg",
            },
        )
