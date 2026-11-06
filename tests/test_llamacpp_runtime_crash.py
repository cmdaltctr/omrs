"""Crash restart and the log cap (tasks 4.3 and 4.8; design D5)."""

from __future__ import annotations

import os
import signal
import socket
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from tests.fixtures.llamacpp.harness import RuntimeEnv, pid_alive, runtime_env_fixture, wait_until
from tests.unit.test_llamacpp_router_worker import fixed_spec

from omrs.integrations.llamacpp_runtime import process
from omrs.integrations.llamacpp_runtime.manager import RuntimeRequestFailed
from omrs.integrations.llamacpp_runtime.state import runtime_dir, state_root


@pytest.fixture()
def runtime_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RuntimeEnv]:
    yield from runtime_env_fixture(tmp_path, monkeypatch)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _chat(base_url: str) -> httpx.Response:
    return httpx.post(f"{base_url}/v1/chat/completions", json={"messages": []}, timeout=10)


# ── 4.3 Crash restart ───────────────────────────────────────────────────


def test_a_crash_between_requests_restarts_once(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    fake.set_env(FAKE_LLAMA_EXIT_AFTER="1")
    lease = runtime_env.manager().lease(fixed_spec(fake, _free_port()))
    assert lease.request(_chat).status_code == 200  # the server dies after this answer
    first_pid = int(fake.starts()[0]["pid"])
    assert wait_until(lambda: not pid_alive(first_pid))
    assert lease.request(_chat).status_code == 200
    assert len(fake.starts()) == 2


def test_a_second_crash_in_the_same_request_ends_it_with_exited(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    lease = runtime_env.manager().lease(fixed_spec(fake, _free_port()))
    assert lease.request(_chat).status_code == 200
    first_pid = int(fake.starts()[0]["pid"])
    fake.set_env(FAKE_LLAMA_CRASH_ON_REQUEST="1")  # the restarted server dies mid-request
    os.killpg(first_pid, signal.SIGKILL)
    assert wait_until(lambda: not pid_alive(first_pid))
    with pytest.raises(RuntimeRequestFailed) as caught:
        lease.request(_chat)
    assert caught.value.reason == "exited"
    assert len(fake.starts()) == 2, "exactly one restart"


def test_a_live_server_is_not_restarted_after_a_failure(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    lease = runtime_env.manager().lease(fixed_spec(fake, _free_port()))
    lease.join()

    def refused(_base_url: str) -> None:
        raise httpx.ConnectError("refused by a proxy")

    with pytest.raises(httpx.ConnectError):
        lease.request(refused)
    assert len(fake.starts()) == 1


def test_another_error_is_passed_through_with_no_restart(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    lease = runtime_env.manager().lease(fixed_spec(fake, _free_port()))

    def broken(_base_url: str) -> None:
        raise ValueError("bad answer")

    with pytest.raises(ValueError):
        lease.request(broken)
    assert len(fake.starts()) == 1


# ── 4.8 Log cap ─────────────────────────────────────────────────────────


def test_a_log_over_the_cap_is_emptied_in_place(
    runtime_env: RuntimeEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert process.LOG_CAP_BYTES == 5 * 1024 * 1024
    fake = runtime_env.fake()
    fake.set_env(FAKE_LLAMA_SPAM_BYTES=str(6 * 1024 * 1024), FAKE_LLAMA_LOG_REQUESTS="1")
    lease = runtime_env.manager().lease(fixed_spec(fake, _free_port()))
    log = runtime_dir(state_root(), "router") / "server.log"
    lease.join()
    assert log.stat().st_size > process.LOG_CAP_BYTES
    lease.request(_chat)
    assert log.stat().st_size < 1024, "the log was not emptied after the request"
    lease.request(_chat)
    assert wait_until(lambda: "request /v1/chat/completions" in log.read_text())
    assert log.stat().st_size < 1024, "the child wrote past a gap: no O_APPEND"


def test_a_log_under_the_cap_is_kept(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    fake.set_env(FAKE_LLAMA_LOG_REQUESTS="1")
    lease = runtime_env.manager().lease(fixed_spec(fake, _free_port()))
    log = runtime_dir(state_root(), "router") / "server.log"
    lease.request(_chat)
    lease.request(_chat)
    assert wait_until(lambda: log.read_text().count("request /v1/chat/completions") == 2)
