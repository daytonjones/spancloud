"""Pre-built retry decorators for Azure service calls.

All variants skip retries on permanent errors (subscription not found,
resource not found) that will never succeed without a configuration change.
"""

from __future__ import annotations

from spancloud.utils.retry import retry_with_backoff

_PERMANENT_AZURE_MARKERS = (
    "does not exist",
    "SubscriptionNotFound",
    "InvalidSubscriptionId",
    "ResourceNotFound",
    "ResourceGroupNotFound",
    "NoRegisteredProviderFound",
    "MissingSubscriptionRegistration",
)


def _is_permanent_azure_error(exc: Exception) -> bool:
    s = str(exc)
    return any(m in s for m in _PERMANENT_AZURE_MARKERS)


# Standard Azure retry — short backoff, skip permanent errors
AZURE_RETRY = retry_with_backoff(
    max_retries=2,
    base_delay=0.5,
    non_retryable_if=_is_permanent_azure_error,
)
AZURE_RETRY_SLOW = retry_with_backoff(
    max_retries=2,
    base_delay=2.0,
    non_retryable_if=_is_permanent_azure_error,
)
AZURE_RETRY_ACTION = retry_with_backoff(
    max_retries=2,
    base_delay=1.0,
    non_retryable_if=_is_permanent_azure_error,
)
