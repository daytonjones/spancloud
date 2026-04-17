"""Core abstractions for Skyforge providers and resources."""

from skyforge.core.exceptions import (
    AuthenticationError,
    ProviderError,
    ResourceNotFoundError,
    SkyforgeError,
)
from skyforge.core.provider import BaseProvider
from skyforge.core.registry import ProviderRegistry, registry
from skyforge.core.resource import Resource, ResourceState, ResourceType

__all__ = [
    "AuthenticationError",
    "BaseProvider",
    "ProviderError",
    "ProviderRegistry",
    "Resource",
    "ResourceNotFoundError",
    "ResourceState",
    "ResourceType",
    "SkyforgeError",
    "registry",
]
