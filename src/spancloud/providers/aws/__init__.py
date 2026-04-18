"""Amazon Web Services provider for Skyforge."""

from skyforge.core.registry import registry
from skyforge.providers.aws.provider import AWSProvider

# Register the AWS provider on import.
_provider = AWSProvider()
registry.register(_provider)

__all__ = ["AWSProvider"]
