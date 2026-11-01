"""Operator stop, exit paths and the start-up sweep (tasks 4.6 and 4.7; D8, D9)."""

from __future__ import annotations

import signal
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.fixtures.llamacpp.harness import RuntimeEnv, pid_alive, runtime_env_fixture

from omrs.integrations.llamacpp_runtime.state import (
    ServerRecord,
    read_server_record,
    runtime_dir,
    state_root,
    write_server_record,
)


@pytest.fixture()
def runtime_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RuntimeEnv]:
    yield from runtime_env_fixture(tmp_path, monkeypatch)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _record(runtime_id: str = "chat"):  # type: ignore[no-untyped-def]
    return read_server_record(runtime_dir(state_root(), runtime_id))


# ── 4.6 Operator stop ───────────────────────────────────────────────────


def test_operator_stop_while_a_client_uses_the_runtime(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    fake.set_env(FAKE_LLAMA_REQUEST_DELAY="3")
    spec = fake.chat(_free_port())
    cli = runtime_env.client()
    assert cli.join(spec)["ok"]
    server_pid = int(fake.starts()[0]["pid"])
    cli.send({"cmd": "request", "path": "/v1/chat/completions", "body": {}, "timeout": 30})
    time.sleep(0.5)  # the request is in progress
    assert runtime_env.manager().stop("chat") is True
    assert not pid_alive(server_pid)
    record = _record()
    assert record is not None and record.stopped_by == "operator"
    failed = cli.read()
    assert (failed["ok"], failed["phase"], failed["reason"]) == (False, "after", "operator-stop")
    again = cli.chat()
    assert (again["ok"], again["phase"], again["reason"]) == (False, "before", "operator-stop")
    assert len(fake.starts()) == 1, "the stopped lease started the server again"
    newcomer = runtime_env.client()
    assert newcomer.join(spec)["ok"]
    assert len(fake.starts()) == 2


def test_operator_stop_of_a_stopped_runtime_signals_nothing(runtime_env: RuntimeEnv) -> None:
    assert runtime_env.manager().stop("chat") is False
    assert _record() is None


def test_the_same_process_starts_again_after_its_lease_left(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    spec = fake.chat(_free_port())
    manager = runtime_env.manager()
    lease = manager.lease(spec)
    lease.join()
    assert manager.stop("chat") is True
    lease.leave()
    lease.join()
    assert len(fake.starts()) == 2


# ── 4.7 Exit paths ──────────────────────────────────────────────────────


def test_sigterm_to_the_only_client_stops_the_server_before_it_exits(
    runtime_env: RuntimeEnv,
) -> None:
    fake = runtime_env.fake()
    spec = fake.chat(_free_port())
    only = runtime_env.client()
    assert only.join(spec)["ok"]
    server_pid = int(fake.starts()[0]["pid"])
    only.proc.send_signal(signal.SIGTERM)
    only.wait()
    assert not pid_alive(server_pid), "the server outlived its only client"
    record = _record()
    assert record is not None and record.stopped_by == "last-client"


def test_close_leaves_every_lease(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    manager = runtime_env.manager()
    manager.lease(fake.chat(_free_port())).join()
    manager.lease(fake.ocr()).join()
    pids = [int(entry["pid"]) for entry in fake.starts()]
    manager.close()
    assert not any(pid_alive(pid) for pid in pids)


def test_sweep_stops_an_owned_server_with_no_client(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    spec = fake.chat(_free_port())
    starter = runtime_env.client()
    assert starter.join(spec)["ok"]
    starter.send({"cmd": "abandon"})  # an orphan, as after SIGKILL
    starter.wait()
    server_pid = int(fake.starts()[0]["pid"])
    assert pid_alive(server_pid)
    assert runtime_env.manager().sweep() == ["chat"]
    assert not pid_alive(server_pid)


def test_sweep_leaves_a_server_that_a_client_holds(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    spec = fake.chat(_free_port())
    holder = runtime_env.client()
    assert holder.join(spec)["ok"]
    assert runtime_env.manager().sweep() == []
    assert pid_alive(int(fake.starts()[0]["pid"]))
    assert holder.chat()["ok"] is True


def test_sweep_never_signals_a_reused_pid(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    spec = fake.chat(_free_port())
    sleeper = subprocess.Popen(["sleep", "60"])  # noqa: S603, S607 - fixed argv
    try:
        write_server_record(
            runtime_dir(state_root(), "chat"),
            ServerRecord(pid=sleeper.pid, port=1, binary=spec.binary, digest=spec.digest),
        )
        assert runtime_env.manager().sweep() == []
        assert sleeper.poll() is None
    finally:
        sleeper.kill()
        sleeper.wait()


def test_operator_stop_never_signals_a_reused_pid(runtime_env: RuntimeEnv) -> None:
    fake = runtime_env.fake()
    spec = fake.chat(_free_port())
    sleeper = subprocess.Popen(["sleep", "60"])  # noqa: S603, S607 - fixed argv
    try:
        write_server_record(
            runtime_dir(state_root(), "chat"),
            ServerRecord(pid=sleeper.pid, port=1, binary=spec.binary, digest=spec.digest),
        )
        assert runtime_env.manager().stop("chat") is False
        assert sleeper.poll() is None
    finally:
        sleeper.kill()
        sleeper.wait()


def test_an_external_lease_never_stops_the_recorded_server(runtime_env: RuntimeEnv) -> None:
    from omrs.integrations.llamacpp_runtime.spec import RuntimeSpec

    fake = runtime_env.fake()
    port = _free_port()
    runtime_env.manager().lease(fake.chat(port)).join()
    external = runtime_env.manager()
    external.lease(
        RuntimeSpec(
            id="chat", role="chat", mode="external", binary="", url_base=f"http://127.0.0.1:{port}"
        )
    )
    assert external.stop("chat") is False
    assert pid_alive(int(fake.starts()[0]["pid"]))
