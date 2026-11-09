"""Lock helpers for router control and its non-blocking status polls."""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, TypeVar

_T = TypeVar("_T")


def locked(method: Callable[..., _T]) -> Callable[..., _T]:
    """Run a router-control method while it holds its re-entrant lock."""

    @functools.wraps(method)
    def run(self: Any, *args: Any, **kwargs: Any) -> _T:
        with self._lock:
            return method(self, *args, **kwargs)

    return run


@contextmanager
def wait_section(lock: threading.RLock) -> Iterator[bool]:
    """Guard a status read without blocking on a Start's join for 3 minutes.

    Tries to acquire the lock with a 50 ms timeout. A status call during a slow
    join (health check, up to 180 s) waits at most 50 ms and then reads current
    state without clearing the wait flag. The next poll acquires normally.

    Yields whether this call acquired the lock.
    """
    acquired = lock.acquire(timeout=0.05)
    try:
        yield acquired
    finally:
        if acquired:
            lock.release()
