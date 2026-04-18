"""GCP Cloud Run service resource discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from google.cloud.run_v2 import ServicesClient
from google.cloud.run_v2.types import ListServicesRequest

from spancloud.core.resource import Resource, ResourceState, ResourceType
from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from spancloud.providers.gcp.auth import GCPAuth

logger = get_logger(__name__)

# Cloud Run conditions determine state — the service itself doesn't have a simple status enum.
# We inspect the terminal_condition or reconciling field.


class CloudRunResources:
    """Handles GCP Cloud Run service discovery."""

    def __init__(self, auth: GCPAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_services(self, region: str | None = None) -> list[Resource]:
        """List all Cloud Run services in the project.

        Scans all regions using the '-' location wildcard, then filters
        by region if specified.

        Args:
            region: Optional region to filter by (e.g., 'us-central1').

        Returns:
            List of Resource objects representing Cloud Run services.
        """
        project = self._auth.project_id
        if not project:
            logger.warning("No GCP project ID configured — cannot list Cloud Run services")
            return []

        client = ServicesClient(credentials=self._auth.credentials)

        def _fetch() -> list[Any]:
            parent = f"projects/{project}/locations/-"
            request = ListServicesRequest(parent=parent)
            services: list[Any] = []
            for svc in client.list_services(request=request):
                services.append(svc)
            return services

        raw_services = await asyncio.to_thread(_fetch)

        resources: list[Resource] = []
        for svc in raw_services:
            svc_region = self._extract_region(svc.name or "")
            if region and svc_region != region:
                continue
            resources.append(self._map_service(svc, svc_region))

        logger.debug("Found %d Cloud Run services", len(resources))
        return resources

    def _extract_region(self, name: str) -> str:
        """Extract region from service resource name.

        Format: projects/{project}/locations/{region}/services/{name}
        """
        parts = name.split("/")
        if len(parts) >= 4:
            return parts[3]
        return ""

    def _map_service(self, svc: Any, region: str) -> Resource:
        """Map a Cloud Run service to a unified Resource."""
        labels = dict(svc.labels) if svc.labels else {}

        # Extract short name from full resource name
        svc_name = svc.name.rsplit("/", 1)[-1] if svc.name else ""

        # Determine state from conditions
        state = self._determine_state(svc)

        # Extract container config from the template
        image = ""
        memory = ""
        cpu = ""
        max_instances = ""
        min_instances = ""
        if svc.template and svc.template.containers:
            container = svc.template.containers[0]
            image = container.image or ""
            if container.resources and container.resources.limits:
                limits = container.resources.limits
                memory = limits.get("memory", "")
                cpu = limits.get("cpu", "")
        if svc.template and svc.template.scaling:
            max_instances = str(svc.template.scaling.max_instance_count or "")
            min_instances = str(svc.template.scaling.min_instance_count or "")

        return Resource(
            id=svc_name,
            name=svc_name,
            resource_type=ResourceType.SERVERLESS,
            provider="gcp",
            region=region,
            state=state,
            created_at=svc.create_time,
            tags=labels,
            metadata={
                "uri": svc.uri or "",
                "image": image,
                "memory": memory,
                "cpu": cpu,
                "max_instances": max_instances,
                "min_instances": min_instances,
                "ingress": svc.ingress.name if svc.ingress else "",
                "launch_stage": svc.launch_stage.name if svc.launch_stage else "",
                "resource_subtype": "cloud_run_service",
            },
        )

    def _determine_state(self, svc: Any) -> ResourceState:
        """Determine the service state from its conditions.

        Cloud Run uses a condition-based model. The terminal condition
        tells us whether the service is ready.
        """
        if svc.reconciling:
            return ResourceState.PENDING

        terminal = svc.terminal_condition
        if terminal:
            if terminal.state and terminal.state.name == "CONDITION_SUCCEEDED":
                return ResourceState.RUNNING
            if terminal.state and terminal.state.name == "CONDITION_FAILED":
                return ResourceState.ERROR

        # Fallback: check conditions list
        for condition in svc.conditions or []:
            if condition.type_ == "Ready":
                if condition.state and condition.state.name == "CONDITION_SUCCEEDED":
                    return ResourceState.RUNNING
                return ResourceState.PENDING

        return ResourceState.UNKNOWN
