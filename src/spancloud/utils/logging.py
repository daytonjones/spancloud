"""Structured logging setup using rich."""

from __future__ import annotations

import logging

from rich.logging import RichHandler


class _GoogleApiFilter(logging.Filter):
    """Suppress and reformat googleapiclient HTTP 403 warnings.

    The google-api-python-client library logs bare "Encountered 403 Forbidden
    with reason X" messages that contain no actionable detail. We suppress
    these and let our own code emit friendlier messages with guidance.
    """

    _SUPPRESS = (
        "accessNotConfigured",
        "SERVICE_DISABLED",
        "has not been used in project",
        "PERMISSION_DENIED",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        # All suppressed cases are re-logged with better messages by _retry.py
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
    # Silence redundant googleapiclient HTTP warnings we already handle
    logging.getLogger("googleapiclient.http").addFilter(_GoogleApiFilter())
    logging.getLogger("googleapiclient.discovery").addFilter(_GoogleApiFilter())


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for a Spancloud module.

    Args:
        name: Typically ``__name__`` from the calling module.

    Returns:
        A configured logger instance.
    """
    return logging.getLogger(name)
