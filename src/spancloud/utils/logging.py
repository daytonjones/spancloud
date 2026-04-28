"""Structured logging setup using rich."""

from __future__ import annotations

import logging

from rich.logging import RichHandler


class _GoogleApiFilter(logging.Filter):
    """Suppress googleapiclient HTTP warnings for permanent GCP errors.

    The google-api-python-client library logs "Encountered 403 Forbidden with
    reason accessNotConfigured" at WARNING for APIs not enabled in a project.
    We already handle this gracefully in our retry logic, so suppress the
    redundant library-level log.
    """

    _SUPPRESS = ("accessNotConfigured", "SERVICE_DISABLED", "has not been used in project")

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
