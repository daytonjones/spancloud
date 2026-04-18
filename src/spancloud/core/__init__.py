"""Core abstractions for Spancloud providers and resources."""

from spancloud.core.exceptions import (
    AuthenticationError,
    ProviderError,
    ResourceNotFoundError,
    SpancloudError,
)
from spancloud.core.provider import BaseProvider
from spancloud.core.registry import ProviderRegistry, registry
from spancloud.core.resource import Resource, ResourceState, ResourceType

__all__ = [
    "AuthenticationError",
    "BaseProvider",
    "ProviderError",
    "ProviderRegistry",
    "Resource",
    "ResourceNotFoundError",
    "ResourceState",
    "ResourceType",
    "SpancloudError",
    "registry",
]
