"""GCP resource relationship mapping.

Maps connections between:
- GCE instances → VPC network, subnet, disks, firewall rules (via tags)
- Cloud SQL → VPC network, authorized networks
- GKE → VPC network, subnet, node pools
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from google.cloud import compute_v1
from google.cloud.container_v1 import ClusterManagerClient
from google.cloud.container_v1.types import ListClustersRequest
from googleapiclient.discovery import build

from spancloud.analysis.models import RelationshipMap, RelationshipType, ResourceRelationship
from spancloud.utils.logging import get_logger
from spancloud.providers.gcp._retry import GCP_RETRY_SLOW
from spancloud.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from spancloud.providers.gcp.auth import GCPAuth

logger = get_logger(__name__)

_GCP_LIMITER = RateLimiter(calls_per_second=8.0, max_concurrency=10)


class GCPRelationshipMapper:
    """Maps relationships between GCP resources.

    Fetches resources in bulk then cross-references locally.
    """

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    @GCP_RETRY_SLOW
    async def map_relationships(
        self, region: str | None = None
    ) -> RelationshipMap:
        """Build a complete resource relationship map.

        Args:
            region: Optional region filter.

        Returns:
            RelationshipMap with all discovered relationships.
        """
        project = self._auth.project_id
        if not project:
            return RelationshipMap(provider="gcp")

        tasks = [
            self._map_instance_relationships(project, region),
            self._map_cloudsql_relationships(project, region),
            self._map_gke_relationships(project, region),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        relationships: list[ResourceRelationship] = []
        for result in results:
            if isinstance(result, list):
                relationships.extend(result)
            elif isinstance(result, Exception):
                logger.warning("GCP relationship mapping failed: %s", result)

        return RelationshipMap(provider="gcp", relationships=relationships)

    async def _map_instance_relationships(
        self, project: str, region: str | None = None
    ) -> list[ResourceRelationship]:
        """Map GCE instance relationships: network, subnet, disks, firewall tags."""
        client = compute_v1.InstancesClient(credentials=self._auth.credentials)

        def _fetch() -> list[dict[str, Any]]:
            instances: list[dict[str, Any]] = []
            request = compute_v1.AggregatedListInstancesRequest(project=project)
            for zone_key, scoped_list in client.aggregated_list(request=request):
                for inst in scoped_list.instances or []:
                    zone_name = zone_key.split("/")[-1] if "/" in zone_key else zone_key
                    if region and not zone_name.startswith(region):
                        continue
                    instances.append({
                        "name": inst.name or str(inst.id),
                        "zone": zone_name,
                        "network_interfaces": [
                            {
                                "network": (ni.network or "").rsplit("/", 1)[-1],
                                "subnetwork": (ni.subnetwork or "").rsplit("/", 1)[-1],
                            }
                            for ni in (inst.network_interfaces or [])
                        ],
                        "disks": [
                            {
                                "source": (d.source or "").rsplit("/", 1)[-1],
                                "device_name": d.device_name or "",
                            }
                            for d in (inst.disks or [])
                        ],
                        "tags": list(inst.tags.items) if inst.tags and inst.tags.items else [],
                    })
            return instances

        async with _GCP_LIMITER:
            instances = await asyncio.to_thread(_fetch)

        rels: list[ResourceRelationship] = []
        for inst in instances:
            name = inst["name"]

            # Network + subnet
            for ni in inst["network_interfaces"]:
                if ni["network"]:
                    rels.append(ResourceRelationship(
                        source_id=name,
                        source_type="gce_instance",
                        source_name=name,
                        target_id=ni["network"],
                        target_type="vpc_network",
                        relationship=RelationshipType.IN_VPC,
                        provider="gcp",
                        region=inst["zone"],
                    ))
                if ni["subnetwork"]:
                    rels.append(ResourceRelationship(
                        source_id=name,
                        source_type="gce_instance",
                        source_name=name,
                        target_id=ni["subnetwork"],
                        target_type="subnet",
                        relationship=RelationshipType.IN_SUBNET,
                        provider="gcp",
                        region=inst["zone"],
                    ))

            # Disks
            for disk in inst["disks"]:
                if disk["source"]:
                    rels.append(ResourceRelationship(
                        source_id=name,
                        source_type="gce_instance",
                        source_name=name,
                        target_id=disk["source"],
                        target_type="persistent_disk",
                        relationship=RelationshipType.ATTACHED_TO,
                        provider="gcp",
                        region=inst["zone"],
                    ))

            # Network tags → firewall rules (tag-based security)
            for tag in inst["tags"]:
                rels.append(ResourceRelationship(
                    source_id=name,
                    source_type="gce_instance",
                    source_name=name,
                    target_id=f"tag:{tag}",
                    target_type="network_tag",
                    relationship=RelationshipType.SECURED_BY,
                    provider="gcp",
                    region=inst["zone"],
                ))

        return rels

    async def _map_cloudsql_relationships(
        self, project: str, region: str | None = None
    ) -> list[ResourceRelationship]:
        """Map Cloud SQL relationships: VPC network."""
        def _fetch() -> list[dict[str, Any]]:
            service = build(
                "sqladmin", "v1",
                credentials=self._auth.credentials,
                cache_discovery=False,
            )
            try:
                response = service.instances().list(project=project).execute()
                return response.get("items", [])
            except Exception:
                return []

        async with _GCP_LIMITER:
            instances = await asyncio.to_thread(_fetch)

        rels: list[ResourceRelationship] = []
        for inst in instances:
            name = inst.get("name", "")
            inst_region = inst.get("region", "")
            if region and inst_region != region:
                continue

            settings = inst.get("settings", {})
            ip_config = settings.get("ipConfiguration", {})
            private_network = ip_config.get("privateNetwork", "")

            if private_network:
                network_name = private_network.rsplit("/", 1)[-1]
                rels.append(ResourceRelationship(
                    source_id=name,
                    source_type="cloudsql_instance",
                    target_id=network_name,
                    target_type="vpc_network",
                    relationship=RelationshipType.IN_VPC,
                    provider="gcp",
                    region=inst_region,
                ))

        return rels

    async def _map_gke_relationships(
        self, project: str, region: str | None = None
    ) -> list[ResourceRelationship]:
        """Map GKE cluster relationships: VPC, subnet, node pools."""
        client = ClusterManagerClient(credentials=self._auth.credentials)

        def _fetch() -> list[Any]:
            parent = f"projects/{project}/locations/-"
            request = ListClustersRequest(parent=parent)
            response = client.list_clusters(request=request)
            return list(response.clusters) if response.clusters else []

        async with _GCP_LIMITER:
            clusters = await asyncio.to_thread(_fetch)

        rels: list[ResourceRelationship] = []
        for cluster in clusters:
            name = cluster.name or ""
            location = cluster.location or ""
            if region and not location.startswith(region):
                continue

            # VPC network
            network = (cluster.network or "").rsplit("/", 1)[-1]
            if network:
                rels.append(ResourceRelationship(
                    source_id=name,
                    source_type="gke_cluster",
                    source_name=name,
                    target_id=network,
                    target_type="vpc_network",
                    relationship=RelationshipType.IN_VPC,
                    provider="gcp",
                    region=location,
                ))

            # Subnet
            subnetwork = (cluster.subnetwork or "").rsplit("/", 1)[-1]
            if subnetwork:
                rels.append(ResourceRelationship(
                    source_id=name,
                    source_type="gke_cluster",
                    source_name=name,
                    target_id=subnetwork,
                    target_type="subnet",
                    relationship=RelationshipType.IN_SUBNET,
                    provider="gcp",
                    region=location,
                ))

            # Node pools
            for pool in cluster.node_pools or []:
                pool_name = pool.name or ""
                rels.append(ResourceRelationship(
                    source_id=name,
                    source_type="gke_cluster",
                    source_name=name,
                    target_id=f"{name}/{pool_name}",
                    target_type="gke_node_pool",
                    target_name=pool_name,
                    relationship=RelationshipType.MEMBER_OF,
                    provider="gcp",
                    region=location,
                ))

        return rels
