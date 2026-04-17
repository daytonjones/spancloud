"""Alibaba Cloud provider for Skyforge."""

from skyforge.core.registry import registry
from skyforge.providers.alibaba.provider import AlibabaCloudProvider

_provider = AlibabaCloudProvider()
registry.register(_provider)

__all__ = ["AlibabaCloudProvider"]
