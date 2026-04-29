"""OCI retry decorators — skip retries on permanent auth/config errors."""

from __future__ import annotations

from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

_logger = get_logger("spancloud.oci")

_PERMANENT_CODES = {"NotAuthenticated", "NotAuthorized", "InvalidParameter", "NotFound"}
_PERMANENT_STATUSES = {401, 404}


_warned_401: bool = False  # module-level dedup flag


def _is_permanent_oci_error(exc: Exception) -> bool:
    """Return True for errors that will never succeed on retry."""
    global _warned_401
    info = exc.args[0] if exc.args and isinstance(exc.args[0], dict) else {}
    status = info.get("status", 0)
    code = info.get("code", "")
    if status in _PERMANENT_STATUSES or code in _PERMANENT_CODES:
        if (status == 401 or code == "NotAuthenticated") and not _warned_401:
            _warned_401 = True
            _logger.warning(
                "OCI authentication rejected (401). Check that your API key in "
                "~/.oci/config is current and the system clock is correct "
                "(OCI requires clock within 5 minutes of server time). "
                "Re-run: spancloud auth login oci"
            )
        return True
    return False


def _fmt(exc: Exception) -> str:
    """Format an OCI exception dict as a concise one-liner."""
    info = exc.args[0] if exc.args and isinstance(exc.args[0], dict) else {}
    if info:
        parts = []
        if info.get("status"):
            parts.append(f"{info['status']}")
        if info.get("code"):
            parts.append(info["code"])
        if info.get("message"):
            parts.append(info["message"])
        if info.get("operation_name"):
            parts.append(f"op={info['operation_name']}")
        return " | ".join(parts) if parts else str(exc)
    return str(exc)


OCI_RETRY = retry_with_backoff(
    max_retries=2,
    base_delay=0.5,
    non_retryable_if=_is_permanent_oci_error,
)

OCI_RETRY_SLOW = retry_with_backoff(
    max_retries=2,
    base_delay=2.0,
    non_retryable_if=_is_permanent_oci_error,
)
