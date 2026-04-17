"""Tests for the Alibaba Cloud provider and resource modules."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from skyforge.core.resource import ResourceState, ResourceType


class TestAlibabaProvider:
    def test_name(self) -> None:
        from skyforge.providers.alibaba.provider import AlibabaCloudProvider

        provider = AlibabaCloudProvider()
        assert provider.name == "alibaba"

    def test_display_name(self) -> None:
        from skyforge.providers.alibaba.provider import AlibabaCloudProvider

        provider = AlibabaCloudProvider()
        assert provider.display_name == "Alibaba Cloud"

    def test_supported_resource_types(self) -> None:
        from skyforge.providers.alibaba.provider import AlibabaCloudProvider

        provider = AlibabaCloudProvider()
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


class TestAlibabaAuth:
    def test_can_create(self) -> None:
        from skyforge.providers.alibaba.auth import AlibabaAuth

        auth = AlibabaAuth()
        assert auth.access_key_id == ""
        assert auth.region == ""

    def test_set_credentials(self) -> None:
        from skyforge.providers.alibaba.auth import AlibabaAuth

        auth = AlibabaAuth()
        auth.set_credentials("LTAI5t-id", "secret-value")
        assert auth.access_key_id == "LTAI5t-id"


class TestECSResources:
    def test_map_instance(self) -> None:
        from skyforge.providers.alibaba.compute import ECSResources

        res = ECSResources(MagicMock())
        inst = SimpleNamespace(
            instance_id="i-abc",
            instance_name="web-1",
            status="Running",
            instance_type="ecs.g6.large",
            osname="Ubuntu 22.04 64-bit",
            image_id="ubuntu_22_04",
            zone_id="us-west-1a",
            vpc_attributes=SimpleNamespace(
                vpc_id="vpc-abc",
                private_ip_address=SimpleNamespace(
                    ip_address=["10.0.0.1"]
                ),
            ),
            public_ip_address=SimpleNamespace(ip_address=["1.2.3.4"]),
            tags=SimpleNamespace(
                tag=[
                    SimpleNamespace(tag_key="env", tag_value="prod"),
                ]
            ),
        )
        resource = res._map_instance(inst, "us-west-1")

        assert resource.id == "i-abc"
        assert resource.name == "web-1"
        assert resource.resource_type == ResourceType.COMPUTE
        assert resource.provider == "alibaba"
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["public_ip"] == "1.2.3.4"
        assert resource.metadata["private_ip"] == "10.0.0.1"
        assert resource.metadata["vpc_id"] == "vpc-abc"
        assert resource.metadata["resource_subtype"] == "ecs_instance"
        assert resource.tags == {"env": "prod"}


class TestDiskResources:
    def test_map_disk(self) -> None:
        from skyforge.providers.alibaba.storage import DiskResources

        res = DiskResources(MagicMock())
        d = SimpleNamespace(
            disk_id="d-abc",
            disk_name="data-disk",
            status="In_use",
            size=200,
            category="cloud_ssd",
            type="data",
            instance_id="i-abc",
            zone_id="us-west-1a",
        )
        resource = res._map_disk(d, "us-west-1")

        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["size_gb"] == "200"
        assert resource.metadata["instance_id"] == "i-abc"
        assert resource.metadata["resource_subtype"] == "ecs_disk"


class TestNetworkResources:
    def test_map_vpc(self) -> None:
        from skyforge.providers.alibaba.network import NetworkResources

        res = NetworkResources(MagicMock())
        v = SimpleNamespace(
            vpc_id="vpc-abc",
            vpc_name="prod-vpc",
            cidr_block="10.0.0.0/16",
            is_default=False,
        )
        resource = res._map_vpc(v, "us-west-1")
        assert resource.name == "prod-vpc"
        assert resource.metadata["cidr_block"] == "10.0.0.0/16"
        assert resource.metadata["resource_subtype"] == "vpc"

    def test_map_vswitch(self) -> None:
        from skyforge.providers.alibaba.network import NetworkResources

        res = NetworkResources(MagicMock())
        s = SimpleNamespace(
            v_switch_id="vsw-1",
            v_switch_name="app",
            cidr_block="10.0.1.0/24",
            vpc_id="vpc-abc",
            zone_id="us-west-1a",
        )
        resource = res._map_vswitch(s, "us-west-1")
        assert resource.metadata["cidr"] == "10.0.1.0/24"
        assert resource.metadata["resource_subtype"] == "vswitch"

    def test_map_sg(self) -> None:
        from skyforge.providers.alibaba.network import NetworkResources

        res = NetworkResources(MagicMock())
        sg = SimpleNamespace(
            security_group_id="sg-1",
            security_group_name="web",
            vpc_id="vpc-abc",
            security_group_type="normal",
        )
        resource = res._map_sg(sg, "us-west-1")
        assert resource.metadata["resource_subtype"] == "security_group"


class TestRDSResources:
    def test_map_rds(self) -> None:
        from skyforge.providers.alibaba.database import RDSResources

        res = RDSResources(MagicMock())
        inst = SimpleNamespace(
            dbinstance_id="rm-abc",
            dbinstance_description="prod-mysql",
            dbinstance_status="Running",
            engine="MySQL",
            engine_version="8.0",
            dbinstance_class="mysql.n2.medium.1",
            dbinstance_type="Primary",
            pay_type="Postpaid",
            vpc_id="vpc-abc",
        )
        resource = res._map_rds(inst, "us-west-1")
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["engine"] == "MySQL"
        assert resource.metadata["resource_subtype"] == "rds_instance"


class TestSLBResources:
    def test_map_lb(self) -> None:
        from skyforge.providers.alibaba.loadbalancer import SLBResources

        res = SLBResources(MagicMock())
        lb = SimpleNamespace(
            load_balancer_id="lb-abc",
            load_balancer_name="main-slb",
            load_balancer_status="active",
            address="1.2.3.4",
            address_type="internet",
            network_type="vpc",
            vpc_id="vpc-abc",
            v_switch_id="vsw-1",
            load_balancer_spec="slb.s1.small",
        )
        resource = res._map_lb(lb, "us-west-1")
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["resource_subtype"] == "slb"


class TestDNSResources:
    def test_map_domain(self) -> None:
        from skyforge.providers.alibaba.dns import DNSResources

        res = DNSResources(MagicMock())
        d = SimpleNamespace(
            domain_id="dns-1",
            domain_name="example.com",
            record_count=10,
            group_name="default",
            version_name="Free",
        )
        resource = res._map_domain(d)
        assert resource.name == "example.com"
        assert resource.region == "global"
        assert resource.metadata["record_count"] == "10"
        assert resource.metadata["resource_subtype"] == "dns_domain"


class TestAlibabaCostAnalyzer:
    def test_can_create(self) -> None:
        from skyforge.providers.alibaba.cost import AlibabaCostAnalyzer

        analyzer = AlibabaCostAnalyzer(MagicMock())
        assert analyzer is not None

    def test_iter_months(self) -> None:
        from datetime import date

        from skyforge.providers.alibaba.cost import _iter_months

        months = _iter_months(date(2026, 4, 10), date(2026, 6, 5))
        assert months == ["2026-04", "2026-05", "2026-06"]


class TestAlibabaSecurityAuditor:
    def test_can_create(self) -> None:
        from skyforge.providers.alibaba.security import AlibabaSecurityAuditor

        auditor = AlibabaSecurityAuditor(MagicMock())
        assert auditor is not None

    def test_port_in_range_all(self) -> None:
        from skyforge.providers.alibaba.security import _port_in_range

        assert _port_in_range("22", "-1/-1") is True
        assert _port_in_range("3389", "1/65535") is True

    def test_port_in_range_specific(self) -> None:
        from skyforge.providers.alibaba.security import _port_in_range

        assert _port_in_range("22", "22/22") is True
        assert _port_in_range("3389", "22/22") is False
        assert _port_in_range("80", "80/443") is True


class TestAlibabaUnusedDetector:
    def test_can_create(self) -> None:
        from skyforge.providers.alibaba.unused import AlibabaUnusedDetector

        detector = AlibabaUnusedDetector(MagicMock())
        assert detector is not None


class TestAlibabaRelationshipMapper:
    def test_can_create(self) -> None:
        from skyforge.providers.alibaba.relationships import (
            AlibabaRelationshipMapper,
        )

        mapper = AlibabaRelationshipMapper(MagicMock())
        assert mapper is not None


class TestAlibabaMonitoring:
    def test_can_create(self) -> None:
        from skyforge.providers.alibaba.monitoring import (
            AlibabaMonitoringAnalyzer,
        )

        analyzer = AlibabaMonitoringAnalyzer(MagicMock())
        assert analyzer is not None

    def test_map_rule(self) -> None:
        from skyforge.providers.alibaba.monitoring import (
            AlibabaMonitoringAnalyzer,
        )

        analyzer = AlibabaMonitoringAnalyzer(MagicMock())
        rule = SimpleNamespace(
            rule_id="r-1",
            rule_name="high-cpu",
            enable_state="true",
            namespace="acs_ecs_dashboard",
            metric_name="CPUUtilization",
            contact_groups="ops,oncall",
        )
        info = analyzer._map_rule(rule)
        assert info.enabled is True
        assert info.notification_channels == 2
        assert "CPUUtilization" in info.combiner


class TestAlibabaActions:
    def test_action_verb_enum(self) -> None:
        from skyforge.providers.alibaba.actions import ActionVerb

        assert ActionVerb.START == "start"
        assert ActionVerb.STOP == "stop"
        assert ActionVerb.REBOOT == "reboot"

    def test_valid_state_transitions(self) -> None:
        from skyforge.providers.alibaba.actions import _VALID_STATES, ActionVerb

        assert "Stopped" in _VALID_STATES[ActionVerb.START]
        assert "Running" in _VALID_STATES[ActionVerb.STOP]
        assert "Running" in _VALID_STATES[ActionVerb.REBOOT]
