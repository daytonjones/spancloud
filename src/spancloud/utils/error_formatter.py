"""Human-readable error messages for common cloud API errors."""

from __future__ import annotations

import re

_PERMANENT_GCP_MARKERS = (
    "SERVICE_DISABLED",
    "accessNotConfigured",
    "has not been used in project",
)

_PERMANENT_AZURE_MARKERS = (
    "does not exist",
    "SubscriptionNotFound",
    "InvalidSubscriptionId",
    "ResourceNotFound",
    "ResourceGroupNotFound",
    "MissingSubscriptionRegistration",
    "NoRegisteredProviderFound",
)

_QUOTA_MARKERS = (
    "RESOURCE_EXHAUSTED",
    "rateLimitExceeded",
    "quota",
)


def is_permanent_api_error(exc: Exception) -> bool:
    """Return True if exc is a permanent provider configuration error."""
    s = str(exc)
    return any(m in s for m in _PERMANENT_GCP_MARKERS) or any(m in s for m in _PERMANENT_AZURE_MARKERS)


def friendly_error(raw: Exception | str) -> str:
    """Return a concise, human-readable error string.

    Detects well-known API-disabled, quota, and auth patterns and formats
    them cleanly.  Falls back to the first line of the raw message.
    """
    s = str(raw)

    if any(m in s for m in _PERMANENT_GCP_MARKERS):
        m = re.search(r"([\w\s]+API) has not been used", s)
        svc = m.group(1).strip() if m else "A required GCP API"
        return (
            f"{svc} is not enabled for this project — "
            "enable it in GCP Console → APIs & Services."
        )

    if any(m in s for m in _PERMANENT_AZURE_MARKERS):
        if "does not exist" in s or "SubscriptionNotFound" in s or "InvalidSubscriptionId" in s:
            return (
                "Azure subscription not found — check the subscription ID "
                "in your azure.env or run `spancloud auth login azure` again."
            )
        return f"Azure resource not found: {s.splitlines()[0][:120]}"

    if any(m in s for m in _QUOTA_MARKERS) or "quota" in s.lower():
        return (
            "Quota exceeded or rate-limited — "
            "request an increase in the provider console."
        )

    if "403" in s and any(k in s for k in ("PERMISSION_DENIED", "Forbidden", "PermissionDenied", "AuthorizationFailed")):
        return "Permission denied — check that your account has the required IAM/RBAC roles."

    if "401" in s or "unauthenticated" in s.lower():
        return "Authentication error — run `spancloud auth login` for this provider."

    first_line = next((line.strip() for line in s.splitlines() if line.strip()), s)
    return first_line[:200] + ("…" if len(first_line) > 200 else "")
