"""Structured logging setup using rich."""

from __future__ import annotations

import logging
import warnings

from rich.logging import RichHandler


class _BotocoreFilter(logging.Filter):
    """Suppress botocore SSO token-refresh noise.

    botocore emits WARNING + full traceback for every region when an SSO token
    has expired. Our AWS auth code catches the underlying exception and emits a
    single clean 'AWS authentication failed' message, so these are redundant.
    """

    _SUPPRESS = (
        "SSO token refresh attempt failed",
        "Refreshing temporary credentials failed",
        "Token has expired and refresh failed",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(m in msg for m in self._SUPPRESS)


class _GoogleApiFilter(logging.Filter):
    """Suppress noisy google-api / google-auth library warnings.

    Covers:
    - googleapiclient 403s (accessNotConfigured, PERMISSION_DENIED, etc.)
      — re-logged with actionable guidance by our retry/cost modules.
    - google.auth GCE metadata server timeouts — expected on non-GCE machines;
      our own 'GCP authentication failed' message is the actionable one.
    - google.auth 'No project ID could be determined' — our GCPAuth warning
      covers this with provider-specific guidance.
    """

    _SUPPRESS = (
        # googleapiclient 403 variants (re-logged by our code)
        "accessNotConfigured",
        "SERVICE_DISABLED",
        "has not been used in project",
        "PERMISSION_DENIED",
        # google.auth GCE metadata noise on non-GCE machines
        "Compute Engine Metadata server unavailable",
        "Authentication failed using Compute Engine",
        # google.auth project-detection noise (our GCPAuth warning covers it)
        "No project ID could be determined",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(m in msg for m in self._SUPPRESS)


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger with rich formatting.

    Args:
        level: Logging level name (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    logging.basicConfig(
        level=level.upper(),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                rich_tracebacks=True,
                show_path=False,
                markup=True,
            )
        ],
    )
    # Silence redundant botocore SSO noise — our AWS auth emits a single clean message
    _bf = _BotocoreFilter()
    for logger_name in ("botocore.tokens", "botocore.credentials"):
        logging.getLogger(logger_name).addFilter(_bf)

    # Silence redundant google library warnings — our code emits better ones
    _f = _GoogleApiFilter()
    for logger_name in (
        "googleapiclient.http",
        "googleapiclient.discovery",
        "google.auth.compute_engine._metadata",
        "google.auth._default",
        "google.auth.transport.requests",
    ):
        logging.getLogger(logger_name).addFilter(_f)

    # Suppress the quota-project UserWarning from google.auth._default
    # (a warnings.warn call, not logging — needs a separate filter)
    warnings.filterwarnings(
        "ignore",
        message=".*quota project.*",
        category=UserWarning,
        module="google.auth.*",
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for a Spancloud module.

    Args:
        name: Typically ``__name__`` from the calling module.

    Returns:
        A configured logger instance.
    """
    return logging.getLogger(name)
