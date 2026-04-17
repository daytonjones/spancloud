"""OCI relationship mapper — instance → subnet/VCN, LB → backends."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from skyforge.analysis.models import (
    RelationshipMap,
    RelationshipType,
    ResourceRelationship,
)
from skyforge.utils.logging import get_logger

if TYPE_CHECKING:
    from skyforge.providers.oci.auth import OCIAuth

logger = get_logger(__name__)


class OCIRelationshipMapper:
    """Builds a relationship graph for OCI resources."""

    def __init__(self, auth: OCIAuth) -> None:
        self._auth = auth

    async def map_relationships(
        self, region: str | None = None
    ) -> RelationshipMap:
        _ = region
        results = await asyncio.gather(
            asyncio.to_thread(self._instance_to_network),
            asyncio.to_thread(self._volume_to_instance),
        )
        rels: list[ResourceRelationship] = []
        for group in results:
            rels.extend(group)
        return RelationshipMap(provider="oci", relationships=rels)

    def _instance_to_network(self) -> list[ResourceRelationship]:
        import oci

        rels: list[ResourceRelationship] = []
        compartment = self._auth.compartment_id
        if not compartment:
            return rels

        try:
            compute = oci.core.ComputeClient(self._auth.config)
            vcn_client = oci.core.VirtualNetworkClient(self._auth.config)

            instances: list = []
            page: str | None = None
            while True:
                r = compute.list_instances(
                    compartment_id=compartment, page=page
                )
                instances.extend(r.data or [])
                page = r.next_page
                if not page:
                    break

            for inst in instances:
                vnics = compute.list_vnic_attachments(
                    compartment_id=compartment, instance_id=inst.id
                ).data or []
                for attach in vnics:
                    try:
                        vnic = vcn_client.get_vnic(attach.vnic_id).data
                    except Exception:
                        continue
                    if not vnic.subnet_id:
                        continue
                    rels.append(
                        ResourceRelationship(
                            source_id=inst.id,
                            source_type="compute_instance",
                            source_name=getattr(inst, "display_name", "") or inst.id,
                            target_id=vnic.subnet_id,
                            target_type="subnet",
                            target_name=vnic.subnet_id.rsplit(".", 1)[-1],
                            relationship=RelationshipType.IN_SUBNET,
                            provider="oci",
                            region=self._auth.region or "",
                        )
                    )
                    for nsg_id in (getattr(vnic, "nsg_ids", None) or []):
                        rels.append(
                            ResourceRelationship(
                                source_id=inst.id,
                                source_type="compute_instance",
                                source_name=getattr(inst, "display_name", "") or inst.id,
                                target_id=nsg_id,
                                target_type="nsg",
                                target_name=nsg_id.rsplit(".", 1)[-1],
                                relationship=RelationshipType.SECURED_BY,
                                provider="oci",
                                region=self._auth.region or "",
                            )
                        )
        except Exception as exc:
            logger.debug("Instance relationship scan skipped: %s", exc)
        return rels

    def _volume_to_instance(self) -> list[ResourceRelationship]:
        import oci

        rels: list[ResourceRelationship] = []
        compartment = self._auth.compartment_id
        if not compartment:
            return rels

        try:
            compute = oci.core.ComputeClient(self._auth.config)
            page: str | None = None
            while True:
                att = compute.list_volume_attachments(
                    compartment_id=compartment, page=page
                )
                for a in att.data or []:
                    if str(getattr(a, "lifecycle_state", "")) != "ATTACHED":
                        continue
                    rels.append(
                        ResourceRelationship(
                            source_id=getattr(a, "volume_id", "") or "",
                            source_type="block_volume",
                            source_name=(
                                (getattr(a, "volume_id", "") or "").rsplit(".", 1)[-1]
                            ),
                            target_id=getattr(a, "instance_id", "") or "",
                            target_type="compute_instance",
                            target_name=(
                                (getattr(a, "instance_id", "") or "").rsplit(".", 1)[-1]
                            ),
                            relationship=RelationshipType.ATTACHED_TO,
                            provider="oci",
                            region=self._auth.region or "",
                        )
                    )
                page = att.next_page
                if not page:
                    break
        except Exception as exc:
            logger.debug("Volume attachment scan skipped: %s", exc)
        return rels
