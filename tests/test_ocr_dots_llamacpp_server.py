"""The llama-server lifecycle of the dots-mocr-llamacpp engine (task 2.4).

Change dots-mocr-llamacpp-backend.
The tests run against ``tests/fixtures/ocr_worker/fake_llama_server.py``, a
script that speaks the few HTTP routes the engine uses. CI has no GPU and no
model. Tests that must show a process stop on SIGTERM or on closed input run
a small worker script in a real subprocess.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from tests.fixtures.ocr_worker.dots_llamacpp import (
    ENGINE_DIR,
    WORKERS,
    engine_modules,
    make_fake_binary,
)

BUILD = 11941


class Env:
    """The server module, a fake binary and the files the fake writes."""

    def __init__(self, server: ModuleType, folder: Path) -> None:
        self.server, self.folder = server, folder
        self.binary = make_fake_binary(folder)
        self.model = folder / "model.gguf"
        self.projector = folder / "mmproj.gguf"
        self.model.write_bytes(b"m")
        self.projector.write_bytes(b"p")
        self.log = folder / "llama-server.log"
        self.pid_file = folder / "llama-server.pid"
        self.starts = folder / "starts.txt"
        self.live: list[Any] = []

    def make(self, **overrides: Any) -> Any:
        """Build a server with short timeouts; stop it at teardown."""
        options: dict[str, Any] = {
            "log_path": self.log,
            "pid_path": self.pid_file,
            "start_timeout": 20.0,
            "poll_interval": 0.05,
            "stop_timeout": 5.0,
        }
        options.update(overrides)
        server = self.server.LlamaServer(self.binary, self.model, self.projector, **options)
        self.live.append(server)
        return server

    def start_lines(self) -> list[list[str]]:
        """Return the argv of each start the fake recorded."""
        if not self.starts.exists():
            return []
        return [json.loads(line.split(" ", 1)[1]) for line in self.starts.read_text().splitlines()]

    def start_pids(self) -> list[int]:
        """Return the pid of each start the fake recorded."""
        if not self.starts.exists():
            return []
        return [int(line.split(" ", 1)[0]) for line in self.starts.read_text().splitlines()]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _wait_dead(pid: int, seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Env]:
    """Load the server module with a fake binary in a temporary folder."""
    monkeypatch.setenv("FAKE_LLAMA_STARTS", str(tmp_path / "starts.txt"))
    monkeypatch.delenv("FAKE_LLAMA_BUILD", raising=False)
    with engine_modules(monkeypatch) as load:
        e = Env(load("server"), tmp_path)
        yield e
        for server in e.live:
            server.stop()
        for pid in e.start_pids():
            if _alive(pid):
                os.kill(pid, signal.SIGKILL)


# ── Command line and build check ───────────────────────────────────────────


def test_server_command_matches_experiment_41_arm_d4(env: Env) -> None:
    """Design D5: the flags of Experiment 41 arm D4, on a loopback port."""
    command = env.server.server_command(env.binary, env.model, env.projector, 4567)
    assert command == [
        str(env.binary),
        "-m",
        str(env.model),
        "--mmproj",
        str(env.projector),
        "--host",
        "127.0.0.1",
        "--port",
        "4567",
        "--temp",
        "0",
        "-c",
        "24576",
        "-np",
        "1",
        "--image-min-tokens",
        "4",
        "--image-max-tokens",
        "14400",
    ]


def test_a_wrong_build_is_refused_before_anything_starts(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A binary that reports another build stops the start and names both builds."""
    monkeypatch.setenv("FAKE_LLAMA_BUILD", "11960")
    with pytest.raises(env.server.ServerError) as excinfo:
        env.make().ensure_started()
    message = str(excinfo.value)
    assert "11960" in message and str(BUILD) in message
    assert env.start_lines() == []


def test_a_missing_binary_names_the_path(env: Env) -> None:
    """A binary that does not exist gives a clear error, not a traceback."""
    env.binary.unlink()
    with pytest.raises(env.server.ServerError) as excinfo:
        env.make().ensure_started()
    assert str(env.binary) in str(excinfo.value)


# ── Start, reuse, stop ─────────────────────────────────────────────────────


def test_the_first_call_starts_the_server_and_a_later_call_reuses_it(env: Env) -> None:
    """One start for many calls; the server is healthy on loopback."""
    server = env.make()
    first = server.ensure_started()
    second = server.ensure_started()
    assert first == second and first.startswith("http://127.0.0.1:")
    assert len(env.start_lines()) == 1
    args = env.start_lines()[0]
    assert args[args.index("--host") + 1] == "127.0.0.1"
    assert env.pid_file.exists()
    record = json.loads(env.pid_file.read_text())
    assert record["pid"] == env.start_pids()[0] and record["binary"] == str(env.binary)


def test_stop_ends_the_process_and_removes_the_pid_file(env: Env) -> None:
    """After stop() no server process and no pid file remain; a second stop is harmless."""
    server = env.make()
    server.ensure_started()
    pid = env.start_pids()[0]
    server.stop()
    assert _wait_dead(pid)
    assert not env.pid_file.exists()
    server.stop()


def test_a_server_that_died_is_started_again(env: Env) -> None:
    """If the process is gone, the next call starts a new one."""
    server = env.make()
    server.ensure_started()
    os.kill(env.start_pids()[0], signal.SIGKILL)
    time.sleep(0.3)  # the dead child is a zombie until the server object polls it
    server.ensure_started()
    assert len(env.start_lines()) == 2


def test_a_health_timeout_names_the_log_and_stops_the_process(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A server that never turns healthy gives a parse-ready error that names the log."""
    monkeypatch.setenv("FAKE_LLAMA_NEVER_HEALTHY", "1")
    with pytest.raises(env.server.ServerError) as excinfo:
        env.make(start_timeout=1.0).ensure_started()
    assert str(env.log) in str(excinfo.value)
    assert _wait_dead(env.start_pids()[0])
    assert not env.pid_file.exists()


def test_a_slow_start_within_the_timeout_succeeds(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The poll waits while ``/health`` answers 503 and returns once it answers 200."""
    monkeypatch.setenv("FAKE_LLAMA_HEALTH_DELAY", "0.6")
    assert env.make().ensure_started().startswith("http://127.0.0.1:")


def test_a_failed_bind_is_retried_once_on_a_new_port(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A server that exits at once (port taken) is started again on another port."""
    monkeypatch.setenv("FAKE_LLAMA_FAIL_ONCE", str(env.folder / "failed-once"))
    env.make().ensure_started()
    assert len(env.start_lines()) == 1, "only the second attempt got far enough to record a start"
    assert (env.folder / "failed-once").exists()


def test_two_failed_starts_give_an_error_that_names_the_log(env: Env) -> None:
    """The retry happens once. After that the error names the log."""
    calls = env.folder / "calls"
    wrapper = env.folder / "wrapper"
    wrapper.write_text(
        f'#!/bin/sh\nif [ "$1" = --version ]; then exec {env.binary} --version; fi\n'
        f"echo x >> {calls}\necho 'address already in use' >&2\nexit 1\n"
    )
    wrapper.chmod(0o755)
    server = env.server.LlamaServer(
        wrapper,
        env.model,
        env.projector,
        log_path=env.log,
        pid_path=env.pid_file,
        start_timeout=5.0,
        poll_interval=0.05,
    )
    with pytest.raises(env.server.ServerError) as excinfo:
        server.ensure_started()
    assert str(env.log) in str(excinfo.value)
    assert len(calls.read_text().splitlines()) == 2


# ── The log ────────────────────────────────────────────────────────────────


def test_the_log_is_capped_and_rotated_once(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    """Output beyond the cap rotates the log to ``.1``; the log never grows past the cap."""
    monkeypatch.setenv("FAKE_LLAMA_SPAM_BYTES", "20000")
    server = env.make(log_cap=3000)
    server.ensure_started()
    server.stop()
    rotated = env.log.with_name(env.log.name + ".1")
    assert rotated.exists()
    assert env.log.stat().st_size <= 3000 + 200
    assert not env.log.with_name(env.log.name + ".2").exists()


# ── Stale servers ──────────────────────────────────────────────────────────

_WORKER = """
import sys
sys.path[:0] = [{core!r}, {engine!r}]
from pathlib import Path
from omrs_ocr_dots_mocr_llamacpp.server import LlamaServer
server = LlamaServer(
    Path({binary!r}), Path({model!r}), Path({projector!r}),
    log_path=Path({log!r}), pid_path=Path({pid!r}),
    start_timeout=20, poll_interval=0.05, stop_timeout=5,
)
server.install_shutdown_hooks()
print(server.ensure_started(), flush=True)
sys.stdin.read()
"""


def _start_worker(env: Env) -> subprocess.Popen[str]:
    script = env.folder / "worker.py"
    script.write_text(
        _WORKER.format(
            core=str(WORKERS / "core" / "src"),
            engine=str(ENGINE_DIR / "src"),
            binary=str(env.binary),
            model=str(env.model),
            projector=str(env.projector),
            log=str(env.log),
            pid=str(env.pid_file),
        )
    )
    worker = subprocess.Popen(  # noqa: S603 - fixed argv
        [sys.executable, "-I", str(script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert worker.stdout is not None
    line = worker.stdout.readline()
    assert line.startswith("http://127.0.0.1:"), worker.stderr.read() if worker.stderr else line
    return worker


def test_closing_the_worker_input_stops_the_server(env: Env) -> None:
    """Normal exit (input closed) runs the exit hook and stops the server."""
    worker = _start_worker(env)
    pid = env.start_pids()[0]
    assert _alive(pid)
    assert worker.stdin is not None
    worker.stdin.close()
    worker.wait(timeout=20)
    assert _wait_dead(pid)
    assert not env.pid_file.exists()


def test_sigterm_to_the_worker_stops_the_server(env: Env) -> None:
    """The host closes a worker with SIGTERM; the server must not outlive it."""
    worker = _start_worker(env)
    pid = env.start_pids()[0]
    worker.send_signal(signal.SIGTERM)
    worker.wait(timeout=20)
    assert worker.returncode == -signal.SIGTERM, "the worker still ends by SIGTERM"
    assert _wait_dead(pid)
    assert not env.pid_file.exists()


def test_a_server_left_by_a_killed_worker_is_stopped_by_the_next_start(env: Env) -> None:
    """SIGKILL leaves the server running; the next worker stops it, then starts its own."""
    worker = _start_worker(env)
    old = env.start_pids()[0]
    worker.kill()
    worker.wait(timeout=20)
    assert _alive(old), "SIGKILL gives the worker no chance to stop its server"
    env.make().ensure_started()
    assert _wait_dead(old)
    assert len(env.start_pids()) == 2


def test_an_unrelated_process_named_in_the_pid_file_is_left_alone(env: Env) -> None:
    """A pid whose command line does not hold the engine's binary path is never stopped."""
    other = subprocess.Popen(["sleep", "30"])  # noqa: S603, S607 - fixed argv
    try:
        env.pid_file.write_text(json.dumps({"pid": other.pid, "binary": str(env.binary)}))
        env.make().ensure_started()
        assert other.poll() is None, "the unrelated process must still run"
    finally:
        other.kill()
        other.wait()


def test_a_pid_file_for_a_dead_process_is_replaced(env: Env) -> None:
    """A pid file whose process is gone is ignored and rewritten."""
    env.pid_file.write_text(json.dumps({"pid": 2**22 + 12345, "binary": str(env.binary)}))
    env.make().ensure_started()
    record = json.loads(env.pid_file.read_text())
    assert record["pid"] == env.start_pids()[0]


def test_an_unreadable_pid_file_is_ignored(env: Env) -> None:
    """Garbage in the pid file does not block a start."""
    env.pid_file.write_text("not json")
    env.make().ensure_started()
    assert len(env.start_lines()) == 1
