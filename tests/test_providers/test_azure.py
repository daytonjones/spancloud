"""Tests for the Azure provider and resource modules."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from spancloud.core.resource import ResourceState, ResourceType

# ---------------------------------------------------------------------------
# Provider + auth
# ---------------------------------------------------------------------------


class TestAzureProvider:
    def test_name(self) -> None:
        from spancloud.providers.azure.provider import AzureProvider

        provider = AzureProvider()
        assert provider.name == "azure"

    def test_display_name(self) -> None:
        from spancloud.providers.azure.provider import AzureProvider

        provider = AzureProvider()
        assert provider.display_name == "Microsoft Azure"

    def test_supported_resource_types(self) -> None:
        from spancloud.providers.azure.provider import AzureProvider

        provider = AzureProvider()
        expected = [
            ResourceType.COMPUTE,
            ResourceType.STORAGE,
            ResourceType.NETWORK,
            ResourceType.DATABASE,
            ResourceType.SERVERLESS,
            ResourceType.CONTAINER,
            ResourceType.LOAD_BALANCER,
            ResourceType.DNS,
        ]
        assert provider.supported_resource_types == expected


class TestAzureAuth:
    def test_can_create(self) -> None:
        from spancloud.providers.azure.auth import AzureAuth

        auth = AzureAuth()
        assert auth.subscription_id == ""
        assert auth.tenant_id == ""

    def test_set_subscription(self) -> None:
        from spancloud.providers.azure.auth import AzureAuth

        auth = AzureAuth()
        auth.set_subscription("abc-123")
        assert auth.subscription_id == "abc-123"


# ---------------------------------------------------------------------------
# Tier 1 — mapper functions
# ---------------------------------------------------------------------------


class TestVMResources:
    def test_map_vm_running(self) -> None:
        from spancloud.providers.azure.compute import VMResources

        res = VMResources(MagicMock())

        vm = SimpleNamespace(
            id=(
                "/subscriptions/abc/resourceGroups/prod/providers/"
                "Microsoft.Compute/virtualMachines/web-1"
            ),
            name="web-1",
            location="eastus",
            tags={"env": "prod"},
            hardware_profile=SimpleNamespace(vm_size="Standard_D2s_v3"),
            os_profile=SimpleNamespace(computer_name="web-1"),
            storage_profile=SimpleNamespace(
                os_disk=SimpleNamespace(os_type="Linux"),
                image_reference=SimpleNamespace(
                    publisher="Canonical",
                    offer="UbuntuServer",
                    sku="22_04-LTS",
                ),
            ),
        )
        resource = res._map_vm(vm, "PowerState/running", "prod")

        assert resource.name == "web-1"
        assert resource.resource_type == ResourceType.COMPUTE
        assert resource.provider == "azure"
        assert resource.region == "eastus"
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["vm_size"] == "Standard_D2s_v3"
        assert resource.metadata["resource_group"] == "prod"
        assert resource.metadata["resource_subtype"] == "virtual_machine"

    def test_parse_resource_group(self) -> None:
        from spancloud.providers.azure.compute import _parse_resource_group

        rid = (
            "/subscriptions/abc/resourceGroups/my-rg/providers/"
            "Microsoft.Compute/virtualMachines/vm-1"
        )
        assert _parse_resource_group(rid) == "my-rg"
        assert _parse_resource_group("") == ""


class TestStorageAccountResources:
    def test_map_account(self) -> None:
        from spancloud.providers.azure.storage import StorageAccountResources

        res = StorageAccountResources(MagicMock())

        sa = SimpleNamespace(
            id="/subscriptions/a/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/data",
            name="data",
            location="westus2",
            tags={},
            sku=SimpleNamespace(name="Standard_LRS", tier="Standard"),
            kind="StorageV2",
            access_tier="Hot",
            enable_https_traffic_only=True,
            allow_blob_public_access=False,
            provisioning_state="Succeeded",
            creation_time=None,
        )
        resource = res._map_account(sa)

        assert resource.name == "data"
        assert resource.resource_type == ResourceType.STORAGE
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["sku"] == "Standard_LRS"
        assert resource.metadata["kind"] == "StorageV2"
        assert resource.metadata["resource_subtype"] == "storage_account"


class TestVNetResources:
    def test_map_vnet(self) -> None:
        from spancloud.providers.azure.network import VNetResources

        res = VNetResources(MagicMock())

        vnet = SimpleNamespace(
            id="/subscriptions/a/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/main",
            name="main",
            location="eastus",
            tags={},
            address_space=SimpleNamespace(address_prefixes=["10.0.0.0/16"]),
            subnets=[SimpleNamespace(name="app"), SimpleNamespace(name="db")],
        )
        resource = res._map_vnet(vnet)

        assert resource.name == "main"
        assert resource.resource_type == ResourceType.NETWORK
        assert resource.metadata["address_prefixes"] == "10.0.0.0/16"
        assert resource.metadata["subnet_count"] == "2"
        assert resource.metadata["resource_subtype"] == "vnet"

    def test_map_public_ip_unattached(self) -> None:
        from spancloud.providers.azure.network import VNetResources

        res = VNetResources(MagicMock())

        pip = SimpleNamespace(
            id="/subscriptions/a/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/ip-1",
            name="ip-1",
            location="eastus",
            tags={},
            ip_address="1.2.3.4",
            public_ip_allocation_method="Static",
            sku=SimpleNamespace(name="Standard"),
            ip_configuration=None,
        )
        resource = res._map_public_ip(pip)

        assert resource.state == ResourceState.STOPPED
        assert resource.metadata["attached"] == "False"


class TestDatabaseResources:
    def test_map_sql_database(self) -> None:
        from spancloud.providers.azure.database import SQLResources

        res = SQLResources(MagicMock())

        server = SimpleNamespace(
            id="/subscriptions/a/resourceGroups/rg/providers/Microsoft.Sql/servers/prod-sql",
            name="prod-sql",
            location="eastus",
        )
        db = SimpleNamespace(
            id=server.id + "/databases/app",
            name="app",
            location="eastus",
            tags={},
            sku=SimpleNamespace(name="S0", tier="Standard"),
            status="Online",
            collation="SQL_Latin1_General_CP1_CI_AS",
        )
        resource = res._map_db(db, server, "rg")

        assert resource.name == "prod-sql/app"
        assert resource.resource_type == ResourceType.DATABASE
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["sku"] == "S0"
        assert resource.metadata["resource_subtype"] == "sql_database"

    def test_map_cosmos_account(self) -> None:
        from spancloud.providers.azure.database import CosmosDBResources

        res = CosmosDBResources(MagicMock())

        acct = SimpleNamespace(
            id="/subscriptions/a/resourceGroups/rg/providers/Microsoft.DocumentDB/databaseAccounts/cos",
            name="cos",
            location="eastus",
            tags={},
            kind="GlobalDocumentDB",
            provisioning_state="Succeeded",
            locations=[SimpleNamespace()],
            document_endpoint="https://cos.documents.azure.com:443/",
        )
        resource = res._map_account(acct)

        assert resource.name == "cos"
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["kind"] == "GlobalDocumentDB"
        assert resource.metadata["resource_subtype"] == "cosmos_db"


class TestAppServiceResources:
    def test_map_function_app(self) -> None:
        from spancloud.providers.azure.app_service import AppServiceResources

        res = AppServiceResources(MagicMock())

        site = SimpleNamespace(
            id="/subscriptions/a/resourceGroups/rg/providers/Microsoft.Web/sites/api",
            name="api",
            location="eastus",
            tags={},
            kind="functionapp,linux",
            state="Running",
            default_host_name="api.azurewebsites.net",
            https_only=True,
            site_config=SimpleNamespace(linux_fx_version="Python|3.11"),
        )
        resource = res._map_site(site)

        assert resource.name == "api"
        assert resource.resource_type == ResourceType.SERVERLESS
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["is_function_app"] == "True"
        assert resource.metadata["resource_subtype"] == "function_app"

    def test_map_web_app(self) -> None:
        from spancloud.providers.azure.app_service import AppServiceResources

        res = AppServiceResources(MagicMock())

        site = SimpleNamespace(
            id="/subscriptions/a/resourceGroups/rg/providers/Microsoft.Web/sites/web",
            name="web",
            location="eastus",
            tags={},
            kind="app,linux",
            state="Stopped",
            default_host_name="web.azurewebsites.net",
            https_only=True,
            site_config=None,
        )
        resource = res._map_site(site)

        assert resource.state == ResourceState.STOPPED
        assert resource.metadata["resource_subtype"] == "web_app"


class TestAKSResources:
    def test_map_cluster(self) -> None:
        from spancloud.providers.azure.aks import AKSResources

        res = AKSResources(MagicMock())

        cluster = SimpleNamespace(
            id="/subscriptions/a/resourceGroups/rg/providers/Microsoft.ContainerService/managedClusters/main",
            name="main",
            location="eastus",
            tags={},
            provisioning_state="Succeeded",
            power_state=SimpleNamespace(code="Running"),
            agent_pool_profiles=[SimpleNamespace(count=3), SimpleNamespace(count=2)],
            kubernetes_version="1.29.0",
            dns_prefix="main",
            fqdn="main.eastus.aks.io",
        )
        resource = res._map_cluster(cluster)

        assert resource.name == "main"
        assert resource.resource_type == ResourceType.CONTAINER
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["node_count"] == "5"
        assert resource.metadata["resource_subtype"] == "aks_cluster"


class TestLoadBalancerResources:
    def test_map_lb(self) -> None:
        from spancloud.providers.azure.loadbalancer import LoadBalancerResources

        res = LoadBalancerResources(MagicMock())

        lb = SimpleNamespace(
            id="/subscriptions/a/resourceGroups/rg/providers/Microsoft.Network/loadBalancers/main-lb",
            name="main-lb",
            location="eastus",
            tags={},
            sku=SimpleNamespace(name="Standard", tier="Regional"),
            frontend_ip_configurations=[SimpleNamespace()],
            backend_address_pools=[SimpleNamespace(), SimpleNamespace()],
            load_balancing_rules=[SimpleNamespace()],
        )
        resource = res._map_lb(lb)

        assert resource.name == "main-lb"
        assert resource.resource_type == ResourceType.LOAD_BALANCER
        assert resource.metadata["sku"] == "Standard"
        assert resource.metadata["backend_pool_count"] == "2"
        assert resource.metadata["resource_subtype"] == "load_balancer"


class TestDNSResources:
    def test_map_zone(self) -> None:
        from spancloud.providers.azure.dns import DNSResources

        res = DNSResources(MagicMock())

        zone = SimpleNamespace(
            id="/subscriptions/a/resourceGroups/rg/providers/Microsoft.Network/dnszones/example.com",
            name="example.com",
            tags={},
            zone_type="Public",
            number_of_record_sets=15,
            name_servers=["ns1-01.azure-dns.com"],
        )
        resource = res._map_zone(zone)

        assert resource.name == "example.com"
        assert resource.resource_type == ResourceType.DNS
        assert resource.region == "global"
        assert resource.metadata["record_count"] == "15"
        assert resource.metadata["resource_subtype"] == "dns_zone"


# ---------------------------------------------------------------------------
# Tier 2
# ---------------------------------------------------------------------------


class TestAzureCostAnalyzer:
    def test_can_create(self) -> None:
        from spancloud.providers.azure.cost import AzureCostAnalyzer

        analyzer = AzureCostAnalyzer(MagicMock())
        assert analyzer is not None

    def test_parse_service_rows_empty(self) -> None:
        from spancloud.providers.azure.cost import _parse_service_rows

        result = SimpleNamespace(rows=[], columns=[])
        assert _parse_service_rows(result) == []


class TestAzureSecurityAuditor:
    def test_can_create(self) -> None:
        from spancloud.providers.azure.security import AzureSecurityAuditor

        auditor = AzureSecurityAuditor(MagicMock())
        assert auditor is not None

    def test_nsg_rule_finding_critical(self) -> None:
        from spancloud.providers.azure.security import AzureSecurityAuditor

        auditor = AzureSecurityAuditor(MagicMock())
        nsg = SimpleNamespace(id="/nsg/1", name="web-nsg", location="eastus")
        rule = SimpleNamespace(
            name="AllowAllInbound",
            access="Allow",
            direction="Inbound",
            source_address_prefix="0.0.0.0/0",
            destination_port_range="*",
            destination_port_ranges=None,
        )
        finding = auditor._nsg_rule_finding(nsg, rule)
        assert finding is not None
        assert finding.severity.value == "critical"

    def test_nsg_rule_finding_sensitive_port(self) -> None:
        from spancloud.providers.azure.security import AzureSecurityAuditor

        auditor = AzureSecurityAuditor(MagicMock())
        nsg = SimpleNamespace(id="/nsg/1", name="web-nsg", location="eastus")
        rule = SimpleNamespace(
            name="AllowSSH",
            access="Allow",
            direction="Inbound",
            source_address_prefix="Internet",
            destination_port_range="22",
            destination_port_ranges=None,
        )
        finding = auditor._nsg_rule_finding(nsg, rule)
        assert finding is not None
        assert finding.severity.value == "high"

    def test_nsg_rule_finding_internal_source_safe(self) -> None:
        from spancloud.providers.azure.security import AzureSecurityAuditor

        auditor = AzureSecurityAuditor(MagicMock())
        nsg = SimpleNamespace(id="/nsg/1", name="web-nsg", location="eastus")
        rule = SimpleNamespace(
            name="AllowVNet",
            access="Allow",
            direction="Inbound",
            source_address_prefix="VirtualNetwork",
            destination_port_range="22",
            destination_port_ranges=None,
        )
        assert auditor._nsg_rule_finding(nsg, rule) is None


class TestAzureUnusedDetector:
    def test_can_create(self) -> None:
        from spancloud.providers.azure.unused import AzureUnusedDetector

        detector = AzureUnusedDetector(MagicMock())
        assert detector is not None


class TestAzureMonitoring:
    def test_can_create(self) -> None:
        from spancloud.providers.azure.monitoring import AzureMonitoringAnalyzer

        analyzer = AzureMonitoringAnalyzer(MagicMock())
        assert analyzer is not None

    def test_map_rule(self) -> None:
        from spancloud.providers.azure.monitoring import AzureMonitoringAnalyzer

        analyzer = AzureMonitoringAnalyzer(MagicMock())
        rule = SimpleNamespace(
            name="cpu-high",
            description="Alert when CPU > 80%",
            enabled=True,
            severity=2,
            criteria=SimpleNamespace(
                all_of=[SimpleNamespace(), SimpleNamespace()],
                odata_type="Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria",
            ),
            actions=[SimpleNamespace()],
        )
        info = analyzer._map_rule(rule)
        assert info.name == "cpu-high"
        assert info.enabled is True
        assert info.conditions_count == 2
        assert info.notification_channels == 1
        assert "sev2" in info.combiner


class TestAzureRelationshipMapper:
    def test_can_create(self) -> None:
        from spancloud.providers.azure.relationships import (
            AzureRelationshipMapper,
        )

        mapper = AzureRelationshipMapper(MagicMock())
        assert mapper is not None


# ---------------------------------------------------------------------------
# Tier 3 — actions
# ---------------------------------------------------------------------------


class TestVMActions:
    def test_action_verb_enum(self) -> None:
        from spancloud.providers.azure.actions import ActionVerb

        assert ActionVerb.START == "start"
        assert ActionVerb.STOP == "deallocate"
        assert ActionVerb.RESTART == "restart"
        assert ActionVerb.POWEROFF == "poweroff"

    def test_valid_state_transitions(self) -> None:
        from spancloud.providers.azure.actions import _VALID_STATES, ActionVerb

        assert "PowerState/stopped" in _VALID_STATES[ActionVerb.START]
        assert "PowerState/deallocated" in _VALID_STATES[ActionVerb.START]
        assert "PowerState/running" in _VALID_STATES[ActionVerb.STOP]
        assert "PowerState/running" in _VALID_STATES[ActionVerb.RESTART]

    def test_resolve_rg_name_from_id(self) -> None:
        from spancloud.providers.azure.actions import _resolve_rg_name

        rg, name = _resolve_rg_name(
            "/subscriptions/x/resourceGroups/prod/providers/"
            "Microsoft.Compute/virtualMachines/web-1",
            None,
        )
        assert rg == "prod"
        assert name == "web-1"

    def test_resolve_rg_name_bare(self) -> None:
        from spancloud.providers.azure.actions import _resolve_rg_name

        rg, name = _resolve_rg_name("web-1", "prod")
        assert rg == "prod"
        assert name == "web-1"
