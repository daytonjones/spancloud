"""DigitalOcean resource relationship mapping."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from skyforge.analysis.models import (
    RelationshipMap,
    RelationshipType,
    ResourceRelationship,
)
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from skyforge.providers.digitalocean.auth import DigitalOceanAuth

logger = get_logger(__name__)


class DigitalOceanRelationshipMapper:
    """Maps relationships between DO resources."""

    def __init__(self, auth: DigitalOceanAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=2, base_delay=2.0)
    async def map_relationships(
        self, region: str | None = None
    ) -> RelationshipMap:
        """Build a complete DO resource relationship map."""
        tasks = [
            self._map_droplet_relationships(region),
            self._map_lb_relationships(region),
            self._map_kubernetes_relationships(region),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        relationships: list[ResourceRelationship] = []
        for result in results:
            if isinstance(result, list):
                relationships.extend(result)
            elif isinstance(result, Exception):
                logger.warning("DO relationship mapping failed: %s", result)

        return RelationshipMap(provider="digitalocean", relationships=relationships)

    async def _map_droplet_relationships(
        self, region: str | None = None
    ) -> list[ResourceRelationship]:
        """Map droplet → VPC/firewall/volume relationships."""
        droplets = await self._auth.get_paginated("/droplets", "droplets")
        volumes = await self._auth.get_paginated("/volumes", "volumes")
        firewalls = await self._auth.get_paginated("/firewalls", "firewalls")

        # Build volume lookup by attached droplet
        vols_by_droplet: dict[int, list[dict]] = {}
        for v in volumes:
            for did in v.get("droplet_ids") or []:
                vols_by_droplet.setdefault(did, []).append(v)

        # Build firewall lookup by attached droplet
        fws_by_droplet: dict[int, list[dict]] = {}
        for fw in firewalls:
            for did in fw.get("droplet_ids") or []:
                fws_by_droplet.setdefault(did, []).append(fw)

        rels: list[ResourceRelationship] = []
        for d in droplets:
            did = d.get("id")
            if not did:
                continue
            if region and (d.get("region") or {}).get("slug") != region:
                continue

            d_region = (d.get("region") or {}).get("slug", "")
            d_name = d.get("name", str(did))

            # VPC
            vpc_id = d.get("vpc_uuid", "")
            if vpc_id:
                rels.append(ResourceRelationship(
                    source_id=str(did),
                    source_type="droplet",
                    source_name=d_name,
                    target_id=vpc_id,
                    target_type="vpc",
                    relationship=RelationshipType.IN_VPC,
                    provider="digitalocean",
                    region=d_region,
                ))

            # Firewalls
            for fw in fws_by_droplet.get(did, []):
                rels.append(ResourceRelationship(
                    source_id=str(did),
                    source_type="droplet",
                    source_name=d_name,
                    target_id=fw.get("id", ""),
                    target_type="firewall",
                    target_name=fw.get("name", ""),
                    relationship=RelationshipType.SECURED_BY,
                    provider="digitalocean",
                    region=d_region,
                ))

            # Volumes
            for v in vols_by_droplet.get(did, []):
                rels.append(ResourceRelationship(
                    source_id=str(did),
                    source_type="droplet",
                    source_name=d_name,
                    target_id=v.get("id", ""),
                    target_type="volume",
                    target_name=v.get("name", ""),
                    relationship=RelationshipType.ATTACHED_TO,
                    provider="digitalocean",
                    region=d_region,
                ))

        return rels

    async def _map_lb_relationships(
        self, region: str | None = None
    ) -> list[ResourceRelationship]:
        """Map load balancer → droplet relationships."""
        lbs = await self._auth.get_paginated(
            "/load_balancers", "load_balancers"
        )

        rels: list[ResourceRelationship] = []
        for lb in lbs:
            if region and (lb.get("region") or {}).get("slug") != region:
                continue

            lb_id = lb.get("id", "")
            lb_name = lb.get("name", lb_id)
            lb_region = (lb.get("region") or {}).get("slug", "")

            for did in lb.get("droplet_ids") or []:
                rels.append(ResourceRelationship(
                    source_id=lb_id,
                    source_type="load_balancer",
                    source_name=lb_name,
                    target_id=str(did),
                    target_type="droplet",
                    relationship=RelationshipType.TARGETS,
                    provider="digitalocean",
                    region=lb_region,
                ))

        return rels

    async def _map_kubernetes_relationships(
        self, region: str | None = None
    ) -> list[ResourceRelationship]:
        """Map DOKS cluster → node pool relationships."""
        clusters = await self._auth.get_paginated(
            "/kubernetes/clusters", "kubernetes_clusters"
        )

        rels: list[ResourceRelationship] = []
        for cluster in clusters:
            if region and cluster.get("region") != region:
                continue

            cluster_id = cluster.get("id", "")
            cluster_name = cluster.get("name", cluster_id)
            cluster_region = cluster.get("region", "")

            for pool in cluster.get("node_pools") or []:
                rels.append(ResourceRelationship(
                    source_id=cluster_id,
                    source_type="doks_cluster",
                    source_name=cluster_name,
                    target_id=pool.get("id", ""),
                    target_type="doks_node_pool",
                    target_name=pool.get("name", ""),
                    relationship=RelationshipType.MEMBER_OF,
                    provider="digitalocean",
                    region=cluster_region,
                ))

        return rels
