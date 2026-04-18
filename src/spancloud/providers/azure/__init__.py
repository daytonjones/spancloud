"""Microsoft Azure provider for Skyforge."""

from skyforge.core.registry import registry
from skyforge.providers.azure.provider import AzureProvider

_provider = AzureProvider()
registry.register(_provider)

__all__ = ["AzureProvider"]
