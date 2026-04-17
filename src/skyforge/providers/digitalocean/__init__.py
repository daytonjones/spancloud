"""Digital Ocean provider for Skyforge."""

from skyforge.core.registry import registry
from skyforge.providers.digitalocean.provider import DigitalOceanProvider

_provider = DigitalOceanProvider()
registry.register(_provider)

__all__ = ["DigitalOceanProvider"]
