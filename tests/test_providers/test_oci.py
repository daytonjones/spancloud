"""Tests for the OCI provider and resource modules."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from skyforge.core.resource import ResourceState, ResourceType


class TestOCIProvider:
    def test_name(self) -> None:
        from skyforge.providers.oci.provider import OCIProvider

        provider = OCIProvider()
        assert provider.name == "oci"

    def test_display_name(self) -> None:
        from skyforge.providers.oci.provider import OCIProvider

        provider = OCIProvider()
        assert provider.display_name == "Oracle Cloud (OCI)"

    def test_supported_resource_types(self) -> None:
        from skyforge.providers.oci.provider import OCIProvider

        provider = OCIProvider()
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


class TestOCIAuth:
    def test_can_create(self) -> None:
        from skyforge.providers.oci.auth import OCIAuth

        auth = OCIAuth()
        assert auth.profile == ""
        assert auth.region == ""

    def test_set_profile(self) -> None:
        from skyforge.providers.oci.auth import OCIAuth

        auth = OCIAuth()
        auth.set_profile("PROD")
        assert auth.profile == "PROD"


class TestInstanceResources:
    def test_map_instance(self) -> None:
        from skyforge.providers.oci.compute import InstanceResources

        res = InstanceResources(MagicMock())

        inst = SimpleNamespace(
            id="ocid1.instance.oc1..abc",
            display_name="web-1",
            shape="VM.Standard.E4.Flex",
            availability_domain="AD-1",
            compartment_id="ocid1.compartment.oc1..xyz",
            fault_domain="FD-1",
            image_id="ocid1.image.oc1..img",
            shape_config=SimpleNamespace(ocpus=2, memory_in_gbs=16),
            freeform_tags={"env": "prod"},
            time_created=None,
            lifecycle_state="RUNNING",
        )
        resource = res._map_instance(inst, "us-ashburn-1")

        assert resource.id == "ocid1.instance.oc1..abc"
        assert resource.name == "web-1"
        assert resource.resource_type == ResourceType.COMPUTE
        assert resource.provider == "oci"
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["shape"] == "VM.Standard.E4.Flex"
        assert resource.metadata["ocpus"] == "2"
        assert resource.metadata["resource_subtype"] == "compute_instance"


class TestObjectStorageResources:
    def test_map_bucket(self) -> None:
        from skyforge.providers.oci.storage import ObjectStorageResources

        res = ObjectStorageResources(MagicMock())
        b = SimpleNamespace(
            name="data-bucket",
            compartment_id="ocid1.compartment..xyz",
            etag="abc",
            freeform_tags={},
            time_created=None,
        )
        resource = res._map_bucket(b, "myns", "us-ashburn-1")
        assert resource.name == "data-bucket"
        assert resource.resource_type == ResourceType.STORAGE
        assert resource.metadata["namespace"] == "myns"
        assert resource.metadata["resource_subtype"] == "object_storage_bucket"


class TestBlockVolumeResources:
    def test_map_volume_available(self) -> None:
        from skyforge.providers.oci.storage import BlockVolumeResources

        res = BlockVolumeResources(MagicMock())
        v = SimpleNamespace(
            id="ocid1.volume..v1",
            display_name="data-vol",
            size_in_gbs=100,
            vpus_per_gb=10,
            availability_domain="AD-1",
            compartment_id="ocid1.compartment..xyz",
            freeform_tags={},
            time_created=None,
            lifecycle_state="AVAILABLE",
        )
        resource = res._map_volume(v, "us-ashburn-1")
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["size_gb"] == "100"
        assert resource.metadata["resource_subtype"] == "block_volume"


class TestNetworkResources:
    def test_map_vcn(self) -> None:
        from skyforge.providers.oci.network import NetworkResources

        res = NetworkResources(MagicMock())
        vcn = SimpleNamespace(
            id="ocid1.vcn..v1",
            display_name="prod-vcn",
            cidr_blocks=["10.0.0.0/16"],
            dns_label="prod",
            compartment_id="ocid1.compartment..xyz",
            freeform_tags={},
        )
        resource = res._map_vcn(vcn, "us-ashburn-1")
        assert resource.name == "prod-vcn"
        assert resource.metadata["cidr_blocks"] == "10.0.0.0/16"
        assert resource.metadata["resource_subtype"] == "vcn"


class TestDatabaseResources:
    def test_map_adb(self) -> None:
        from skyforge.providers.oci.database import DatabaseResources

        res = DatabaseResources(MagicMock())
        adb = SimpleNamespace(
            id="ocid1.autonomousdb..a1",
            display_name="my-adb",
            db_name="MYADB",
            db_workload="OLTP",
            cpu_core_count=1,
            data_storage_size_in_tbs=1,
            is_free_tier=True,
            compartment_id="ocid1.compartment..xyz",
            freeform_tags={},
            time_created=None,
            lifecycle_state="AVAILABLE",
        )
        resource = res._map_adb(adb, "us-ashburn-1")
        assert resource.name == "my-adb"
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["resource_subtype"] == "autonomous_database"


class TestOKEResources:
    def test_map_cluster(self) -> None:
        from skyforge.providers.oci.container import OKEResources

        res = OKEResources(MagicMock())
        c = SimpleNamespace(
            id="ocid1.cluster..c1",
            name="prod-oke",
            kubernetes_version="v1.29.1",
            vcn_id="ocid1.vcn..v1",
            endpoints="https://cluster.io",
            compartment_id="ocid1.compartment..xyz",
            freeform_tags={},
            lifecycle_state="ACTIVE",
        )
        resource = res._map_cluster(c, "us-ashburn-1")
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["resource_subtype"] == "oke_cluster"


class TestLoadBalancerResources:
    def test_map_lb(self) -> None:
        from skyforge.providers.oci.loadbalancer import LoadBalancerResources

        res = LoadBalancerResources(MagicMock())
        lb = SimpleNamespace(
            id="ocid1.lb..l1",
            display_name="main-lb",
            shape_name="flexible",
            is_private=False,
            backend_sets={"b1": {}, "b2": {}},
            listeners={"l1": {}},
            compartment_id="ocid1.compartment..xyz",
            freeform_tags={},
            lifecycle_state="ACTIVE",
        )
        resource = res._map_lb(lb, "us-ashburn-1", "load_balancer")
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["backend_set_count"] == "2"
        assert resource.metadata["resource_subtype"] == "load_balancer"


class TestDNSResources:
    def test_map_zone(self) -> None:
        from skyforge.providers.oci.dns import DNSResources

        res = DNSResources(MagicMock())
        z = SimpleNamespace(
            id="ocid1.dns-zone..z1",
            name="example.com",
            zone_type="PRIMARY",
            view_id="ocid1.view..v",
            version="1",
            freeform_tags={},
            time_created=None,
        )
        resource = res._map_zone(z, "us-ashburn-1")
        assert resource.name == "example.com"
        assert resource.resource_type == ResourceType.DNS
        assert resource.metadata["resource_subtype"] == "dns_zone"


class TestOCICostAnalyzer:
    def test_can_create(self) -> None:
        from skyforge.providers.oci.cost import OCICostAnalyzer

        analyzer = OCICostAnalyzer(MagicMock())
        assert analyzer is not None


class TestOCISecurityAuditor:
    def test_can_create(self) -> None:
        from skyforge.providers.oci.security import OCISecurityAuditor

        auditor = OCISecurityAuditor(MagicMock())
        assert auditor is not None


class TestOCIUnusedDetector:
    def test_can_create(self) -> None:
        from skyforge.providers.oci.unused import OCIUnusedDetector

        detector = OCIUnusedDetector(MagicMock())
        assert detector is not None


class TestOCIRelationshipMapper:
    def test_can_create(self) -> None:
        from skyforge.providers.oci.relationships import OCIRelationshipMapper

        mapper = OCIRelationshipMapper(MagicMock())
        assert mapper is not None


class TestOCIMonitoring:
    def test_can_create(self) -> None:
        from skyforge.providers.oci.monitoring import OCIMonitoringAnalyzer

        analyzer = OCIMonitoringAnalyzer(MagicMock())
        assert analyzer is not None

    def test_map_alarm(self) -> None:
        from skyforge.providers.oci.monitoring import OCIMonitoringAnalyzer

        analyzer = OCIMonitoringAnalyzer(MagicMock())
        alarm = SimpleNamespace(
            id="ocid1.alarm..a1",
            display_name="high-cpu",
            severity="CRITICAL",
            namespace="oci_computeagent",
            destinations=["ocid1.topic..t1"],
            is_enabled=True,
        )
        info = analyzer._map_alarm(alarm)
        assert info.enabled is True
        assert info.notification_channels == 1
        assert "CRITICAL" in info.combiner


class TestOCIActions:
    def test_action_verb_enum(self) -> None:
        from skyforge.providers.oci.actions import ActionVerb

        assert ActionVerb.START == "START"
        assert ActionVerb.STOP == "STOP"
        assert ActionVerb.SOFTRESET == "SOFTRESET"

    def test_valid_state_transitions(self) -> None:
        from skyforge.providers.oci.actions import _VALID_STATES, ActionVerb

        assert "STOPPED" in _VALID_STATES[ActionVerb.START]
        assert "RUNNING" in _VALID_STATES[ActionVerb.STOP]
        assert "RUNNING" in _VALID_STATES[ActionVerb.SOFTRESET]
