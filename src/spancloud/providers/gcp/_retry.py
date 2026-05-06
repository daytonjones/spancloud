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
    "PERMISSION_DENIED",
)

_logger = get_logger("spancloud.gcp")

_API_NAME_RE = re.compile(r"([\w\s]+API) has not been used")
_ENABLE_URL_RE = re.compile(r"https://console\.developers\.google\.com/apis/api/[^\s\"']+")

# Map URL hostname fragment → (human name, required IAM role)
_IAM_ROLE_MAP: list[tuple[str, str, str]] = [
    ("bigquery",              "BigQuery",              "roles/bigquery.dataViewer + roles/bigquery.jobUser"),
    ("cloudbilling",          "Cloud Billing",         "roles/billing.viewer"),
    ("cloudresourcemanager",  "Cloud Resource Manager","roles/resourcemanager.projectViewer"),
    ("compute",               "Compute Engine",        "roles/compute.viewer"),
    ("storage",               "Cloud Storage",         "roles/storage.objectViewer"),
    ("run",                   "Cloud Run",             "roles/run.viewer"),
    ("cloudfunctions",        "Cloud Functions",       "roles/cloudfunctions.viewer"),
    ("sqladmin",              "Cloud SQL",             "roles/cloudsql.viewer"),
    ("container",             "Kubernetes Engine",     "roles/container.viewer"),
    ("dns",                   "Cloud DNS",             "roles/dns.reader"),
    ("monitoring",            "Cloud Monitoring",      "roles/monitoring.viewer"),
    ("cloudkms",              "Cloud KMS",             "roles/cloudkms.viewer"),
]

_URL_RE = re.compile(r"requesting (https://[^\s\"']+)")


_PERMANENT_AUTH_MARKERS = (
    "Reauthentication is needed",
    "Please run `gcloud auth application-default login`",
)


def _is_permanent_gcp_error(exc: Exception) -> bool:
    msg = str(exc)

    # Expired ADC token — retrying never helps; user must re-login interactively.
    # Treat as permanent so we fail on the first attempt (no backoff noise).
    if any(marker in msg for marker in _PERMANENT_AUTH_MARKERS):
        _logger.warning(
            "GCP credentials have expired — run: gcloud auth application-default login"
        )
        return True

    if not any(marker in msg for marker in _PERMANENT_403_MARKERS):
        return False

    if "PERMISSION_DENIED" in msg:
        url_match = _URL_RE.search(msg)
        if url_match:
            url = url_match.group(1)
            for fragment, svc_name, role in _IAM_ROLE_MAP:
                if fragment in url:
                    _logger.warning(
                        "GCP permission denied for %s — grant your account '%s' "
                        "in GCP Console → IAM & Admin.",
                        svc_name, role,
                    )
                    return True
        _logger.warning(
            "GCP permission denied — your account is missing an IAM role. "
            "Check GCP Console → IAM & Admin."
        )
        return True

    # API not enabled
    name_match = _API_NAME_RE.search(msg)
    url_match = _ENABLE_URL_RE.search(msg)
    api_name = name_match.group(1).strip() if name_match else "A required GCP API"
    if url_match:
        _logger.warning(
            "%s is not enabled for this project. Enable it at: %s",
            api_name, url_match.group(0).rstrip(").,"),
        )
    else:
        _logger.warning(
            "%s is not enabled — enable it in GCP Console → APIs & Services → Library.",
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
