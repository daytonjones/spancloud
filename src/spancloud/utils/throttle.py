"""Async rate limiter and concurrency throttle for cloud API calls.

Prevents throttling errors and minimizes costs by controlling how fast
we hit provider APIs. Uses a token-bucket algorithm with configurable
burst and sustained rates.
"""

from __future__ import annotations

import asyncio
import time

from spancloud.utils.logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Token-bucket rate limiter for async API calls.

    Limits concurrent requests and enforces a sustained request rate.
    Use as an async context manager around API calls.

    Example::

        limiter = RateLimiter(calls_per_second=5.0, max_concurrency=10)
        async with limiter:
            await some_api_call()

    asyncio primitives are created lazily and re-created whenever the running
    event loop changes (e.g. across multiple asyncio.run() calls in the GUI's
    AsyncWorker threads).
    """

    def __init__(
        self,
        calls_per_second: float = 5.0,
        max_concurrency: int = 10,
    ) -> None:
        """Initialize the rate limiter.

        Args:
            calls_per_second: Maximum sustained request rate.
            max_concurrency: Maximum number of in-flight requests.
        """
        self._interval = 1.0 / calls_per_second
        self._max_concurrency = max_concurrency
        self._semaphore: asyncio.Semaphore | None = None
        self._lock: asyncio.Lock | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_call: float = 0.0

    def _ensure_primitives(self) -> tuple[asyncio.Semaphore, asyncio.Lock]:
        """Return primitives valid for the current event loop, creating new ones if needed."""
        try:
            loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not self._loop or self._semaphore is None or self._lock is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrency)
            self._lock = asyncio.Lock()
            self._loop = loop
        return self._semaphore, self._lock

    async def acquire(self) -> None:
        """Wait until a request slot is available."""
        sem, lock = self._ensure_primitives()
        await sem.acquire()
        async with lock:
            now = time.monotonic()
            wait = self._last_call + self._interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

    def release(self) -> None:
        """Release a request slot."""
        if self._semaphore is not None:
            self._semaphore.release()

    async def __aenter__(self) -> RateLimiter:
        await self.acquire()
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.release()


async def run_in_batches(
    items: list,
    batch_fn,
    batch_size: int = 20,
    limiter: RateLimiter | None = None,
) -> list:
    """Process items in batches with rate limiting.

    Useful for APIs that support batch requests or when you want
    to limit the number of concurrent individual requests.

    Args:
        items: Items to process.
        batch_fn: Async function taking a batch (list) and returning results (list).
        batch_size: Number of items per batch.
        limiter: Optional rate limiter for each batch call.

    Returns:
        Combined results from all batches.
    """
    results: list = []
    for i in range(0, len(items), batch_size):
        batch = items[i : i + batch_size]
        if limiter:
            async with limiter:
                batch_results = await batch_fn(batch)
        else:
            batch_results = await batch_fn(batch)
        results.extend(batch_results)
    return results
