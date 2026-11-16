"""``experiments/_lib/hosted_calls.py``: the shared gate for hosted calls (Exp 35 tasks 2.1 to 2.3).

The gate holds the in-flight limit of one role, waits on a rate limit and
stops the stage when the attempts run out or the account is out of credit
(design D1, D2). Every test uses stub calls, an injected sleep and an
injected random source: nothing waits and nothing reaches the network.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest
from experiments._lib.hosted_calls import HostedGate, RateLimitStop, classify


class _Response:
    def __init__(self, headers: Mapping[str, str], body: Any = None) -> None:
        self.headers = dict(headers)
        self.body = body


class _StatusError(Exception):
    """A stub provider error: ``status_code`` and ``response.headers``, as ``openai`` carries."""

    def __init__(self, status: int, headers: Mapping[str, str] | None = None, body: Any = None):
        super().__init__(f"Error code: {status}")
        self.status_code = status
        self.response = _Response(headers or {}, body)


class _Sleeps:
    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def _gate(limit: int = 4, *, attempts: int = 6, rand: float = 0.5) -> tuple[HostedGate, _Sleeps]:
    sleeps = _Sleeps()
    gate = HostedGate("answer", limit, attempts=attempts, sleep=sleeps, rand=lambda: rand)
    return gate, sleeps


def _failing(errors: list[BaseException], result: Any = "ok") -> tuple[Any, list[int]]:
    """A call that raises each error in turn, then returns *result*."""
    calls: list[int] = []

    async def send() -> Any:
        calls.append(1)
        if len(calls) <= len(errors):
            raise errors[len(calls) - 1]
        return result

    return send, calls


# --- 2.1 concurrency -------------------------------------------------------------------


async def test_limit_four_never_has_more_than_four_in_flight() -> None:
    gate, _ = _gate(4)
    state = {"now": 0, "peak": 0}

    async def send() -> str:
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.001)
        state["now"] -= 1
        return "ok"

    results = await asyncio.gather(*(gate.call(send) for _ in range(20)))
    assert results == ["ok"] * 20
    assert state["peak"] == 4


async def test_limit_one_runs_calls_in_submission_order() -> None:
    gate, _ = _gate(1)
    started: list[int] = []

    def make(number: int) -> Any:
        async def send() -> int:
            started.append(number)
            await asyncio.sleep(0.001 * (10 - number))
            return number

        return send

    results = await asyncio.gather(*(gate.call(make(n)) for n in range(10)))
    assert started == list(range(10))
    assert results == list(range(10))


# --- 2.2 classification ----------------------------------------------------------------


@pytest.mark.parametrize("status", [429, 402])
def test_status_429_or_402_is_a_rate_limit(status: int) -> None:
    limit = classify(_StatusError(status, {"Retry-After": "3"}))
    assert limit is not None
    assert limit.http_status == status
    assert limit.kind == "rate_limit"


def test_zai_429_with_body_code_1302_is_a_rate_limit() -> None:
    body = {"error": {"code": "1302", "message": "rate limit reached for requests"}}
    limit = classify(_StatusError(429, body=body))
    assert limit is not None
    assert limit.kind == "rate_limit"
    assert limit.retry_after_seconds is None


def test_402_without_retry_after_is_out_of_credit() -> None:
    limit = classify(_StatusError(402))
    assert limit is not None
    assert limit.kind == "out_of_credit"


@pytest.mark.parametrize(
    "error",
    [_StatusError(500), TimeoutError("read timed out"), ValueError("bad JSON")],
)
def test_server_error_and_timeout_are_not_rate_limits(error: BaseException) -> None:
    assert classify(error) is None


def test_answer_error_without_record_is_not_a_rate_limit_even_when_text_names_429() -> None:
    result = {
        "status": "error",
        "answer": None,
        "error": "Generation failed: RateLimitError: Error code: 429 - rate limited",
    }
    assert classify(result) is None


def test_answer_result_record_is_a_rate_limit_with_its_wait() -> None:
    result = {
        "status": "error",
        "answer": None,
        "rate_limited": {"kind": "rate_limit", "http_status": 429, "retry_after_seconds": 7.0},
    }
    limit = classify(result)
    assert limit is not None
    assert (limit.kind, limit.http_status, limit.retry_after_seconds) == ("rate_limit", 429, 7.0)


_EVIDENCE = {
    "ordinal": 1, "chunk_id": "c1", "chunk_ids": ["c1"], "source_id": "s1",
    "source_version": "v1", "source": "doc.md", "source_chunk_index": 0,
    "score": 0.5, "score_kind": "similarity", "text": "The sky is blue.",
}  # fmt: skip


async def _real_result(error: BaseException) -> dict[str, Any]:
    """Build the answer error result with the real OMRS seam wrapper and builder (task 0.2)."""
    from omrs.core.answer.results import stage_failure_result
    from omrs.core.answer.stages import synthesise_answer
    from omrs.core.settings import AnswerBlock

    async def seam(prompt: str) -> str:
        raise error

    outcome = await synthesise_answer(
        "q", [_EVIDENCE], complete=seam, answer_block=AnswerBlock(), error_detail=str
    )
    return stage_failure_result(
        "q", "server", failure_stage="generation", error=outcome.error,
        evidence=[_EVIDENCE], rate_limited=outcome.rate_limited,
    )  # fmt: skip


async def test_real_omrs_rate_limited_result_is_a_rate_limit_with_its_wait() -> None:
    result = await _real_result(_StatusError(429, {"Retry-After": "7"}))
    limit = classify(result)
    assert limit is not None
    assert (limit.kind, limit.http_status, limit.retry_after_seconds) == ("rate_limit", 429, 7.0)
    gate, sleeps = _gate()
    answers = [result, {"status": "ok", "answer": "a"}]

    async def send() -> Any:
        return answers.pop(0)

    assert await gate.call(send) == {"status": "ok", "answer": "a"}
    assert sleeps.waits == [7.0]


async def test_real_omrs_error_without_record_is_not_a_rate_limit() -> None:
    result = await _real_result(RuntimeError("Error code: 429 - upstream says slow down"))
    assert "429" in result["error"]
    assert classify(result) is None


def test_ok_answer_result_is_not_a_rate_limit() -> None:
    assert classify({"status": "ok", "answer": "x"}) is None


# --- 2.3 waits and the stop ------------------------------------------------------------


async def test_retry_after_seven_waits_seven_seconds() -> None:
    gate, sleeps = _gate()
    send, calls = _failing([_StatusError(429, {"Retry-After": "7"})])
    assert await gate.call(send) == "ok"
    assert sleeps.waits == [7.0]
    assert len(calls) == 2


async def test_retry_after_ms_is_read() -> None:
    gate, sleeps = _gate()
    send, _ = _failing([_StatusError(429, {"retry-after-ms": "1500"})])
    await gate.call(send)
    assert sleeps.waits == [1.5]


async def test_header_names_are_read_in_any_case() -> None:
    gate, sleeps = _gate()
    send, _ = _failing([_StatusError(402, {"retry-after": "20"})])
    await gate.call(send)
    assert sleeps.waits == [20.0]


async def test_retry_after_above_600_seconds_stops_at_once() -> None:
    gate, sleeps = _gate()
    send, calls = _failing([_StatusError(429, {"Retry-After": "601"})])
    with pytest.raises(RateLimitStop, match="601"):
        await gate.call(send)
    assert sleeps.waits == []
    assert len(calls) == 1


async def test_no_header_backs_off_base_5_factor_2_cap_120_with_equal_jitter() -> None:
    gate, sleeps = _gate(attempts=8, rand=0.0)
    send, _ = _failing([_StatusError(429)] * 7)
    await gate.call(send)
    # Equal jitter: half of the backoff is fixed, half is random (random 0 here).
    assert sleeps.waits == [2.5, 5.0, 10.0, 20.0, 40.0, 60.0, 60.0]
    gate, sleeps = _gate(attempts=3, rand=1.0)
    send, _ = _failing([_StatusError(429)] * 2)
    await gate.call(send)
    assert sleeps.waits == [5.0, 10.0]


async def test_record_wait_inside_an_answer_result_is_used() -> None:
    gate, sleeps = _gate()
    limited = {
        "status": "error",
        "rate_limited": {"kind": "rate_limit", "http_status": 429, "retry_after_seconds": 9.0},
    }
    answers = [limited, {"status": "ok", "answer": "a"}]

    async def send() -> Any:
        return answers.pop(0)

    assert await gate.call(send) == {"status": "ok", "answer": "a"}
    assert sleeps.waits == [9.0]


async def test_attempts_used_up_raise_rate_limit_stop() -> None:
    gate, sleeps = _gate()
    send, calls = _failing([_StatusError(429)] * 10)
    with pytest.raises(RateLimitStop, match="6 attempts"):
        await gate.call(send)
    assert len(calls) == 6
    assert len(sleeps.waits) == 5


async def test_402_without_retry_after_stops_at_once_with_top_up_message() -> None:
    gate, sleeps = _gate()
    send, calls = _failing([_StatusError(402)])
    with pytest.raises(RateLimitStop, match="top up"):
        await gate.call(send)
    assert len(calls) == 1
    assert sleeps.waits == []


async def test_out_of_credit_record_stops_at_once_with_top_up_message() -> None:
    gate, sleeps = _gate()
    calls: list[int] = []

    async def send() -> Any:
        calls.append(1)
        record = {"kind": "out_of_credit", "http_status": 402, "retry_after_seconds": None}
        return {"status": "error", "answer": None, "rate_limited": record}

    with pytest.raises(RateLimitStop, match="top up"):
        await gate.call(send)
    assert len(calls) == 1
    assert sleeps.waits == []


async def test_other_error_passes_through_unchanged() -> None:
    gate, sleeps = _gate()
    error = _StatusError(500)
    send, calls = _failing([error])
    with pytest.raises(_StatusError) as caught:
        await gate.call(send)
    assert caught.value is error
    assert len(calls) == 1
    assert sleeps.waits == []


async def test_sleep_does_not_hold_a_slot() -> None:
    """A call that waits on a rate limit lets another call of the role run."""
    order: list[str] = []
    release = asyncio.Event()

    async def slow_sleep(seconds: float) -> None:
        order.append("wait")
        await release.wait()

    gate = HostedGate("answer", 1, sleep=slow_sleep, rand=lambda: 0.5)
    send, _ = _failing([_StatusError(429, {"Retry-After": "1"})], result="first")

    async def other() -> str:
        order.append("other")
        release.set()
        return "second"

    results = await asyncio.gather(gate.call(send), gate.call(other))
    assert results == ["first", "second"]
    assert order == ["wait", "other"]
