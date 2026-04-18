"""Vultr provider for Spancloud."""

from spancloud.core.registry import registry
from spancloud.providers.vultr.provider import VultrProvider

_provider = VultrProvider()
registry.register(_provider)

__all__ = ["VultrProvider"]
