"""Amazon Web Services provider for Spancloud."""

from spancloud.core.registry import registry
from spancloud.providers.aws.provider import AWSProvider

# Register the AWS provider on import.
_provider = AWSProvider()
registry.register(_provider)

__all__ = ["AWSProvider"]
