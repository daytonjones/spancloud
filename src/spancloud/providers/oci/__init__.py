"""Oracle Cloud Infrastructure provider for Spancloud."""

from spancloud.core.registry import registry
from spancloud.providers.oci.provider import OCIProvider

_provider = OCIProvider()
registry.register(_provider)

__all__ = ["OCIProvider"]
