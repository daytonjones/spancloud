"""Cloud provider implementations.

Importing this module registers all available providers with the global registry.
"""

from spancloud.providers import alibaba, aws, azure, digitalocean, gcp, oci, vultr

__all__ = ["alibaba", "aws", "azure", "digitalocean", "gcp", "oci", "vultr"]
