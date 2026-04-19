"""Mock provider — returns static demo data for screenshots and demos."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from spancloud.core.provider import BaseProvider
from spancloud.core.resource import Resource, ResourceState, ResourceType

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Demo resource factory helpers
# ---------------------------------------------------------------------------

def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _r(
    rid: str,
    name: str,
    rt: ResourceType,
    state: ResourceState = ResourceState.RUNNING,
    region: str = "us-east-1",
    created: datetime | None = None,
    tags: dict | None = None,
    **meta: object,
) -> Resource:
    return Resource(
        id=rid,
        name=name,
        provider="mock",
        resource_type=rt,
        state=state,
        region=region,
        created_at=created,
        tags=tags or {},
        metadata={k: str(v) for k, v in meta.items()},
    )


# ---------------------------------------------------------------------------
# Static demo data keyed by (provider_name, ResourceType)
# ---------------------------------------------------------------------------

_DEMO: dict[str, dict[ResourceType, list[Resource]]] = {
    "aws": {
        ResourceType.COMPUTE: [
            _r("i-0abc123456789def0", "web-prod-01",    ResourceType.COMPUTE, ResourceState.RUNNING,  "us-east-1", _dt(2024,3,12), {"env":"prod","team":"platform"}, instance_type="t3.medium"),
            _r("i-0def987654321abc1", "api-prod-01",    ResourceType.COMPUTE, ResourceState.RUNNING,  "us-east-1", _dt(2024,3,12), {"env":"prod","team":"platform"}, instance_type="t3.large"),
            _r("i-0fed321cba654def2", "worker-prod-01", ResourceType.COMPUTE, ResourceState.RUNNING,  "us-west-2", _dt(2024,4,1),  {"env":"prod","team":"data"},     instance_type="c5.xlarge"),
            _r("i-0aaa111bbb222ccc3", "staging-web",    ResourceType.COMPUTE, ResourceState.STOPPED,  "us-east-1", _dt(2024,5,20), {"env":"staging"},                instance_type="t3.small"),
            _r("i-0bbb222ccc333ddd4", "dev-sandbox",    ResourceType.COMPUTE, ResourceState.STOPPED,  "eu-west-1", _dt(2024,6,1),  {"env":"dev"},                    instance_type="t2.micro"),
        ],
        ResourceType.STORAGE: [
            _r("arn:aws:s3:::prod-assets-bucket",    "prod-assets-bucket",    ResourceType.STORAGE, ResourceState.RUNNING, "us-east-1", _dt(2023,1,15), size_bytes="42949672960",  versioning="enabled"),
            _r("arn:aws:s3:::prod-logs-archive",     "prod-logs-archive",     ResourceType.STORAGE, ResourceState.RUNNING, "us-east-1", _dt(2023,2,1),  size_bytes="107374182400", versioning="enabled"),
            _r("arn:aws:s3:::staging-uploads",       "staging-uploads",       ResourceType.STORAGE, ResourceState.RUNNING, "us-west-2", _dt(2023,6,10), size_bytes="5368709120",   versioning="disabled"),
            _r("arn:aws:s3:::dev-scratch-bucket",    "dev-scratch-bucket",    ResourceType.STORAGE, ResourceState.RUNNING, "us-east-1", _dt(2024,1,3),  size_bytes="1073741824",   versioning="disabled"),
        ],
        ResourceType.NETWORK: [
            _r("vpc-0abc123456", "prod-vpc",    ResourceType.NETWORK, ResourceState.RUNNING, "us-east-1", _dt(2022,8,1),  cidr="10.0.0.0/16",  subnets="6"),
            _r("vpc-0def456789", "staging-vpc", ResourceType.NETWORK, ResourceState.RUNNING, "us-east-1", _dt(2023,1,15), cidr="10.1.0.0/16",  subnets="4"),
            _r("vpc-0ghi789012", "dev-vpc",     ResourceType.NETWORK, ResourceState.RUNNING, "eu-west-1", _dt(2023,6,1),  cidr="10.2.0.0/16",  subnets="2"),
        ],
        ResourceType.DATABASE: [
            _r("arn:aws:rds:us-east-1:123456789:db:prod-postgres", "prod-postgres", ResourceType.DATABASE, ResourceState.RUNNING, "us-east-1", _dt(2023,3,1), engine="postgres", engine_version="15.4", instance_class="db.t3.medium"),
            _r("arn:aws:rds:us-east-1:123456789:db:prod-mysql",    "prod-mysql",    ResourceType.DATABASE, ResourceState.RUNNING, "us-east-1", _dt(2023,5,1), engine="mysql",    engine_version="8.0",  instance_class="db.t3.small"),
            _r("arn:aws:rds:us-west-2:123456789:db:analytics-pg",  "analytics-pg",  ResourceType.DATABASE, ResourceState.STOPPED, "us-west-2", _dt(2024,1,1), engine="postgres", engine_version="15.4", instance_class="db.r5.large"),
        ],
        ResourceType.SERVERLESS: [
            _r("arn:aws:lambda:us-east-1:123456:function:api-handler",    "api-handler",    ResourceType.SERVERLESS, ResourceState.RUNNING, "us-east-1", _dt(2024,2,1),  runtime="python3.12", memory_mb="512",  timeout_s="30"),
            _r("arn:aws:lambda:us-east-1:123456:function:image-resizer",  "image-resizer",  ResourceType.SERVERLESS, ResourceState.RUNNING, "us-east-1", _dt(2024,3,15), runtime="nodejs20.x", memory_mb="1024", timeout_s="60"),
            _r("arn:aws:lambda:us-west-2:123456:function:data-processor", "data-processor", ResourceType.SERVERLESS, ResourceState.RUNNING, "us-west-2", _dt(2024,4,1),  runtime="python3.12", memory_mb="256",  timeout_s="120"),
        ],
        ResourceType.LOAD_BALANCER: [
            _r("arn:aws:elasticloadbalancing:us-east-1:123456:loadbalancer/app/prod-alb/abc123", "prod-alb",     ResourceType.LOAD_BALANCER, ResourceState.RUNNING, "us-east-1", _dt(2023,4,1), lb_type="application", targets="3"),
            _r("arn:aws:elasticloadbalancing:us-east-1:123456:loadbalancer/net/prod-nlb/def456", "prod-nlb",     ResourceType.LOAD_BALANCER, ResourceState.RUNNING, "us-east-1", _dt(2023,9,1), lb_type="network",     targets="2"),
        ],
        ResourceType.CONTAINER: [
            _r("arn:aws:eks:us-east-1:123456:cluster/prod-cluster", "prod-cluster", ResourceType.CONTAINER, ResourceState.RUNNING, "us-east-1", _dt(2023,6,1), kubernetes_version="1.29", node_groups="3"),
        ],
        ResourceType.DNS: [
            _r("Z1PA6795UKMFR9", "example.com",         ResourceType.DNS, ResourceState.RUNNING, "global", _dt(2022,1,1), record_count="42"),
            _r("Z2FDTNDATAQYW2", "internal.example.com", ResourceType.DNS, ResourceState.RUNNING, "global", _dt(2022,6,1), record_count="18"),
        ],
        ResourceType.IAM: [
            _r("AIDA000000000000001", "deploy-bot",      ResourceType.IAM, ResourceState.RUNNING, "global", _dt(2022,1,1), user_type="service"),
            _r("AIDA000000000000002", "ci-runner",       ResourceType.IAM, ResourceState.RUNNING, "global", _dt(2022,3,1), user_type="service"),
            _r("AIDA000000000000003", "alice@example.com", ResourceType.IAM, ResourceState.RUNNING, "global", _dt(2023,1,1), user_type="human"),
            _r("AIDA000000000000004", "bob@example.com",   ResourceType.IAM, ResourceState.RUNNING, "global", _dt(2023,6,1), user_type="human"),
        ],
    },
    "gcp": {
        ResourceType.COMPUTE: [
            _r("projects/demo-project/zones/us-central1-a/instances/web-01", "web-01", ResourceType.COMPUTE, ResourceState.RUNNING,  "us-central1", _dt(2024,2,1),  machine_type="n2-standard-2"),
            _r("projects/demo-project/zones/us-central1-a/instances/api-01", "api-01", ResourceType.COMPUTE, ResourceState.RUNNING,  "us-central1", _dt(2024,2,15), machine_type="e2-medium"),
            _r("projects/demo-project/zones/eu-west1-b/instances/worker-01", "worker-01", ResourceType.COMPUTE, ResourceState.STOPPED, "eu-west1",   _dt(2024,3,1),  machine_type="n1-standard-4"),
        ],
        ResourceType.STORAGE: [
            _r("gs://demo-prod-assets",  "demo-prod-assets",  ResourceType.STORAGE, ResourceState.RUNNING, "us-central1", _dt(2023,1,1), storage_class="STANDARD"),
            _r("gs://demo-backups",      "demo-backups",      ResourceType.STORAGE, ResourceState.RUNNING, "us-east1",    _dt(2023,6,1), storage_class="NEARLINE"),
            _r("gs://demo-staging-data", "demo-staging-data", ResourceType.STORAGE, ResourceState.RUNNING, "eu-west1",    _dt(2024,1,1), storage_class="STANDARD"),
        ],
        ResourceType.DATABASE: [
            _r("projects/demo-project/instances/prod-postgres", "prod-postgres", ResourceType.DATABASE, ResourceState.RUNNING, "us-central1", _dt(2023,4,1), database_version="POSTGRES_15", tier="db-n1-standard-2"),
        ],
        ResourceType.SERVERLESS: [
            _r("projects/demo-project/locations/us-central1/functions/api-handler", "api-handler", ResourceType.SERVERLESS, ResourceState.RUNNING, "us-central1", _dt(2024,1,1), runtime="python312", memory_mb="512"),
            _r("projects/demo-project/locations/us-central1/functions/data-proc",   "data-proc",   ResourceType.SERVERLESS, ResourceState.RUNNING, "us-central1", _dt(2024,2,1), runtime="python312", memory_mb="256"),
        ],
        ResourceType.CONTAINER: [
            _r("projects/demo-project/locations/us-central1/clusters/prod-gke", "prod-gke", ResourceType.CONTAINER, ResourceState.RUNNING, "us-central1", _dt(2023,8,1), kubernetes_version="1.29"),
        ],
        ResourceType.NETWORK: [
            _r("projects/demo-project/global/networks/default", "default", ResourceType.NETWORK, ResourceState.RUNNING, "global", _dt(2022,1,1), subnets="8"),
        ],
    },
    "azure": {
        ResourceType.COMPUTE: [
            _r("/subscriptions/demo/resourceGroups/prod-rg/providers/Microsoft.Compute/virtualMachines/web-vm-01", "web-vm-01", ResourceType.COMPUTE, ResourceState.RUNNING,  "eastus", _dt(2024,1,15), size="Standard_D2s_v3"),
            _r("/subscriptions/demo/resourceGroups/prod-rg/providers/Microsoft.Compute/virtualMachines/api-vm-01", "api-vm-01", ResourceType.COMPUTE, ResourceState.RUNNING,  "eastus", _dt(2024,1,15), size="Standard_D2s_v3"),
            _r("/subscriptions/demo/resourceGroups/dev-rg/providers/Microsoft.Compute/virtualMachines/dev-vm-01",  "dev-vm-01", ResourceType.COMPUTE, ResourceState.STOPPED, "westus", _dt(2024,3,1),  size="Standard_B2s"),
        ],
        ResourceType.STORAGE: [
            _r("/subscriptions/demo/resourceGroups/prod-rg/providers/Microsoft.Storage/storageAccounts/prodstgacct", "prodstgacct", ResourceType.STORAGE, ResourceState.RUNNING, "eastus", _dt(2023,2,1), sku="Standard_LRS"),
            _r("/subscriptions/demo/resourceGroups/dev-rg/providers/Microsoft.Storage/storageAccounts/devstgacct",  "devstgacct",  ResourceType.STORAGE, ResourceState.RUNNING, "westus", _dt(2024,1,1), sku="Standard_LRS"),
        ],
        ResourceType.DATABASE: [
            _r("/subscriptions/demo/resourceGroups/prod-rg/providers/Microsoft.Sql/servers/prod-sql", "prod-sql", ResourceType.DATABASE, ResourceState.RUNNING, "eastus", _dt(2023,5,1), edition="Standard", service_objective="S2"),
        ],
        ResourceType.NETWORK: [
            _r("/subscriptions/demo/resourceGroups/prod-rg/providers/Microsoft.Network/virtualNetworks/prod-vnet", "prod-vnet", ResourceType.NETWORK, ResourceState.RUNNING, "eastus", _dt(2022,6,1), address_space="10.0.0.0/16"),
        ],
    },
    "digitalocean": {
        ResourceType.COMPUTE: [
            _r("123456001", "web-droplet-01",  ResourceType.COMPUTE, ResourceState.RUNNING, "nyc3", _dt(2024,1,10), size="s-2vcpu-4gb"),
            _r("123456002", "api-droplet-01",  ResourceType.COMPUTE, ResourceState.RUNNING, "nyc3", _dt(2024,1,10), size="s-4vcpu-8gb"),
            _r("123456003", "worker-droplet",  ResourceType.COMPUTE, ResourceState.RUNNING, "sfo3", _dt(2024,2,1),  size="s-2vcpu-2gb"),
            _r("123456004", "staging-droplet", ResourceType.COMPUTE, ResourceState.STOPPED, "nyc1", _dt(2024,3,15), size="s-1vcpu-1gb"),
        ],
        ResourceType.STORAGE: [
            _r("vol-abc123", "prod-data-volume",    ResourceType.STORAGE, ResourceState.RUNNING, "nyc3", _dt(2023,6,1), size_gb="100"),
            _r("vol-def456", "staging-data-volume", ResourceType.STORAGE, ResourceState.RUNNING, "nyc3", _dt(2024,1,1), size_gb="50"),
        ],
        ResourceType.CONTAINER: [
            _r("cluster-abc123", "prod-doks", ResourceType.CONTAINER, ResourceState.RUNNING, "nyc3", _dt(2023,9,1), kubernetes_version="1.29", node_count="3"),
        ],
    },
    "vultr": {
        ResourceType.COMPUTE: [
            _r("vultr-inst-001", "web-01",     ResourceType.COMPUTE, ResourceState.RUNNING, "ewr", _dt(2024,1,5),  plan="vc2-2c-4gb"),
            _r("vultr-inst-002", "api-01",     ResourceType.COMPUTE, ResourceState.RUNNING, "ewr", _dt(2024,1,5),  plan="vc2-4c-8gb"),
            _r("vultr-inst-003", "staging-01", ResourceType.COMPUTE, ResourceState.STOPPED, "lax", _dt(2024,3,1),  plan="vc2-1c-2gb"),
        ],
        ResourceType.STORAGE: [
            _r("vultr-blk-001", "prod-block-storage", ResourceType.STORAGE, ResourceState.RUNNING, "ewr", _dt(2023,11,1), size_gb="200"),
        ],
    },
    "oci": {
        ResourceType.COMPUTE: [
            _r("ocid1.instance.oc1.iad.demo001", "web-instance-01", ResourceType.COMPUTE, ResourceState.RUNNING, "us-ashburn-1", _dt(2024,2,1),  shape="VM.Standard.E4.Flex"),
            _r("ocid1.instance.oc1.iad.demo002", "api-instance-01", ResourceType.COMPUTE, ResourceState.RUNNING, "us-ashburn-1", _dt(2024,2,1),  shape="VM.Standard.E4.Flex"),
        ],
        ResourceType.STORAGE: [
            _r("ocid1.bucket.oc1.iad.demo001", "prod-object-storage", ResourceType.STORAGE, ResourceState.RUNNING, "us-ashburn-1", _dt(2023,6,1), storage_tier="Standard"),
            _r("ocid1.bucket.oc1.iad.demo002", "archive-storage",     ResourceType.STORAGE, ResourceState.RUNNING, "us-ashburn-1", _dt(2023,8,1), storage_tier="Archive"),
        ],
        ResourceType.NETWORK: [
            _r("ocid1.vcn.oc1.iad.demo001", "prod-vcn", ResourceType.NETWORK, ResourceState.RUNNING, "us-ashburn-1", _dt(2022,9,1), cidr="10.0.0.0/16"),
        ],
    },
    "alibaba": {
        ResourceType.COMPUTE: [
            _r("i-demo-ecs-001", "web-ecs-01",    ResourceType.COMPUTE, ResourceState.RUNNING, "cn-hangzhou", _dt(2024,1,10), instance_type="ecs.c7.large"),
            _r("i-demo-ecs-002", "worker-ecs-01", ResourceType.COMPUTE, ResourceState.RUNNING, "cn-hangzhou", _dt(2024,1,10), instance_type="ecs.g7.xlarge"),
        ],
        ResourceType.STORAGE: [
            _r("oss://demo-prod-bucket", "demo-prod-bucket", ResourceType.STORAGE, ResourceState.RUNNING, "cn-hangzhou", _dt(2023,3,1), storage_class="Standard"),
        ],
        ResourceType.DATABASE: [
            _r("rm-demo-rds-001", "prod-rds", ResourceType.DATABASE, ResourceState.RUNNING, "cn-hangzhou", _dt(2023,5,1), engine="MySQL", engine_version="8.0"),
        ],
    },
}

_DEMO = {
    pname: {
        rt: [r.model_copy(update={"provider": pname}) for r in resources]
        for rt, resources in type_map.items()
    }
    for pname, type_map in _DEMO.items()
}

_SUPPORTED_TYPES: dict[str, list[ResourceType]] = {
    name: list(types.keys()) for name, types in _DEMO.items()
}


class MockProvider(BaseProvider):
    """Drop-in provider that returns static demo data — no credentials needed."""

    def __init__(self, name: str, display_name: str) -> None:
        self._name = name
        self._display_name = display_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def supported_resource_types(self) -> list[ResourceType]:
        return _SUPPORTED_TYPES.get(self._name, [])

    async def authenticate(self) -> bool:
        return True

    async def is_authenticated(self) -> bool:
        return True

    async def list_resources(
        self,
        resource_type: ResourceType,
        region: str | None = None,
        tags: dict | None = None,
    ) -> list[Resource]:
        resources = _DEMO.get(self._name, {}).get(resource_type, [])
        if region:
            resources = [r for r in resources if r.region == region or region == ""]
        if tags:
            resources = [
                r for r in resources
                if all(r.tags.get(k) == v for k, v in tags.items())
            ]
        return resources

    async def get_resource(
        self,
        resource_type: ResourceType,
        resource_id: str,
        region: str | None = None,
    ) -> Resource:
        from spancloud.core.exceptions import ResourceNotFoundError
        for r in _DEMO.get(self._name, {}).get(resource_type, []):
            if r.id == resource_id:
                return r
        raise ResourceNotFoundError(self._name, resource_type.value, resource_id)

    async def get_status(self) -> dict[str, str]:
        return {"provider": self._name, "status": "mock", "mode": "demo"}
