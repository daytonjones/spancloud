"""Oracle Cloud Infrastructure provider for Skyforge."""

from skyforge.core.registry import registry
from skyforge.providers.oci.provider import OCIProvider

_provider = OCIProvider()
registry.register(_provider)

__all__ = ["OCIProvider"]
