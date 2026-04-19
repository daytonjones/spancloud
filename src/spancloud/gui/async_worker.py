"""QThread-based bridge for running async provider coroutines from Qt."""

from __future__ import annotations

import asyncio
from typing import Any, Coroutine

from PySide6.QtCore import QThread, Signal


class AsyncWorker(QThread):
    """Run a single async coroutine in a background thread.

    Usage::

        worker = AsyncWorker(provider.list_resources(ResourceType.COMPUTE))
        worker.result_ready.connect(self._on_resources)
        worker.error_occurred.connect(self._on_error)
        worker.start()
        self._workers.append(worker)   # keep a reference while running

    Signals are emitted on the GUI thread via Qt's queued-connection mechanism.
    """

    result_ready: Signal = Signal(object)
    error_occurred: Signal = Signal(str)

    def __init__(self, coro: Coroutine[Any, Any, Any]) -> None:
        super().__init__()
        self._coro = coro

    def run(self) -> None:
        try:
            result = asyncio.run(self._coro)
            self.result_ready.emit(result)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
