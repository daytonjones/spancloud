"""Structured logging setup using rich."""

from __future__ import annotations

import logging

from rich.logging import RichHandler


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


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for a Spancloud module.

    Args:
        name: Typically ``__name__`` from the calling module.

    Returns:
        A configured logger instance.
    """
    return logging.getLogger(name)
