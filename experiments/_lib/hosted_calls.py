"""The shared gate for hosted calls in the Experiment 35 harness (design D1, D2).

One :class:`HostedGate` serves one role (answers, the ``chat`` judge or the
Ragas judge). It holds the in-flight limit of the role, waits on a rate limit
and stops the stage cleanly when waiting cannot help::

    gate = HostedGate("answer", 16, attempts=6)
    result = await gate.call(lambda: engine.answer(question))

A call is rate-limited when it raises an error whose ``status_code`` is 429 or
402, or when it returns an answer result that carries the OMRS
``rate_limited`` record. The gate never reads error text. The wait is the
``Retry-After`` time (or ``retry-after-ms``, or the record's
``retry_after_seconds``); without one it is a backoff of base 5 s, factor 2,
cap 120 s, with equal jitter. The gate raises :class:`RateLimitStop` at once
for an out-of-credit reply (HTTP 402 with no ``Retry-After``) or a wait above
600 s, and after the last attempt. Any other error passes through unchanged.

The wait happens outside the in-flight slot, so a waiting call does not hold
back the other calls of the role.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar

__all__ = ["HostedGate", "RateLimit", "RateLimitStop", "classify"]

T = TypeVar("T")

RATE_LIMIT = "rate_limit"
OUT_OF_CREDIT = "out_of_credit"
MAX_WAIT_SECONDS = 600.0
BACKOFF_BASE_SECONDS = 5.0
BACKOFF_FACTOR = 2.0
BACKOFF_CAP_SECONDS = 120.0
DEFAULT_ATTEMPTS = 6


class RateLimitStop(RuntimeError):
    """The stage must stop: the account is out of credit, a wait is too long, or attempts ran out.

    The stage keeps the results that finished, writes no done-marker and exits
    with the rate-limit exit code. A later ``--resume`` sends the call again.
    """


@dataclass(frozen=True)
class RateLimit:
    """One rate-limit reply.

    Attributes:
        kind: ``rate_limit`` or ``out_of_credit``.
        http_status: 429 or 402.
        retry_after_seconds: The wait the provider asked for, or None.
    """

    kind: str
    http_status: int | None
    retry_after_seconds: float | None


def _header(headers: Any, name: str) -> str | None:
    if not hasattr(headers, "items"):
        return None
    for key, value in headers.items():
        if str(key).lower() == name:
            return str(value)
    return None


def _retry_after(exc: BaseException) -> float | None:
    headers = getattr(getattr(exc, "response", None), "headers", None)
    milliseconds = _header(headers, "retry-after-ms")
    seconds = _header(headers, "retry-after")
    try:
        if milliseconds is not None:
            return float(milliseconds) / 1000.0
        if seconds is not None:
            return float(seconds)
    except ValueError:
        return None
    return None


def classify(outcome: BaseException | Mapping[str, Any]) -> RateLimit | None:
    """Return the rate limit that *outcome* shows, or None.

    Args:
        outcome: An exception a call raised, or the result a call returned.

    Returns:
        The rate limit, or None when *outcome* is not one. Error text is never read.
    """
    if isinstance(outcome, Mapping):
        record = outcome.get("rate_limited")
        if not isinstance(record, Mapping):
            return None
        wait = record.get("retry_after_seconds")
        return RateLimit(
            kind=str(record.get("kind")),
            http_status=record.get("http_status"),
            retry_after_seconds=None if wait is None else float(wait),
        )
    status = getattr(outcome, "status_code", None)
    if status not in (429, 402):
        return None
    wait = _retry_after(outcome)
    kind = OUT_OF_CREDIT if status == 402 and wait is None else RATE_LIMIT
    return RateLimit(kind=kind, http_status=status, retry_after_seconds=wait)


class HostedGate:
    """The in-flight limit, rate-limit waits and the stop for one role."""

    def __init__(
        self,
        role: str,
        limit: int,
        *,
        attempts: int = DEFAULT_ATTEMPTS,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rand: Callable[[], float] = random.random,
    ) -> None:
        """Build the gate.

        Args:
            role: The role name, used in messages.
            limit: The most calls of this role in flight at once.
            attempts: The most sends of one call while it is rate-limited
                (``--rate-limit-attempts``).
            sleep: Waits a number of seconds. Tests inject a stub.
            rand: Returns a number in [0, 1) for the jitter. Tests inject a stub.
        """
        self.role = role
        self.limit = limit
        self.attempts = attempts
        self._slots = asyncio.Semaphore(limit)
        self._sleep = sleep
        self._rand = rand

    def _backoff(self, attempt: int) -> float:
        full = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * BACKOFF_FACTOR ** (attempt - 1))
        return full / 2 + self._rand() * full / 2

    def _wait(self, limit: RateLimit, attempt: int) -> float:
        status = limit.http_status
        if limit.kind == OUT_OF_CREDIT:
            raise RateLimitStop(
                f"{self.role}: the provider account is out of credit (HTTP {status}); "
                "top up the account, then run the same command with --resume"
            )
        if attempt >= self.attempts:
            raise RateLimitStop(
                f"{self.role}: still rate-limited (HTTP {status}) after {self.attempts} "
                "attempts; run the same command with --resume later"
            )
        wait = limit.retry_after_seconds
        if wait is None:
            return self._backoff(attempt)
        if wait > MAX_WAIT_SECONDS:
            raise RateLimitStop(
                f"{self.role}: the provider asks for a wait of {wait:g} s (HTTP {status}), "
                f"above {MAX_WAIT_SECONDS:g} s; run the same command with --resume later"
            )
        return wait

    async def call(self, send: Callable[[], Awaitable[T]]) -> T:
        """Send one call under the gate and return its result.

        Args:
            send: Makes one fresh call each time it is called.

        Returns:
            The first result that is not a rate limit.

        Raises:
            RateLimitStop: Out of credit, a wait above 600 s, or the attempts ran out.
            Exception: Any other error of *send*, unchanged.
        """
        attempt = 0
        while True:
            attempt += 1
            async with self._slots:
                try:
                    result = await send()
                except Exception as exc:
                    limit = classify(exc)
                    if limit is None:
                        raise
                else:
                    limit = classify(result) if isinstance(result, Mapping) else None
                    if limit is None:
                        return result
            await self._sleep(self._wait(limit, attempt))
