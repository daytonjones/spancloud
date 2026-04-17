"""Tests for the GCP provider and resource modules."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from skyforge.core.exceptions import ProviderError
from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.providers.gcp.provider import GCPProvider


@pytest.fixture
def gcp_provider() -> GCPProvider:
    """Return a GCPProvider with mocked auth."""
    provider = GCPProvider()
    provider._auth._project_id = "test-project"
    provider._auth._credentials = MagicMock()
    provider._authenticated = True
    return provider


class TestGCPProvider:
    """Tests for the GCPProvider class."""

    def test_name(self) -> None:
        provider = GCPProvider()
        assert provider.name == "gcp"

    def test_display_name(self) -> None:
        provider = GCPProvider()
        assert provider.display_name == "Google Cloud Platform"

    def test_supported_resource_types(self) -> None:
        provider = GCPProvider()
        expected = [
            ResourceType.COMPUTE,
            ResourceType.STORAGE,
            ResourceType.NETWORK,
            ResourceType.DATABASE,
            ResourceType.CONTAINER,
            ResourceType.SERVERLESS,
            ResourceType.LOAD_BALANCER,
            ResourceType.DNS,
        ]
        assert provider.supported_resource_types == expected

    @pytest.mark.asyncio
    async def test_unsupported_resource_type_raises(self, gcp_provider: GCPProvider) -> None:
        with pytest.raises(ProviderError, match="not yet supported"):
            await gcp_provider.list_resources(ResourceType.IAM)

    @pytest.mark.asyncio
    async def test_get_resource_compute_requires_region(self, gcp_provider: GCPProvider) -> None:
        with pytest.raises(ProviderError, match="Zone"):
            await gcp_provider.get_resource(ResourceType.COMPUTE, "test-instance")

    @pytest.mark.asyncio
    async def test_get_resource_unsupported_type(self, gcp_provider: GCPProvider) -> None:
        with pytest.raises(ProviderError, match="not supported"):
            await gcp_provider.get_resource(ResourceType.STORAGE, "my-bucket")

    @pytest.mark.asyncio
    async def test_tag_filtering(self, gcp_provider: GCPProvider) -> None:
        """Verify client-side tag filtering works across resource types."""
        mock_resources = [
            Resource(
                id="inst-1",
                name="tagged",
                resource_type=ResourceType.COMPUTE,
                provider="gcp",
                tags={"env": "prod"},
            ),
            Resource(
                id="inst-2",
                name="untagged",
                resource_type=ResourceType.COMPUTE,
                provider="gcp",
                tags={"env": "dev"},
            ),
        ]
        gcp_provider._compute.list_instances = AsyncMock(return_value=mock_resources)

        result = await gcp_provider.list_resources(
            ResourceType.COMPUTE, tags={"env": "prod"}
        )
        assert len(result) == 1
        assert result[0].name == "tagged"


class TestGCPAuth:
    """Tests for GCPAuth helpers."""

    def test_set_project(self) -> None:
        from skyforge.providers.gcp.auth import GCPAuth

        auth = GCPAuth()
        auth.set_project("my-other-project")
        assert auth.project_id == "my-other-project"
        auth.set_project("")
        assert auth.project_id == ""

    def test_sync_list_projects_filters_inactive(self) -> None:
        """_sync_list_projects should skip non-ACTIVE projects and sort the rest."""
        from unittest.mock import MagicMock, patch

        from skyforge.providers.gcp.auth import GCPAuth

        auth = GCPAuth()
        auth._credentials = MagicMock()

        # Fake the googleapiclient discovery chain
        list_request = MagicMock()
        list_request.execute.return_value = {
            "projects": [
                {
                    "projectId": "zeta-prod",
                    "name": "Zeta Prod",
                    "projectNumber": 1,
                    "lifecycleState": "ACTIVE",
                },
                {
                    "projectId": "archived-001",
                    "name": "Archived",
                    "projectNumber": 2,
                    "lifecycleState": "DELETE_REQUESTED",
                },
                {
                    "projectId": "alpha-dev",
                    "name": "alpha-dev",
                    "projectNumber": 3,
                    "lifecycleState": "ACTIVE",
                },
            ],
        }
        projects_api = MagicMock()
        projects_api.list.return_value = list_request
        projects_api.list_next.return_value = None
        service = MagicMock()
        service.projects.return_value = projects_api

        with patch("googleapiclient.discovery.build", return_value=service):
            out = auth._sync_list_projects()

        ids = [p["project_id"] for p in out]
        assert ids == ["alpha-dev", "zeta-prod"]  # sorted, DELETE_REQUESTED dropped


class TestNetworkResources:
    """Tests for VPC network resource mapping."""

    def test_map_network(self) -> None:
        from skyforge.providers.gcp.vpc import NetworkResources

        auth = MagicMock()
        nr = NetworkResources(auth)

        mock_network = MagicMock()
        mock_network.id = 12345
        mock_network.name = "my-vpc"
        mock_network.auto_create_subnetworks = False
        mock_network.mtu = 1460
        mock_network.routing_config.routing_mode = "REGIONAL"
        mock_network.peerings = []

        resource = nr._map_network(mock_network)

        assert resource.id == "12345"
        assert resource.name == "my-vpc"
        assert resource.resource_type == ResourceType.NETWORK
        assert resource.provider == "gcp"
        assert resource.region == "global"
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["subnet_mode"] == "custom"
        assert resource.metadata["resource_subtype"] == "vpc"

    def test_map_network_auto_mode(self) -> None:
        from skyforge.providers.gcp.vpc import NetworkResources

        auth = MagicMock()
        nr = NetworkResources(auth)

        mock_network = MagicMock()
        mock_network.id = 99
        mock_network.name = "default"
        mock_network.auto_create_subnetworks = True
        mock_network.mtu = 1460
        mock_network.routing_config.routing_mode = "GLOBAL"
        mock_network.peerings = [MagicMock()]

        resource = nr._map_network(mock_network)
        assert resource.metadata["subnet_mode"] == "auto"
        assert resource.metadata["peering_count"] == "1"


class TestSubnetResources:
    """Tests for subnet resource mapping."""

    def test_map_subnet(self) -> None:
        from skyforge.providers.gcp.vpc import SubnetResources

        auth = MagicMock()
        sr = SubnetResources(auth)

        mock_subnet = MagicMock()
        mock_subnet.id = 111
        mock_subnet.name = "my-subnet"
        mock_subnet.network = "projects/p/global/networks/my-vpc"
        mock_subnet.ip_cidr_range = "10.0.0.0/24"
        mock_subnet.purpose = "PRIVATE"
        mock_subnet.private_ip_google_access = True
        mock_subnet.stack_type = "IPV4_ONLY"

        resource = sr._map_subnet(mock_subnet, "us-central1")

        assert resource.name == "my-subnet"
        assert resource.region == "us-central1"
        assert resource.metadata["network"] == "my-vpc"
        assert resource.metadata["ip_cidr_range"] == "10.0.0.0/24"
        assert resource.metadata["resource_subtype"] == "subnet"


class TestFirewallResources:
    """Tests for firewall rule resource mapping."""

    def test_map_firewall(self) -> None:
        from skyforge.providers.gcp.vpc import FirewallResources

        auth = MagicMock()
        fr = FirewallResources(auth)

        mock_fw = MagicMock()
        mock_fw.id = 222
        mock_fw.name = "allow-ssh"
        mock_fw.network = "projects/p/global/networks/my-vpc"
        mock_fw.direction = "INGRESS"
        mock_fw.priority = 1000
        mock_fw.allowed = [MagicMock()]
        mock_fw.denied = []
        mock_fw.source_ranges = ["0.0.0.0/0"]
        mock_fw.target_tags = ["ssh-server"]
        mock_fw.disabled = False

        resource = fr._map_firewall(mock_fw)

        assert resource.name == "allow-ssh"
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["direction"] == "INGRESS"
        assert resource.metadata["action"] == "allow"
        assert resource.metadata["source_ranges"] == "0.0.0.0/0"
        assert resource.metadata["resource_subtype"] == "firewall"

    def test_disabled_firewall_is_stopped(self) -> None:
        from skyforge.providers.gcp.vpc import FirewallResources

        auth = MagicMock()
        fr = FirewallResources(auth)

        mock_fw = MagicMock()
        mock_fw.id = 333
        mock_fw.name = "disabled-rule"
        mock_fw.network = "projects/p/global/networks/default"
        mock_fw.direction = "INGRESS"
        mock_fw.priority = 65534
        mock_fw.allowed = []
        mock_fw.denied = [MagicMock()]
        mock_fw.source_ranges = []
        mock_fw.target_tags = []
        mock_fw.disabled = True

        resource = fr._map_firewall(mock_fw)
        assert resource.state == ResourceState.STOPPED


class TestCloudSQLResources:
    """Tests for Cloud SQL resource mapping."""

    def test_map_instance(self) -> None:
        from skyforge.providers.gcp.cloudsql import CloudSQLResources

        auth = MagicMock()
        cs = CloudSQLResources(auth)

        instance_dict = {
            "name": "my-db",
            "region": "us-central1",
            "state": "RUNNABLE",
            "databaseVersion": "POSTGRES_15",
            "settings": {
                "tier": "db-custom-2-8192",
                "dataDiskSizeGb": 100,
                "availabilityType": "REGIONAL",
                "userLabels": {"env": "prod"},
            },
            "ipAddresses": [{"ipAddress": "10.0.0.5", "type": "PRIVATE"}],
            "connectionName": "project:us-central1:my-db",
            "gceZone": "us-central1-a",
            "instanceType": "CLOUD_SQL_INSTANCE",
        }

        resource = cs._map_instance(instance_dict)

        assert resource.id == "my-db"
        assert resource.resource_type == ResourceType.DATABASE
        assert resource.state == ResourceState.RUNNING
        assert resource.tags == {"env": "prod"}
        assert resource.metadata["database_version"] == "POSTGRES_15"
        assert resource.metadata["tier"] == "db-custom-2-8192"
        assert resource.metadata["resource_subtype"] == "cloudsql_instance"


class TestGKEResources:
    """Tests for GKE resource mapping."""

    def test_map_cluster(self) -> None:
        from skyforge.providers.gcp.gke import GKEResources

        auth = MagicMock()
        gke = GKEResources(auth)

        mock_pool = MagicMock()
        mock_pool.initial_node_count = 3

        mock_cluster = MagicMock()
        mock_cluster.name = "my-cluster"
        mock_cluster.location = "us-central1"
        mock_cluster.status.name = "RUNNING"
        mock_cluster.current_master_version = "1.29.1-gke.100"
        mock_cluster.current_node_version = "1.29.1-gke.100"
        mock_cluster.endpoint = "34.1.2.3"
        mock_cluster.network = "projects/p/global/networks/default"
        mock_cluster.subnetwork = "projects/p/regions/us-central1/subnetworks/default"
        mock_cluster.cluster_ipv4_cidr = "10.4.0.0/14"
        mock_cluster.node_pools = [mock_pool]
        mock_cluster.resource_labels = {"team": "platform"}

        resource = gke._map_cluster(mock_cluster)

        assert resource.name == "my-cluster"
        assert resource.resource_type == ResourceType.CONTAINER
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["kubernetes_version"] == "1.29.1-gke.100"
        assert resource.metadata["total_node_count"] == "3"
        assert resource.metadata["resource_subtype"] == "gke_cluster"

    def test_map_node_pool(self) -> None:
        from skyforge.providers.gcp.gke import GKEResources

        auth = MagicMock()
        gke = GKEResources(auth)

        mock_pool = MagicMock()
        mock_pool.name = "default-pool"
        mock_pool.status.name = "RUNNING"
        mock_pool.initial_node_count = 3
        mock_pool.version = "1.29.1-gke.100"
        mock_pool.config.machine_type = "e2-medium"
        mock_pool.config.disk_size_gb = 100
        mock_pool.config.disk_type = "pd-standard"
        mock_pool.autoscaling.enabled = True
        mock_pool.autoscaling.min_node_count = 1
        mock_pool.autoscaling.max_node_count = 5

        resource = gke._map_node_pool(mock_pool, "my-cluster", "us-central1")

        assert resource.id == "my-cluster/default-pool"
        assert resource.name == "default-pool"
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["cluster"] == "my-cluster"
        assert resource.metadata["machine_type"] == "e2-medium"
        assert resource.metadata["autoscaling_enabled"] == "True"
        assert resource.metadata["resource_subtype"] == "gke_node_pool"


class TestCloudFunctionsResources:
    """Tests for Cloud Functions resource mapping."""

    def test_map_function(self) -> None:
        from skyforge.providers.gcp.functions import CloudFunctionsResources

        auth = MagicMock()
        cf = CloudFunctionsResources(auth)

        mock_fn = MagicMock()
        mock_fn.name = "projects/test/locations/us-central1/functions/my-function"
        mock_fn.state.name = "ACTIVE"
        mock_fn.labels = {"env": "staging"}
        mock_fn.build_config.runtime = "python312"
        mock_fn.build_config.entry_point = "handler"
        mock_fn.service_config.available_memory = "256Mi"
        mock_fn.service_config.timeout_seconds = 60
        mock_fn.service_config.max_instance_count = 100
        mock_fn.service_config.min_instance_count = 0
        mock_fn.environment.name = "GEN_2"
        mock_fn.url = "https://my-function-abc123.run.app"
        mock_fn.update_time = None

        resource = cf._map_function(mock_fn, "us-central1")

        assert resource.id == "my-function"
        assert resource.name == "my-function"
        assert resource.resource_type == ResourceType.SERVERLESS
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["runtime"] == "python312"
        assert resource.metadata["resource_subtype"] == "cloud_function"

    def test_extract_region(self) -> None:
        from skyforge.providers.gcp.functions import CloudFunctionsResources

        auth = MagicMock()
        cf = CloudFunctionsResources(auth)

        name = "projects/test-project/locations/us-central1/functions/my-fn"
        assert cf._extract_region(name) == "us-central1"

        assert cf._extract_region("short") == ""


class TestCloudRunResources:
    """Tests for Cloud Run resource mapping."""

    def test_map_service_ready(self) -> None:
        from skyforge.providers.gcp.cloudrun import CloudRunResources

        auth = MagicMock()
        cr = CloudRunResources(auth)

        mock_svc = MagicMock()
        mock_svc.name = "projects/test/locations/us-central1/services/my-service"
        mock_svc.labels = {"app": "web"}
        mock_svc.reconciling = False
        mock_svc.terminal_condition.state.name = "CONDITION_SUCCEEDED"
        mock_svc.conditions = []
        mock_svc.uri = "https://my-service-abc.run.app"
        mock_svc.create_time = None
        mock_svc.ingress.name = "INGRESS_TRAFFIC_ALL"
        mock_svc.launch_stage.name = "GA"

        container = MagicMock()
        container.image = "gcr.io/test/image:latest"
        container.resources.limits = {"memory": "512Mi", "cpu": "1"}
        mock_svc.template.containers = [container]
        mock_svc.template.scaling.max_instance_count = 10
        mock_svc.template.scaling.min_instance_count = 0

        resource = cr._map_service(mock_svc, "us-central1")

        assert resource.id == "my-service"
        assert resource.resource_type == ResourceType.SERVERLESS
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["image"] == "gcr.io/test/image:latest"
        assert resource.metadata["resource_subtype"] == "cloud_run_service"

    def test_reconciling_service_is_pending(self) -> None:
        from skyforge.providers.gcp.cloudrun import CloudRunResources

        auth = MagicMock()
        cr = CloudRunResources(auth)

        mock_svc = MagicMock()
        mock_svc.reconciling = True
        mock_svc.terminal_condition = None
        mock_svc.conditions = []

        state = cr._determine_state(mock_svc)
        assert state == ResourceState.PENDING

    def test_extract_region(self) -> None:
        from skyforge.providers.gcp.cloudrun import CloudRunResources

        auth = MagicMock()
        cr = CloudRunResources(auth)

        name = "projects/test/locations/europe-west1/services/api"
        assert cr._extract_region(name) == "europe-west1"


class TestLoadBalancerResources:
    """Tests for load balancer resource mapping."""

    def test_map_forwarding_rule(self) -> None:
        from skyforge.providers.gcp.loadbalancer import LoadBalancerResources

        auth = MagicMock()
        lb = LoadBalancerResources(auth)

        mock_rule = MagicMock()
        mock_rule.id = 444
        mock_rule.name = "my-lb-rule"
        mock_rule.target = "projects/p/global/targetHttpProxies/my-proxy"
        mock_rule.backend_service = None
        mock_rule.load_balancing_scheme = "EXTERNAL_MANAGED"
        mock_rule.port_range = "443-443"
        mock_rule.ports = []
        mock_rule.labels = {"tier": "frontend"}
        mock_rule.network_tier = "PREMIUM"
        # The compute_v1 ForwardingRule uses I_p_address and I_p_protocol
        mock_rule.I_p_address = "34.120.1.1"
        mock_rule.I_p_protocol = "TCP"

        resource = lb._map_forwarding_rule(mock_rule, "global")

        assert resource.name == "my-lb-rule"
        assert resource.resource_type == ResourceType.LOAD_BALANCER
        assert resource.state == ResourceState.RUNNING
        assert resource.metadata["ip_address"] == "34.120.1.1"
        assert resource.metadata["lb_type"] == "external_http"
        assert resource.metadata["resource_subtype"] == "forwarding_rule"

    def test_classify_lb_types(self) -> None:
        from skyforge.providers.gcp.loadbalancer import LoadBalancerResources

        auth = MagicMock()
        lb = LoadBalancerResources(auth)

        rule = MagicMock()

        rule.target = "projects/p/global/targetHttpsProxies/x"
        assert lb._classify_lb_type("EXTERNAL_MANAGED", rule) == "external_http"

        rule.target = "projects/p/global/targetSslProxies/x"
        assert lb._classify_lb_type("EXTERNAL", rule) == "external_ssl_proxy"

        rule.target = "projects/p/global/targetTcpProxies/x"
        assert lb._classify_lb_type("EXTERNAL", rule) == "external_tcp_proxy"

        rule.target = "projects/p/global/targetPools/x"
        assert lb._classify_lb_type("EXTERNAL", rule) == "external_network"

        rule.target = "projects/p/regions/r/targetHttpProxies/x"
        assert lb._classify_lb_type("INTERNAL_MANAGED", rule) == "internal_http"

        rule.target = ""
        assert lb._classify_lb_type("INTERNAL", rule) == "internal_tcp_udp"
