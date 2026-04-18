"""Digital Ocean provider for Spancloud."""

from spancloud.core.registry import registry
from spancloud.providers.digitalocean.provider import DigitalOceanProvider

_provider = DigitalOceanProvider()
registry.register(_provider)

__all__ = ["DigitalOceanProvider"]
