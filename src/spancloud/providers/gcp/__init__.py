"""Google Cloud Platform provider for Spancloud."""

from spancloud.core.registry import registry
from spancloud.providers.gcp.provider import GCPProvider

# Register the GCP provider on import.
_provider = GCPProvider()
registry.register(_provider)

__all__ = ["GCPProvider"]
