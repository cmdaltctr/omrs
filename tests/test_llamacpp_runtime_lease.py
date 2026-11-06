"""Lease lifecycle across processes (tasks 3.1 to 3.5, 3.7 and 3.10; design D4).

Each test drives real client processes (``tests/fixtures/llamacpp/client.py``)
against the fake ``llama-server``. The fake's start log counts how many
servers started; ``server.json`` in the runtime folder shows how the last
one stopped.
"""

from __future__ import annotations

import json
import signal
import socket
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from tests.fixtures.llamacpp.harness import RuntimeEnv, pid_alive, runtime_env_fixture, wait_until
from tests.unit.test_llamacpp_router_worker import fixed_spec

from omrs.integrations.llamacpp_runtime.locks import LockFile
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


def _folder(runtime_id: str = "router") -> Path:
    return runtime_dir(state_root(), runtime_id)


def test_two_clients_share_one_server(runtime_env: RuntimeEnv) -> None:
    """3.1: two client processes join one runtime; exactly one server starts."""
    fake = runtime_env.fake()
    spec = fixed_spec(fake, _free_port())
    first, second = runtime_env.client(), runtime_env.client()
    assert first.join(spec)["ok"] is True
    assert second.join(spec)["ok"] is True
    assert first.chat()["ok"] is True
    assert second.chat()["ok"] is True
    assert len(fake.starts()) == 1


def test_first_leaves_and_the_server_lives(runtime_env: RuntimeEnv) -> None:
    """3.2: the first client exits; the second's next request needs no start."""
    fake = runtime_env.fake()
    spec = fixed_spec(fake, _free_port())
    first, second = runtime_env.client(), runtime_env.client()
    assert first.join(spec)["ok"] and second.join(spec)["ok"]
    assert first.call({"cmd": "exit"})["ok"]
    assert first.wait() == 0
    server_pid = int(fake.starts()[0]["pid"])
    assert pid_alive(server_pid)
    assert second.chat()["ok"] is True
    assert len(fake.starts()) == 1


def test_last_leaves_and_the_server_stops(runtime_env: RuntimeEnv) -> None:
    """3.3: the only client exits; the group is gone and the record says last-client."""
    fake = runtime_env.fake()
    spec = fixed_spec(fake, _free_port())
    only = runtime_env.client()
    assert only.join(spec)["ok"]
    assert only.chat()["ok"]
    server_pid = int(fake.starts()[0]["pid"])
    assert only.call({"cmd": "exit"})["ok"]
    assert only.wait() == 0
    assert not pid_alive(server_pid)
    record = read_server_record(_folder())
    assert record is not None
    assert (record.state, record.stopped_by) == ("stopped", "last-client")


def test_sigkill_one_of_two_clients_keeps_the_server(runtime_env: RuntimeEnv) -> None:
    """3.4: SIGKILL one client; the server runs on and the other client is served."""
    fake = runtime_env.fake()
    spec = fixed_spec(fake, _free_port())
    first, second = runtime_env.client(), runtime_env.client()
    assert first.join(spec)["ok"] and second.join(spec)["ok"]
    first.proc.send_signal(signal.SIGKILL)
    first.wait()
    assert pid_alive(int(fake.starts()[0]["pid"]))
    assert second.chat()["ok"] is True
    assert len(fake.starts()) == 1


def test_sigkill_the_only_client_then_a_new_client_adopts(runtime_env: RuntimeEnv) -> None:
    """3.5: an orphan after SIGKILL is adopted by the next client; one start only."""
    fake = runtime_env.fake()
    spec = fixed_spec(fake, _free_port())
    only = runtime_env.client()
    assert only.join(spec)["ok"]
    only.proc.send_signal(signal.SIGKILL)
    only.wait()
    newcomer = runtime_env.client()
    assert newcomer.join(spec)["ok"]
    assert newcomer.chat()["ok"] is True
    assert len(fake.starts()) == 1


def test_a_reused_pid_is_never_signalled(runtime_env: RuntimeEnv) -> None:
    """3.7: a recorded pid that runs another command is left alone; a new server starts."""
    fake = runtime_env.fake()
    spec = fixed_spec(fake, _free_port())
    sleeper = subprocess.Popen(["sleep", "60"])  # noqa: S603, S607 - fixed argv
    try:
        write_server_record(
            _folder(),
            ServerRecord(
                pid=sleeper.pid,
                port=spec.port or 0,
                binary=spec.binary,
                digest=spec.digest,
                state="running",
            ),
        )
        client = runtime_env.client()
        assert client.join(spec)["ok"]
        assert client.chat()["ok"] is True
        assert len(fake.starts()) == 1
        assert sleeper.poll() is None, "the reused pid was signalled"
    finally:
        sleeper.kill()
        sleeper.wait()


def test_the_lock_descriptor_is_not_inherited(runtime_env: RuntimeEnv) -> None:
    """3.10: after the starter ends with no leave, nothing holds ``clients.lock``."""
    fake = runtime_env.fake()
    fds_file = fake.logs / "fds.json"
    fake.set_env(FAKE_LLAMA_FDS=str(fds_file))
    spec = fixed_spec(fake, _free_port())
    starter = runtime_env.client()
    assert starter.join(spec)["ok"]
    starter.send({"cmd": "abandon"})
    starter.wait()
    assert pid_alive(int(fake.starts()[0]["pid"]))
    probe = LockFile(_folder() / "clients.lock")
    try:
        assert probe.acquire(shared=False, blocking=False) is True
    finally:
        probe.close()
    # Only standard input, output and error came from the starter: /dev/null
    # and server.log, never a pipe.
    fds = json.loads(fds_file.read_text(encoding="utf-8"))
    assert fds == {"0": "chr", "1": "reg", "2": "reg"}


def test_the_server_survives_its_starter_and_writes_to_server_log(
    runtime_env: RuntimeEnv,
) -> None:
    """4.1 (detach): output goes to ``server.log``; the server outlives the starter."""
    fake = runtime_env.fake()
    fake.set_env(FAKE_LLAMA_SPAM_BYTES="500")
    spec = fixed_spec(fake, _free_port())
    starter, other = runtime_env.client(), runtime_env.client()
    assert starter.join(spec)["ok"] and other.join(spec)["ok"]
    starter.send({"cmd": "abandon"})
    starter.wait()
    assert other.chat()["ok"] is True
    assert wait_until(lambda: "x" * 99 in (_folder() / "server.log").read_text())
