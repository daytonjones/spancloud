"""Vultr provider for Skyforge."""

from skyforge.core.registry import registry
from skyforge.providers.vultr.provider import VultrProvider

_provider = VultrProvider()
registry.register(_provider)

__all__ = ["VultrProvider"]
