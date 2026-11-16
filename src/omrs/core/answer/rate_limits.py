"""Classify a provider rate limit and retry a short HTTP 402 wait (design D25).

A provider error is a rate limit when it carries ``status_code`` 429 or 402.
The wait comes from ``retry-after-ms`` or ``retry-after`` in
``response.headers``. The module reads these by duck typing, so core imports
no provider library.

``kind`` is ``rate_limit`` for HTTP 429 and for HTTP 402 with a wait (a spend
budget in flight). It is ``out_of_credit`` for HTTP 402 with no wait.

Only an HTTP 402 with a wait of 30 seconds or less is sent again, at most 2
more times. HTTP 429 is not retried here, because the provider client
libraries already retry it.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any

#: The sleep the 402 retry waits with; tests replace it.
sleep: Callable[[float], Awaitable[None]] = asyncio.sleep

#: The longest HTTP 402 wait that OMRS waits for before it sends the call again.
MAX_402_WAIT_SECONDS = 30.0

#: Further attempts after the first one for a short HTTP 402 wait.
MAX_402_RETRIES = 2

RATE_LIMIT = "rate_limit"
OUT_OF_CREDIT = "out_of_credit"

Seam = Callable[[str], Awaitable[str]]


@dataclass(frozen=True)
class RateLimit:
    """A provider rate limit read from an exception.

    Attributes:
        kind: ``rate_limit`` or ``out_of_credit``.
        http_status: 429 or 402.
        retry_after_seconds: The wait the provider asked for, else ``None``.
    """

    kind: str
    http_status: int
    retry_after_seconds: float | None

    def as_dict(self) -> dict[str, Any]:
        """Return the result record ``{kind, http_status, retry_after_seconds}``."""
        return asdict(self)


def _retry_after(exc: BaseException) -> float | None:
    """Return the wait in seconds from the error's response headers, else ``None``."""
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    lowered = {str(key).lower(): value for key, value in headers.items()}
    for name, scale in (("retry-after-ms", 1000.0), ("retry-after", 1.0)):
        try:
            return float(lowered[name]) / scale
        except (KeyError, TypeError, ValueError):
            continue
    return None


def classify_rate_limit(exc: BaseException) -> RateLimit | None:
    """Return the rate limit that *exc* carries, or ``None`` for any other error.

    Args:
        exc: The exception a completion or judge call raised.

    Returns:
        A :class:`RateLimit` for ``status_code`` 429 or 402, else ``None``.
    """
    status = getattr(exc, "status_code", None)
    if status not in (429, 402):
        return None
    wait = _retry_after(exc)
    kind = OUT_OF_CREDIT if status == 402 and wait is None else RATE_LIMIT
    return RateLimit(kind=kind, http_status=int(status), retry_after_seconds=wait)


def generation_message(limit: RateLimit) -> str:
    """Return the fixed ``error`` text of a rate-limited generation."""
    if limit.kind == OUT_OF_CREDIT:
        return (
            "Generation failed: the answer model's provider account is out of credit "
            f"(HTTP {limit.http_status}). Top up the account, then ask again."
        )
    return (
        "Generation failed: the answer model's provider is limiting requests "
        f"(HTTP {limit.http_status}). Wait, then ask again."
    )


def judge_reason(limit: RateLimit) -> str:
    """Return the fixed ``verification_skipped`` reason of a rate-limited judge."""
    if limit.kind == OUT_OF_CREDIT:
        return (
            "verification failed: the judge model's provider account is out of credit "
            f"(HTTP {limit.http_status}). Top up the judge provider account, then ask again."
        )
    return (
        "verification failed: the judge model's provider is limiting requests "
        f"(HTTP {limit.http_status}). Wait, then ask again."
    )


def _short_402(limit: RateLimit | None) -> bool:
    return (
        limit is not None
        and limit.http_status == 402
        and limit.retry_after_seconds is not None
        and limit.retry_after_seconds <= MAX_402_WAIT_SECONDS
    )


def with_short_402_retry(seam: Seam) -> Seam:
    """Wrap *seam* so a short HTTP 402 wait is waited out and the call sent again.

    Args:
        seam: An async completion seam (prompt in, reply out).

    Returns:
        A seam that makes at most :data:`MAX_402_RETRIES` more attempts per
        call. Any other error, and the last 402, propagate unchanged.
    """

    async def retrying(prompt: str) -> str:
        retries = 0
        while True:
            try:
                return await seam(prompt)
            except Exception as exc:
                limit = classify_rate_limit(exc)
                if retries >= MAX_402_RETRIES or not _short_402(limit):
                    raise
                retries += 1
                await sleep(limit.retry_after_seconds)  # type: ignore[union-attr,arg-type]

    return retrying
