"""Tests for the DigitalOcean provider and resource modules."""

from __future__ import annotations

from unittest.mock import MagicMock

from skyforge.core.resource import ResourceState, ResourceType


class TestDigitalOceanProvider:
    """Tests for the DigitalOceanProvider class."""

    def test_name(self) -> None:
        from skyforge.providers.digitalocean.provider import DigitalOceanProvider

        provider = DigitalOceanProvider()
        assert provider.name == "digitalocean"

    def test_display_name(self) -> None:
        from skyforge.providers.digitalocean.provider import DigitalOceanProvider

        provider = DigitalOceanProvider()
        assert provider.display_name == "Digital Ocean"

    def test_supported_resource_types(self) -> None:
        from skyforge.providers.digitalocean.provider import DigitalOceanProvider

        provider = DigitalOceanProvider()
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


class TestDigitalOceanAuth:
    def test_can_create(self) -> None:
        from skyforge.providers.digitalocean.auth import DigitalOceanAuth

        auth = DigitalOceanAuth()
        assert auth.token == ""


class TestDropletResources:
    def test_map_droplet(self) -> None:
        from skyforge.providers.digitalocean.droplets import DropletResources

        auth = MagicMock()
        res = DropletResources(auth)

        d = {
            "id": 12345,
            "name": "web-1",
            "status": "active",
            "region": {"slug": "nyc3", "name": "New York 3"},
            "image": {"slug": "ubuntu-22-04-x64", "distribution": "Ubuntu"},
            "size": {
                "slug": "s-1vcpu-1gb", "price_monthly": 6, "price_hourly": 0.00893,
            },
            "vcpus": 1,
            "memory": 1024,
            "disk": 25,
            "networks": {
                "v4": [
                    {"type": "public", "ip_address": "1.2.3.4"},
                    {"type": "private", "ip_address": "10.0.0.5"},
                ],
            },
            "tags": ["prod"],
            "created_at": "2026-01-01T00:00:00Z",
        }
        resource = res._map_droplet(d)

        assert resource.id == "12345"
        assert resource.name == "web-1"
        assert resource.resource_type == ResourceType.COMPUTE
        assert resource.provider == "digitalocean"
        assert resource.region == "nyc3"
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["size"] == "s-1vcpu-1gb"
        assert resource.metadata["public_ip"] == "1.2.3.4"
        assert resource.metadata["private_ip"] == "10.0.0.5"
        assert resource.metadata["resource_subtype"] == "droplet"


class TestVolumeResources:
    def test_map_volume(self) -> None:
        from skyforge.providers.digitalocean.storage import VolumeResources

        auth = MagicMock()
        res = VolumeResources(auth)

        v = {
            "id": "vol-abc",
            "name": "data-vol",
            "region": {"slug": "nyc3"},
            "size_gigabytes": 100,
            "filesystem_type": "ext4",
            "droplet_ids": [12345],
            "created_at": "2026-01-01T00:00:00Z",
        }
        resource = res._map_volume(v)

        assert resource.name == "data-vol"
        assert resource.resource_type == ResourceType.STORAGE
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["size_gb"] == "100"
        assert resource.metadata["resource_subtype"] == "volume"

    def test_map_volume_unattached(self) -> None:
        from skyforge.providers.digitalocean.storage import VolumeResources

        auth = MagicMock()
        res = VolumeResources(auth)

        v = {
            "id": "vol-xyz",
            "name": "unused",
            "region": {"slug": "sfo3"},
            "size_gigabytes": 50,
            "droplet_ids": [],
        }
        resource = res._map_volume(v)
        assert resource.state == ResourceState.STOPPED


class TestVPCResources:
    def test_map_vpc(self) -> None:
        from skyforge.providers.digitalocean.vpc import VPCResources

        auth = MagicMock()
        res = VPCResources(auth)

        vpc = {
            "id": "vpc-1",
            "name": "prod-vpc",
            "region": "nyc3",
            "ip_range": "10.0.0.0/16",
            "default": False,
            "description": "Production VPC",
        }
        resource = res._map_vpc(vpc)

        assert resource.name == "prod-vpc"
        assert resource.metadata["ip_range"] == "10.0.0.0/16"
        assert resource.metadata["resource_subtype"] == "vpc"

    def test_map_firewall(self) -> None:
        from skyforge.providers.digitalocean.vpc import FirewallResources

        auth = MagicMock()
        res = FirewallResources(auth)

        fw = {
            "id": "fw-1",
            "name": "web-fw",
            "status": "succeeded",
            "inbound_rules": [{"protocol": "tcp", "ports": "80"}],
            "outbound_rules": [],
            "droplet_ids": [1, 2, 3],
        }
        resource = res._map_firewall(fw)
        assert resource.name == "web-fw"
        assert resource.metadata["inbound_rules"] == "1"
        assert resource.metadata["droplet_count"] == "3"


class TestDatabaseResources:
    def test_map_database(self) -> None:
        from skyforge.providers.digitalocean.database import DatabaseResources

        auth = MagicMock()
        res = DatabaseResources(auth)

        db = {
            "id": "db-1",
            "name": "my-postgres",
            "status": "online",
            "region": "nyc1",
            "engine": "pg",
            "version": "15",
            "size": "db-s-1vcpu-1gb",
            "num_nodes": 1,
            "connection": {
                "host": "db.host.com",
                "port": 25060,
                "database": "defaultdb",
            },
            "tags": ["production"],
        }
        resource = res._map_database(db)

        assert resource.name == "my-postgres"
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["engine"] == "pg"
        assert resource.metadata["resource_subtype"] == "managed_database"


class TestKubernetesResources:
    def test_map_cluster(self) -> None:
        from skyforge.providers.digitalocean.kubernetes import KubernetesResources

        auth = MagicMock()
        res = KubernetesResources(auth)

        cluster = {
            "id": "k8s-1",
            "name": "prod-cluster",
            "region": "nyc3",
            "status": {"state": "running"},
            "version": "1.29.1-do.0",
            "endpoint": "https://k8s.do.com/k8s-1",
            "node_pools": [{"id": "np-1"}],
            "ha": True,
            "tags": [],
        }
        resource = res._map_cluster(cluster)

        assert resource.name == "prod-cluster"
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["resource_subtype"] == "doks_cluster"


class TestDNSResources:
    def test_map_domain(self) -> None:
        from skyforge.providers.digitalocean.dns import DNSResources

        auth = MagicMock()
        res = DNSResources(auth)

        domain = {"name": "example.com", "ttl": 1800}
        resource = res._map_domain(domain)

        assert resource.name == "example.com"
        assert resource.metadata["resource_subtype"] == "dns_domain"

    def test_map_record(self) -> None:
        from skyforge.providers.digitalocean.dns import DNSResources

        auth = MagicMock()
        res = DNSResources(auth)

        record = {
            "id": 111,
            "type": "A",
            "name": "www",
            "data": "1.2.3.4",
            "ttl": 300,
            "priority": None,
        }
        resource = res._map_record(record, "example.com")

        assert resource.name == "www.example.com"
        assert resource.metadata["record_type"] == "A"
        assert resource.metadata["data"] == "1.2.3.4"


class TestDropletActions:
    def test_action_verb_enum(self) -> None:
        from skyforge.providers.digitalocean.actions import ActionVerb

        assert ActionVerb.START == "power_on"
        assert ActionVerb.STOP == "power_off"
        assert ActionVerb.REBOOT == "reboot"
        assert ActionVerb.SHUTDOWN == "shutdown"

    def test_valid_state_transitions(self) -> None:
        from skyforge.providers.digitalocean.actions import _VALID_STATES, ActionVerb

        assert "off" in _VALID_STATES[ActionVerb.START]
        assert "active" in _VALID_STATES[ActionVerb.STOP]
        assert "active" in _VALID_STATES[ActionVerb.REBOOT]


class TestDigitalOceanCostAnalyzer:
    def test_can_create(self) -> None:
        from skyforge.providers.digitalocean.cost import DigitalOceanCostAnalyzer

        auth = MagicMock()
        analyzer = DigitalOceanCostAnalyzer(auth)
        assert analyzer is not None

    def test_classify_service(self) -> None:
        from skyforge.providers.digitalocean.cost import DigitalOceanCostAnalyzer

        auth = MagicMock()
        analyzer = DigitalOceanCostAnalyzer(auth)

        assert analyzer._classify_service("Droplet s-1vcpu-1gb") == "Droplets"
        assert analyzer._classify_service("Block Storage 100GB") == "Block Storage"
        assert analyzer._classify_service("Kubernetes control plane") == "Kubernetes (DOKS)"
        assert analyzer._classify_service("random thing") == "Other"

    async def test_get_cost_summary_happy_path(self) -> None:
        """Balance endpoint reports MTD usage + history has a prior invoice."""
        from decimal import Decimal

        from skyforge.providers.digitalocean.cost import DigitalOceanCostAnalyzer

        auth = MagicMock()
        # Pick a date well inside the 30-day window
        from datetime import date, timedelta

        invoice_date = (date.today() - timedelta(days=5)).isoformat() + "T00:00:00Z"

        async def fake_get(path: str, params: dict | None = None) -> dict:
            assert path == "/customers/my/balance"
            return {
                "account_balance": "-12.50",
                "month_to_date_usage": "42.17",
                "month_to_date_balance": "-54.67",
            }

        async def fake_paginated(path: str, key: str, **_: object) -> list[dict]:
            assert path == "/customers/my/billing_history"
            assert key == "billing_history"
            return [
                {
                    "description": "Invoice for prior month",
                    "amount": "100.00",
                    "type": "Invoice",
                    "date": invoice_date,
                },
                {
                    "description": "Payment (credit card)",
                    "amount": "-200.00",
                    "type": "Payment",
                    "date": invoice_date,
                },
            ]

        auth.get = fake_get
        auth.get_paginated = fake_paginated
        analyzer = DigitalOceanCostAnalyzer(auth)

        summary = await analyzer.get_cost_summary(period_days=30)

        # Total = MTD usage ($42.17) + invoice charge ($100) — payment ignored
        assert summary.total_cost == Decimal("142.17")
        assert summary.currency == "USD"
        # Service list includes the invoice bucket + the synthetic MTD bucket
        service_names = {s.service for s in summary.by_service}
        assert "Current Month-to-Date Usage" in service_names
        assert "Prior Monthly Invoices" in service_names
        # Notes should surface the balance + warn about granularity
        assert "Month-to-date usage: $42.17" in summary.notes
        assert "monthly invoices only" in summary.notes

    async def test_get_cost_summary_auth_failure(self) -> None:
        """401 on the balance endpoint must surface in notes, not hide as $0."""
        from decimal import Decimal

        from skyforge.providers.digitalocean.cost import DigitalOceanCostAnalyzer

        auth = MagicMock()

        async def fake_get(path: str, params: dict | None = None) -> dict:
            raise RuntimeError("HTTP 401 Unauthorized")

        async def fake_paginated(path: str, key: str, **_: object) -> list[dict]:
            raise RuntimeError("HTTP 401 Unauthorized")

        auth.get = fake_get
        auth.get_paginated = fake_paginated
        analyzer = DigitalOceanCostAnalyzer(auth)

        summary = await analyzer.get_cost_summary(period_days=30)

        assert summary.total_cost == Decimal("0.00")
        # The failure must be surfaced — not silently swallowed as before
        assert "balance endpoint failed" in summary.notes
        # Hint should explain this is an account-role issue, not a PAT-scope issue
        assert "billing role" in summary.notes or "team role" in summary.notes


class TestDigitalOceanSecurityAuditor:
    def test_can_create(self) -> None:
        from skyforge.providers.digitalocean.security import (
            DigitalOceanSecurityAuditor,
        )

        auth = MagicMock()
        auditor = DigitalOceanSecurityAuditor(auth)
        assert auditor is not None


class TestDigitalOceanUnusedDetector:
    def test_can_create(self) -> None:
        from skyforge.providers.digitalocean.unused import (
            DigitalOceanUnusedDetector,
        )

        auth = MagicMock()
        detector = DigitalOceanUnusedDetector(auth)
        assert detector is not None


class TestDigitalOceanMonitoring:
    def test_can_create(self) -> None:
        from skyforge.providers.digitalocean.monitoring import (
            DigitalOceanMonitoringAnalyzer,
        )

        analyzer = DigitalOceanMonitoringAnalyzer(MagicMock())
        assert analyzer is not None


class TestDigitalOceanRelationshipMapper:
    def test_can_create(self) -> None:
        from skyforge.providers.digitalocean.relationships import (
            DigitalOceanRelationshipMapper,
        )

        auth = MagicMock()
        mapper = DigitalOceanRelationshipMapper(auth)
        assert mapper is not None
