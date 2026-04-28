"""Pre-built retry decorators for GCP service calls.

All variants skip retries on permanent 403s (SERVICE_DISABLED /
accessNotConfigured) since those won't resolve without manual intervention.
"""

from __future__ import annotations

import re

from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

_PERMANENT_403_MARKERS = (
    "SERVICE_DISABLED",
    "accessNotConfigured",
    "has not been used in project",
    "it is disabled",
)

_logger = get_logger("spancloud.gcp")

# Patterns to extract the API name and the enable URL from the HttpError body
_API_NAME_RE = re.compile(r"([\w\s]+API) has not been used")
_ENABLE_URL_RE = re.compile(r"https://console\.developers\.google\.com/apis/api/[^\s\"']+")


def _is_permanent_gcp_error(exc: Exception) -> bool:
    msg = str(exc)
    if not any(marker in msg for marker in _PERMANENT_403_MARKERS):
        return False

    name_match = _API_NAME_RE.search(msg)
    url_match = _ENABLE_URL_RE.search(msg)
    api_name = name_match.group(1).strip() if name_match else "A required GCP API"
    if url_match:
        _logger.warning(
            "%s is not enabled for this project. Enable it at: %s",
            api_name,
            url_match.group(0).rstrip(").,"),
        )
    else:
        _logger.warning(
            "%s is not enabled for this project — enable it in "
            "GCP Console → APIs & Services → Library.",
            api_name,
        )
    return True


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
