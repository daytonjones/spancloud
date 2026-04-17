"""Abstract base class defining the cloud provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skyforge.core.resource import Resource, ResourceType


class BaseProvider(ABC):
    """Interface that all cloud provider implementations must follow.

    Each provider handles authentication, resource discovery, and resource
    management for a single cloud platform. Providers are registered in the
    global registry and discovered at runtime.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this provider (e.g., 'aws', 'gcp')."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable provider name (e.g., 'Amazon Web Services')."""

    @property
    @abstractmethod
    def supported_resource_types(self) -> list[ResourceType]:
        """Resource types this provider can manage."""

    @abstractmethod
    async def authenticate(self) -> bool:
        """Verify credentials and establish a session.

        Returns:
            True if authentication succeeded, False otherwise.
        """

    @abstractmethod
    async def is_authenticated(self) -> bool:
        """Check whether the provider currently has valid credentials."""

    @abstractmethod
    async def list_resources(
        self,
        resource_type: ResourceType,
        region: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> list[Resource]:
        """List all resources of a given type.

        Args:
            resource_type: The category of resources to list.
            region: Optional region filter. If None, uses the default region.
            tags: Optional tag filter. Only return resources matching all tags.

        Returns:
            List of Resource objects.
        """

    @abstractmethod
    async def get_resource(
        self,
        resource_type: ResourceType,
        resource_id: str,
        region: str | None = None,
    ) -> Resource:
        """Fetch a single resource by ID.

        Args:
            resource_type: The category of the resource.
            resource_id: Provider-specific resource identifier.
            region: Optional region hint to speed up lookup.

        Returns:
            The matching Resource.

        Raises:
            ResourceNotFoundError: If the resource does not exist.
        """

    async def get_status(self) -> dict[str, str]:
        """Return a summary of provider health and connectivity.

        Returns:
            Dictionary with status information (e.g., authenticated, region, account).
        """
        authenticated = await self.is_authenticated()
        return {
            "provider": self.name,
            "display_name": self.display_name,
            "authenticated": str(authenticated),
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
