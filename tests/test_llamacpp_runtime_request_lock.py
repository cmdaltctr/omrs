"""The request lock of a one-slot runtime (task 4.5; design D6).

The fake answers one POST at a time when its argument list holds ``-np 1``,
as a one-slot llama-server queues a second request. Each request takes 3 s
and each client allows 4 s. With the lock, the second request's clock starts
when the first ends, so both succeed. Without it, the second waits inside the
server while its clock runs, and times out.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.fixtures.llamacpp.harness import ClientProcess, RuntimeEnv, runtime_env_fixture

REQUEST = {"cmd": "request", "path": "/v1/chat/completions", "body": {}, "timeout": 4}


@pytest.fixture()
def runtime_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RuntimeEnv]:
    yield from runtime_env_fixture(tmp_path, monkeypatch)


def _two_requests_at_once(
    runtime_env: RuntimeEnv, *, request_lock: bool
) -> tuple[dict, dict, float]:  # type: ignore[type-arg]
    fake = runtime_env.fake()
    fake.set_env(FAKE_LLAMA_REQUEST_DELAY="3")
    spec = fake.ocr(flags=("-np", "1"))
    assert spec.one_slot
    first, second = runtime_env.client(), runtime_env.client()
    for client in (first, second):
        if not request_lock:
            assert client.call({"cmd": "config", "request_lock": False})["ok"]
        assert client.join(spec)["ok"]
    begun = time.monotonic()
    first.send(REQUEST)
    second.send(REQUEST)
    answers = _read_both(first, second)
    return answers[0], answers[1], time.monotonic() - begun


def _read_both(first: ClientProcess, second: ClientProcess) -> list[dict]:  # type: ignore[type-arg]
    return [first.read(timeout=30), second.read(timeout=30)]


def test_both_requests_succeed_with_the_lock(runtime_env: RuntimeEnv) -> None:
    first, second, took = _two_requests_at_once(runtime_env, request_lock=True)
    assert first["ok"] is True, first
    assert second["ok"] is True, second
    assert took >= 5.5, "the two requests ran one after the other"


def test_without_the_lock_the_second_request_times_out(runtime_env: RuntimeEnv) -> None:
    first, second, _took = _two_requests_at_once(runtime_env, request_lock=False)
    reasons = sorted(answer.get("reason", "ok") for answer in (first, second))
    assert reasons == ["client-timeout", "ok"]


def test_a_runtime_with_several_slots_takes_no_request_lock(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    fake.set_env(FAKE_LLAMA_REQUEST_DELAY="2")
    spec = fake.ocr(flags=("--temp", "0"))
    assert not spec.one_slot
    first, second = runtime_env.client(), runtime_env.client()
    assert first.join(spec)["ok"] and second.join(spec)["ok"]
    begun = time.monotonic()
    first.send(REQUEST)
    second.send(REQUEST)
    assert all(answer["ok"] for answer in _read_both(first, second))
    assert time.monotonic() - begun < 3.8, "requests to a many-slot runtime ran in turn"
