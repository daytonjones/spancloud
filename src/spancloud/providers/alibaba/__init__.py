"""Alibaba Cloud provider for Spancloud."""

from spancloud.core.registry import registry
from spancloud.providers.alibaba.provider import AlibabaCloudProvider

_provider = AlibabaCloudProvider()
registry.register(_provider)

__all__ = ["AlibabaCloudProvider"]
