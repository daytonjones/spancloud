"""Retry logic with exponential backoff for cloud API calls."""

from __future__ import annotations

import asyncio
import functools
import random
from typing import TYPE_CHECKING, ParamSpec, TypeVar

from spancloud.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    non_retryable_if: Callable[[Exception], bool] | None = None,
) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """Decorator that retries an async function with exponential backoff.

    Designed to limit incurred cloud costs by throttling retries and
    avoiding thundering-herd effects with jitter.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds before the first retry.
        max_delay: Cap on the delay between retries.
        jitter: Whether to add random jitter to the delay.
        retryable_exceptions: Exception types that trigger a retry.
        non_retryable_if: Optional predicate; if it returns True for an
            exception the error is raised immediately without any retries.

    Returns:
        Decorated async function with retry behavior.
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception: Exception | None = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as exc:
                    last_exception = exc

                    if non_retryable_if is not None and non_retryable_if(exc):
                        raise

                    if attempt == max_retries:
                        logger.error(
                            "All %d retries exhausted for %s: %s",
                            max_retries,
                            func.__name__,
                            exc,
                        )
                        raise

                    delay = min(base_delay * (2**attempt), max_delay)
                    if jitter:
                        delay = delay * (0.5 + random.random() * 0.5)  # noqa: S311

                    logger.warning(
                        "Retry %d/%d for %s after %.1fs: %s",
                        attempt + 1,
                        max_retries,
                        func.__name__,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)

            # Unreachable, but keeps type checkers happy
            assert last_exception is not None  # noqa: S101
            raise last_exception

        return wrapper

    return decorator
