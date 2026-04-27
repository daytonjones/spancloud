"""Pre-built retry decorators for GCP service calls.

All variants skip retries on permanent 403s (SERVICE_DISABLED /
accessNotConfigured) since those won't resolve without manual intervention.
"""

from __future__ import annotations

from spancloud.utils.retry import retry_with_backoff

_PERMANENT_403_MARKERS = (
    "SERVICE_DISABLED",
    "accessNotConfigured",
    "has not been used in project",
    "it is disabled",
)


def _is_permanent_gcp_error(exc: Exception) -> bool:
    msg = str(exc)
    return any(marker in msg for marker in _PERMANENT_403_MARKERS)


# Drop-in replacements for the two parameter sets used across GCP modules
GCP_RETRY = retry_with_backoff(
    max_retries=3,
    base_delay=1.0,
    non_retryable_if=_is_permanent_gcp_error,
)
GCP_RETRY_SLOW = retry_with_backoff(
    max_retries=2,
    base_delay=2.0,
    non_retryable_if=_is_permanent_gcp_error,
)
GCP_RETRY_FAST = retry_with_backoff(
    max_retries=2,
    base_delay=1.0,
    non_retryable_if=_is_permanent_gcp_error,
)
