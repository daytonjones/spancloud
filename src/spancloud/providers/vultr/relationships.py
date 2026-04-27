"""Vultr resource relationship mapping.

Maps connections between:
- Instances → VPCs, firewall groups, block storage
- Load balancers → instances
- Kubernetes clusters → node pools
- Databases → VPCs
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from spancloud.analysis.models import RelationshipMap, RelationshipType, ResourceRelationship
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.vultr.auth import VultrAuth

logger = get_logger(__name__)


class VultrRelationshipMapper:
    """Maps relationships between Vultr resources."""

    def __init__(self, auth: VultrAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def map_relationships(
        self, region: str | None = None
    ) -> RelationshipMap:
        """Build a complete resource relationship map.

        Args:
            region: Optional region filter.

        Returns:
            RelationshipMap with all discovered relationships.
        """
        tasks = [
            self._map_instance_relationships(region),
            self._map_lb_relationships(region),
            self._map_kubernetes_relationships(region),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        relationships: list[ResourceRelationship] = []
        for result in results:
            if isinstance(result, list):
                relationships.extend(result)
            elif isinstance(result, Exception):
                logger.warning("Vultr relationship mapping failed: %s", result)

        return RelationshipMap(provider="vultr", relationships=relationships)

    async def _map_instance_relationships(
        self, region: str | None = None
    ) -> list[ResourceRelationship]:
        """Map instance → VPC, firewall, block storage relationships."""
        instances = await self._auth.get_paginated("/instances", "instances")

        block_by_instance: dict[str, list[dict]] = {}
        try:
            blocks = await self._auth.get_paginated("/blocks", "blocks")
            for block in blocks:
                attached = block.get("attached_to_instance", "")
                if attached:
                    block_by_instance.setdefault(attached, []).append(block)
        except Exception as exc:
            logger.debug("Block storage fetch failed, skipping block relationships: %s", exc)

        import ipaddress

        rels: list[ResourceRelationship] = []

        # VPC 1.0 — match instances to networks by subnet (internal_ip field on instance)
        try:
            vpcs1 = await self._auth.get_paginated("/vpcs", "vpcs")
            vpc1_subnets: list[tuple[dict, ipaddress.IPv4Network]] = []
            for vpc in vpcs1:
                subnet = vpc.get("v4_subnet", "")
                mask = vpc.get("v4_subnet_mask", 0)
                if subnet and mask:
                    try:
                        net = ipaddress.IPv4Network(f"{subnet}/{mask}", strict=False)
                        vpc1_subnets.append((vpc, net))
                    except Exception:
                        pass
            for inst in instances:
                if region and inst.get("region") != region:
                    continue
                internal_ip = inst.get("internal_ip", "")
                if not internal_ip:
                    continue
                try:
                    ip = ipaddress.IPv4Address(internal_ip)
                except Exception:
                    continue
                for vpc, net in vpc1_subnets:
                    if region and vpc.get("region") != region:
                        continue
                    if ip in net:
                        rels.append(ResourceRelationship(
                            source_id=inst.get("id", ""),
                            source_type="instance",
                            source_name=inst.get("label", inst.get("id", "")),
                            target_id=vpc.get("id", ""),
                            target_type="vpc",
                            relationship=RelationshipType.IN_VPC,
                            provider="vultr",
                            region=inst.get("region", ""),
                        ))
        except Exception as exc:
            logger.debug("VPC 1.0 relationship mapping failed: %s", exc)

        for inst in instances:
            if region and inst.get("region") != region:
                continue

            inst_id = inst.get("id", "")
            label = inst.get("label", inst_id)

            # VPC 2.0 — instance carries vpc2_ids list directly
            vpc2_ids = list(inst.get("vpc2_ids") or [])
            if not vpc2_ids and inst.get("vpc2_id"):
                vpc2_ids = [inst["vpc2_id"]]
            for vpc_id in vpc2_ids:
                if not vpc_id:
                    continue
                rels.append(ResourceRelationship(
                    source_id=inst_id,
                    source_type="instance",
                    source_name=label,
                    target_id=vpc_id,
                    target_type="vpc",
                    relationship=RelationshipType.IN_VPC,
                    provider="vultr",
                    region=inst.get("region", ""),
                ))

            # Firewall group
            fw_id = inst.get("firewall_group_id", "")
            if fw_id:
                rels.append(ResourceRelationship(
                    source_id=inst_id,
                    source_type="instance",
                    source_name=label,
                    target_id=fw_id,
                    target_type="firewall_group",
                    relationship=RelationshipType.SECURED_BY,
                    provider="vultr",
                    region=inst.get("region", ""),
                ))

            # Block storage
            for block in block_by_instance.get(inst_id, []):
                rels.append(ResourceRelationship(
                    source_id=inst_id,
                    source_type="instance",
                    source_name=label,
                    target_id=block.get("id", ""),
                    target_type="block_storage",
                    target_name=block.get("label", ""),
                    relationship=RelationshipType.ATTACHED_TO,
                    provider="vultr",
                    region=inst.get("region", ""),
                ))

        return rels

    async def _map_lb_relationships(
        self, region: str | None = None
    ) -> list[ResourceRelationship]:
        """Map load balancer → instance relationships."""
        lbs = await self._auth.get_paginated("/load-balancers", "load_balancers")

        rels: list[ResourceRelationship] = []
        for lb in lbs:
            if region and lb.get("region") != region:
                continue

            lb_id = lb.get("id", "")
            lb_label = lb.get("label", lb_id)

            # VPC
            vpc_id = lb.get("vpc", "")
            if vpc_id:
                rels.append(ResourceRelationship(
                    source_id=lb_id,
                    source_type="load_balancer",
                    source_name=lb_label,
                    target_id=vpc_id,
                    target_type="vpc",
                    relationship=RelationshipType.IN_VPC,
                    provider="vultr",
                    region=lb.get("region", ""),
                ))

            # Target instances
            for inst_id in lb.get("instances", []):
                rels.append(ResourceRelationship(
                    source_id=lb_id,
                    source_type="load_balancer",
                    source_name=lb_label,
                    target_id=inst_id,
                    target_type="instance",
                    relationship=RelationshipType.TARGETS,
                    provider="vultr",
                    region=lb.get("region", ""),
                ))

            # Firewall rules (via firewall_rules if present)
            fw_id = lb.get("firewall_group_id", "")
            if fw_id:
                rels.append(ResourceRelationship(
                    source_id=lb_id,
                    source_type="load_balancer",
                    source_name=lb_label,
                    target_id=fw_id,
                    target_type="firewall_group",
                    relationship=RelationshipType.SECURED_BY,
                    provider="vultr",
                    region=lb.get("region", ""),
                ))

        return rels

    async def _map_kubernetes_relationships(
        self, region: str | None = None
    ) -> list[ResourceRelationship]:
        """Map VKE cluster → node pool relationships."""
        clusters = await self._auth.get_paginated(
            "/kubernetes/clusters", "vke_clusters"
        )

        rels: list[ResourceRelationship] = []
        for cluster in clusters:
            if region and cluster.get("region") != region:
                continue

            cluster_id = cluster.get("id", "")
            label = cluster.get("label", cluster_id)

            for pool in cluster.get("node_pools", []):
                pool_id = pool.get("id", "")
                pool_label = pool.get("label", pool_id)

                rels.append(ResourceRelationship(
                    source_id=cluster_id,
                    source_type="vke_cluster",
                    source_name=label,
                    target_id=pool_id,
                    target_type="vke_node_pool",
                    target_name=pool_label,
                    relationship=RelationshipType.MEMBER_OF,
                    provider="vultr",
                    region=cluster.get("region", ""),
                ))

            # Firewall group
            fw_id = cluster.get("firewall_group_id", "")
            if fw_id:
                rels.append(ResourceRelationship(
                    source_id=cluster_id,
                    source_type="vke_cluster",
                    source_name=label,
                    target_id=fw_id,
                    target_type="firewall_group",
                    relationship=RelationshipType.SECURED_BY,
                    provider="vultr",
                    region=cluster.get("region", ""),
                ))

        return rels
