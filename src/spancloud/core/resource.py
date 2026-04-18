"""Resource models representing cloud infrastructure objects."""

from __future__ import annotations

from datetime import datetime  # noqa: TCH003 — pydantic needs this at runtime
from enum import StrEnum

from pydantic import BaseModel, Field


class ResourceType(StrEnum):
    """Categories of cloud resources Skyforge can manage."""

    COMPUTE = "compute"
    STORAGE = "storage"
    NETWORK = "network"
    DATABASE = "database"
    CONTAINER = "container"
    SERVERLESS = "serverless"
    IAM = "iam"
    DNS = "dns"
    LOAD_BALANCER = "load_balancer"
    OTHER = "other"


class ResourceState(StrEnum):
    """Lifecycle state of a cloud resource."""

    RUNNING = "running"
    STOPPED = "stopped"
    PENDING = "pending"
    TERMINATED = "terminated"
    ERROR = "error"
    UNKNOWN = "unknown"


class Resource(BaseModel):
    """Unified representation of a cloud resource across providers."""

    id: str = Field(description="Provider-specific resource identifier")
    name: str = Field(description="Human-readable resource name")
    resource_type: ResourceType = Field(description="Category of the resource")
    provider: str = Field(description="Cloud provider name (e.g., 'aws', 'gcp')")
    region: str = Field(default="", description="Region or location where the resource lives")
    state: ResourceState = Field(default=ResourceState.UNKNOWN, description="Current state")
    created_at: datetime | None = Field(default=None, description="When the resource was created")
    tags: dict[str, str] = Field(default_factory=dict, description="Key-value tags/labels")
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="Provider-specific metadata that doesn't map to standard fields",
    )

    @property
    def display_name(self) -> str:
        """Return the best human-readable identifier."""
        return self.name or self.id

    def __str__(self) -> str:
        return (
            f"{self.provider}:{self.resource_type.value}"
            f"/{self.display_name} ({self.state.value})"
        )
