"""Google Cloud Platform provider for Skyforge."""

from skyforge.core.registry import registry
from skyforge.providers.gcp.provider import GCPProvider

# Register the GCP provider on import.
_provider = GCPProvider()
registry.register(_provider)

__all__ = ["GCPProvider"]
