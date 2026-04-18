"""Microsoft Azure provider for Spancloud."""

from spancloud.core.registry import registry
from spancloud.providers.azure.provider import AzureProvider

_provider = AzureProvider()
registry.register(_provider)

__all__ = ["AzureProvider"]
