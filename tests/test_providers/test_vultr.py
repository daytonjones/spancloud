"""Tests for the Vultr provider and resource modules."""

from __future__ import annotations

from unittest.mock import MagicMock

from skyforge.core.resource import ResourceState, ResourceType


class TestVultrProvider:
    """Tests for the VultrProvider class."""

    def test_name(self) -> None:
        from skyforge.providers.vultr.provider import VultrProvider

        provider = VultrProvider()
        assert provider.name == "vultr"

    def test_display_name(self) -> None:
        from skyforge.providers.vultr.provider import VultrProvider

        provider = VultrProvider()
        assert provider.display_name == "Vultr"

    def test_supported_resource_types(self) -> None:
        from skyforge.providers.vultr.provider import VultrProvider

        provider = VultrProvider()
        expected = [
            ResourceType.COMPUTE,
            ResourceType.STORAGE,
            ResourceType.NETWORK,
            ResourceType.DATABASE,
            ResourceType.CONTAINER,
            ResourceType.LOAD_BALANCER,
            ResourceType.DNS,
        ]
        assert provider.supported_resource_types == expected


class TestVultrAuth:
    """Tests for the Vultr auth client."""

    def test_can_create(self) -> None:
        from skyforge.providers.vultr.auth import VultrAuth

        auth = VultrAuth()
        assert auth.api_key == ""


class TestInstanceResources:
    """Tests for Vultr instance mapping."""

    def test_map_instance(self) -> None:
        from skyforge.providers.vultr.instances import InstanceResources

        auth = MagicMock()
        res = InstanceResources(auth)

        inst = {
            "id": "abc-123",
            "label": "web-1",
            "status": "active",
            "power_status": "running",
            "region": "ewr",
            "plan": "vc2-1c-1gb",
            "vcpu_count": 1,
            "ram": 1024,
            "disk": 25,
            "os": "Ubuntu 22.04",
            "main_ip": "1.2.3.4",
            "v6_main_ip": "",
            "server_status": "ok",
            "tags": ["prod"],
            "date_created": "2026-01-01T00:00:00+00:00",
        }
        resource = res._map_instance(inst)

        assert resource.id == "abc-123"
        assert resource.name == "web-1"
        assert resource.resource_type == ResourceType.COMPUTE
        assert resource.provider == "vultr"
        assert resource.region == "ewr"
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["plan"] == "vc2-1c-1gb"
        assert resource.metadata["resource_subtype"] == "instance"

    def test_map_bare_metal(self) -> None:
        from skyforge.providers.vultr.instances import BareMetalResources

        auth = MagicMock()
        res = BareMetalResources(auth)

        bm = {
            "id": "bm-456",
            "label": "metal-1",
            "status": "active",
            "region": "lax",
            "plan": "vbm-4c-32gb",
            "cpu_count": 4,
            "ram": "32768 MB",
            "disk": "2x 240GB SSD",
            "os": "Ubuntu 22.04",
            "main_ip": "5.6.7.8",
            "tags": [],
        }
        resource = res._map_bare_metal(bm)

        assert resource.name == "metal-1"
        assert resource.metadata["resource_subtype"] == "bare_metal"


class TestStorageResources:
    """Tests for Vultr storage mapping."""

    def test_map_block(self) -> None:
        from skyforge.providers.vultr.storage import BlockStorageResources

        auth = MagicMock()
        res = BlockStorageResources(auth)

        block = {
            "id": "blk-1",
            "label": "data-vol",
            "status": "active",
            "region": "ewr",
            "size_gb": 100,
            "block_type": "high_perf",
            "attached_to_instance": "abc-123",
            "cost": 10,
        }
        resource = res._map_block(block)

        assert resource.name == "data-vol"
        assert resource.resource_type == ResourceType.STORAGE
        assert resource.metadata["size_gb"] == "100"
        assert resource.metadata["resource_subtype"] == "block_storage"

    def test_map_object_storage(self) -> None:
        from skyforge.providers.vultr.storage import ObjectStorageResources

        auth = MagicMock()
        res = ObjectStorageResources(auth)

        obj = {
            "id": 123,
            "label": "my-objects",
            "status": "active",
            "region": "ewr",
            "cluster_id": 1,
            "s3_hostname": "ewr1.vultrobjects.com",
            "s3_access_key": "AKXXX",
        }
        resource = res._map_object_storage(obj)

        assert resource.name == "my-objects"
        assert resource.metadata["resource_subtype"] == "object_storage"


class TestVPCResources:
    """Tests for Vultr VPC mapping."""

    def test_map_vpc(self) -> None:
        from skyforge.providers.vultr.vpc import VPCResources

        auth = MagicMock()
        res = VPCResources(auth)

        vpc = {
            "id": "vpc-1",
            "description": "prod-vpc",
            "region": "ewr",
            "ip_block": "10.0.0.0",
            "prefix_length": 24,
        }
        resource = res._map_vpc(vpc)

        assert resource.name == "prod-vpc"
        assert resource.metadata["ip_block"] == "10.0.0.0"
        assert resource.metadata["resource_subtype"] == "vpc"

    def test_map_firewall(self) -> None:
        from skyforge.providers.vultr.vpc import FirewallResources

        auth = MagicMock()
        res = FirewallResources(auth)

        fw = {
            "id": "fw-1",
            "description": "web-fw",
            "rule_count": 5,
            "instance_count": 3,
            "max_rule_count": 50,
        }
        resource = res._map_firewall(fw)

        assert resource.name == "web-fw"
        assert resource.metadata["rule_count"] == "5"
        assert resource.metadata["resource_subtype"] == "firewall_group"


class TestDatabaseResources:
    """Tests for Vultr database mapping."""

    def test_map_database(self) -> None:
        from skyforge.providers.vultr.database import DatabaseResources

        auth = MagicMock()
        res = DatabaseResources(auth)

        db = {
            "id": "db-1",
            "label": "my-postgres",
            "status": "Running",
            "region": "ewr",
            "database_engine": "pg",
            "database_engine_version": 15,
            "plan": "vultr-dbaas-hobbyist-cc-1-25-1",
            "host": "db.vultr.com",
            "port": 5432,
            "dbname": "defaultdb",
            "tags": ["production"],
        }
        resource = res._map_database(db)

        assert resource.name == "my-postgres"
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["engine"] == "pg"
        assert resource.metadata["resource_subtype"] == "managed_database"


class TestKubernetesResources:
    """Tests for Vultr VKE mapping."""

    def test_map_cluster(self) -> None:
        from skyforge.providers.vultr.kubernetes import KubernetesResources

        auth = MagicMock()
        res = KubernetesResources(auth)

        cluster = {
            "id": "vke-1",
            "label": "prod-cluster",
            "status": "active",
            "region": "ewr",
            "version": "v1.29.0+1",
            "ip": "1.2.3.4",
            "endpoint": "https://vke.vultr.com/vke-1",
            "node_pools": [{"id": "np-1", "label": "default"}],
            "ha_controlplanes": True,
            "firewall_group_id": "fw-1",
        }
        resource = res._map_cluster(cluster)

        assert resource.name == "prod-cluster"
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["resource_subtype"] == "vke_cluster"


class TestDNSResources:
    """Tests for Vultr DNS mapping."""

    def test_map_domain(self) -> None:
        from skyforge.providers.vultr.dns import DNSResources

        auth = MagicMock()
        res = DNSResources(auth)

        domain = {
            "domain": "example.com",
            "dns_sec": "disabled",
        }
        resource = res._map_domain(domain)

        assert resource.name == "example.com"
        assert resource.metadata["resource_subtype"] == "dns_domain"

    def test_map_record(self) -> None:
        from skyforge.providers.vultr.dns import DNSResources

        auth = MagicMock()
        res = DNSResources(auth)

        record = {
            "id": "rec-1",
            "type": "A",
            "name": "www",
            "data": "1.2.3.4",
            "ttl": 300,
            "priority": 0,
        }
        resource = res._map_record(record, "example.com")

        assert resource.name == "www.example.com"
        assert resource.metadata["record_type"] == "A"
        assert resource.metadata["data"] == "1.2.3.4"


class TestVultrActions:
    """Tests for Vultr instance actions."""

    def test_action_verb_enum(self) -> None:
        from skyforge.providers.vultr.actions import ActionVerb

        assert ActionVerb.START == "start"
        assert ActionVerb.STOP == "halt"
        assert ActionVerb.REBOOT == "reboot"

    def test_valid_state_transitions(self) -> None:
        from skyforge.providers.vultr.actions import _VALID_STATES, ActionVerb

        assert "halted" in _VALID_STATES[ActionVerb.START]
        assert "active" in _VALID_STATES[ActionVerb.STOP]
        assert "active" in _VALID_STATES[ActionVerb.REBOOT]


class TestVultrCostAnalyzer:
    """Tests for Vultr cost analyzer."""

    def test_can_create(self) -> None:
        from skyforge.providers.vultr.cost import VultrCostAnalyzer

        auth = MagicMock()
        analyzer = VultrCostAnalyzer(auth)
        assert analyzer is not None

    def test_classify_service(self) -> None:
        from skyforge.providers.vultr.cost import VultrCostAnalyzer

        auth = MagicMock()
        analyzer = VultrCostAnalyzer(auth)

        assert "Compute" in analyzer._classify_service("Cloud Compute Instance")
        assert "Block Storage" in analyzer._classify_service("Block Storage 100GB")
        assert "Kubernetes" in analyzer._classify_service("VKE Cluster")
        assert analyzer._classify_service("something unknown") == "Other"


class TestVultrSecurityAuditor:
    """Tests for Vultr security auditor."""

    def test_can_create(self) -> None:
        from skyforge.providers.vultr.security import VultrSecurityAuditor

        auth = MagicMock()
        auditor = VultrSecurityAuditor(auth)
        assert auditor is not None


class TestVultrUnusedDetector:
    """Tests for Vultr unused detector."""

    def test_can_create(self) -> None:
        from skyforge.providers.vultr.unused import VultrUnusedDetector

        auth = MagicMock()
        detector = VultrUnusedDetector(auth)
        assert detector is not None

    async def test_old_snapshot_savings_in_gb_not_bytes(self) -> None:
        """Regression: Vultr /snapshots returns size in BYTES, not GB.

        Prior bug: multiplied raw bytes by $0.05/GB/mo, producing
        absurd totals like $1,342,177,280/mo for a 25 GB snapshot.
        """
        from unittest.mock import AsyncMock

        from skyforge.providers.vultr.unused import VultrUnusedDetector

        auth = MagicMock()
        # 25 GB expressed in bytes
        twenty_five_gb = 25 * 1024 ** 3
        # date_created from 200 days ago (older than the default 90-day threshold)
        auth.get_paginated = AsyncMock(
            return_value=[
                {
                    "id": "snap-1",
                    "description": "old-snap",
                    "size": twenty_five_gb,
                    "date_created": "2025-01-01T00:00:00Z",
                },
            ]
        )
        detector = VultrUnusedDetector(auth)
        results = await detector._find_old_snapshots(days_threshold=90)

        assert len(results) == 1
        savings = results[0].estimated_monthly_savings
        # 25 GB × $0.05 = $1.25/mo — sanity check the order of magnitude
        assert "1.25" in savings
        assert "$1,342,177,280" not in savings
        assert "25.00 GB" in results[0].reason


class TestVultrRelationshipMapper:
    """Tests for Vultr relationship mapper."""

    def test_can_create(self) -> None:
        from skyforge.providers.vultr.relationships import VultrRelationshipMapper

        auth = MagicMock()
        mapper = VultrRelationshipMapper(auth)
        assert mapper is not None
