"""Busy servers, races, versions and lock order (tasks 3.6, 3.8, 3.9, 3.11, 3.12).

A slow ``/health`` or a long request never makes a server stale; five
clients that start at once share one server; SIGINT to a CLI's process group
never reaches the server; a changed program path is refused while the old
server has clients; and join and leave in many threads and processes never
deadlock.
"""

from __future__ import annotations

import os
import signal
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.fixtures.llamacpp.harness import RuntimeEnv, pid_alive, runtime_env_fixture

from omrs.integrations.llamacpp_runtime.manager import RuntimeUnavailable


@pytest.fixture()
def runtime_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RuntimeEnv]:
    yield from runtime_env_fixture(tmp_path, monkeypatch)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _busy_server_is_adopted(runtime_env: RuntimeEnv, request_seconds: float) -> None:
    fake = runtime_env.fake()
    sleep_file = fake.logs / "health-sleep.txt"
    fake.set_env(
        FAKE_LLAMA_REQUEST_DELAY=str(request_seconds),
        FAKE_LLAMA_HEALTH_SLEEP_FILE=str(sleep_file),
    )
    spec = fake.chat(_free_port())
    first, second = runtime_env.client(), runtime_env.client()
    assert first.join(spec)["ok"]
    server_pid = int(fake.starts()[0]["pid"])
    sleep_file.write_text("5", encoding="utf-8")  # every /health now takes 5 s
    first.send(
        {
            "cmd": "request",
            "path": "/v1/chat/completions",
            "body": {},
            "timeout": request_seconds + 30,
        }
    )
    time.sleep(0.3)  # the request is in progress
    begun = time.monotonic()
    joined = second.join(spec)
    assert joined["ok"] is True
    assert time.monotonic() - begun < 4, "the join waited on /health"
    assert first.read(timeout=request_seconds + 30)["ok"] is True
    assert pid_alive(server_pid), "the busy server was signalled"
    assert len(fake.starts()) == 1


def test_a_slow_health_and_a_busy_request_never_make_it_stale(runtime_env: RuntimeEnv) -> None:
    """3.6: a 5 s ``/health`` and a 3 s request; the second client adopts."""
    _busy_server_is_adopted(runtime_env, 3.0)


@pytest.mark.slow
def test_a_sixty_second_request_never_makes_it_stale(runtime_env: RuntimeEnv) -> None:
    """3.6 (slow): the same with a 60 s request in progress."""
    _busy_server_is_adopted(runtime_env, 60.0)


def test_five_clients_at_once_start_one_server(runtime_env: RuntimeEnv) -> None:
    """3.8: five clients join a stopped runtime at once; one start, five answers."""
    fake = runtime_env.fake()
    fake.set_env(FAKE_LLAMA_HEALTH_DELAY="0.5")
    spec = fake.chat(_free_port())
    clients = [runtime_env.client() for _ in range(5)]
    for client in clients:
        client.send({"cmd": "join", "spec": spec.to_dict()})
    assert all(client.read()["ok"] for client in clients)
    for client in clients:
        client.send({"cmd": "request", "path": "/v1/chat/completions", "body": {}})
    assert all(client.read()["ok"] for client in clients)
    assert len(fake.starts()) == 1


def test_sigint_to_a_cli_group_never_reaches_the_server(runtime_env: RuntimeEnv) -> None:
    """3.9: Ctrl-C in the CLI's group; the server and the web app's requests go on."""
    fake = runtime_env.fake()
    spec = fake.chat(_free_port())
    cli = runtime_env.client(new_group=True)
    web = runtime_env.client()
    assert cli.join(spec)["ok"]
    assert web.join(spec)["ok"]
    os.killpg(cli.pid, signal.SIGINT)
    cli.wait()
    assert pid_alive(int(fake.starts()[0]["pid"]))
    assert web.chat()["ok"] is True
    assert len(fake.starts()) == 1


def test_a_changed_binary_is_refused_while_the_old_server_has_clients(
    runtime_env: RuntimeEnv,
) -> None:
    """3.11: ``version-busy`` with clients; with none, the old stops and the new starts."""
    old, new = runtime_env.fake("bin-old"), runtime_env.fake("bin-new")
    port = _free_port()
    holder = runtime_env.client()
    assert holder.join(old.chat(port))["ok"]
    old_pid = int(old.starts()[0]["pid"])
    asker = runtime_env.client()
    refused = asker.join(new.chat(port))
    assert refused == {"ok": False, "reason": "version-busy", "reason_text": refused["reason_text"]}
    assert pid_alive(old_pid), "the old server was signalled"
    assert holder.chat()["ok"] is True
    holder.send({"cmd": "abandon"})  # the old server now has no client
    holder.wait()
    assert asker.join(new.chat(port))["ok"] is True
    assert not pid_alive(old_pid)
    assert len(new.starts()) == 1
    assert asker.chat()["ok"] is True


def _churn(runtime_env: RuntimeEnv, seconds: float) -> None:
    fake = runtime_env.fake()
    spec = fake.chat(_free_port())
    stop_at = time.monotonic() + seconds
    errors: list[BaseException] = []

    def thread_body() -> None:
        manager = runtime_env.manager()
        try:
            while time.monotonic() < stop_at:
                lease = manager.lease(spec)
                try:
                    lease.join()
                except RuntimeUnavailable as error:
                    errors.append(error)
                lease.leave()
        except BaseException as error:  # noqa: BLE001 - reported below
            errors.append(error)

    threads = [threading.Thread(target=thread_body, daemon=True) for _ in range(4)]
    clients = [runtime_env.client() for _ in range(2)]
    for thread in threads:
        thread.start()
    rounds = 0
    while time.monotonic() < stop_at:
        for client in clients:
            client.send({"cmd": "join", "spec": spec.to_dict()})
        for client in clients:
            client.read(timeout=60)
        for client in clients:
            assert client.call({"cmd": "leave"}, timeout=60)["ok"]
        rounds += 1
    for thread in threads:
        thread.join(timeout=60)
        assert not thread.is_alive(), "a thread is stuck: lock order broken"
    assert errors == []
    assert rounds > 0


def test_join_and_leave_in_threads_and_processes_never_deadlock(runtime_env: RuntimeEnv) -> None:
    """3.12 (fast): 3 s of join and leave in 4 threads and 2 processes."""
    _churn(runtime_env, 3.0)


@pytest.mark.slow
def test_join_and_leave_for_twenty_seconds_never_deadlock(runtime_env: RuntimeEnv) -> None:
    """3.12: the same for 20 s."""
    _churn(runtime_env, 20.0)
