"""Test harness for the shared runtime manager (tasks 1.2, 3 and 4).

:class:`FakeRuntime` installs the fake ``llama-server`` in a temporary folder
and builds the specs the tests join. :class:`ClientProcess` drives one
``client.py`` process (an extra OMRS client). The ``runtime_env`` fixture in
each test module cleans up every client and every fake server it started, so
no process outlives a test.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from omrs.integrations.llamacpp_runtime.spec import (
    DeclaredFile,
    RuntimeSpec,
    ocr_spec,
)

from .install import install_fake_server, read_start_log, write_fake_env

CLIENT = Path(__file__).resolve().parent / "client.py"


def wait_until(predicate: Callable[[], bool], timeout: float = 10.0, step: float = 0.05) -> bool:
    """Poll *predicate* until it is true or *timeout* seconds pass."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


def pid_alive(pid: int) -> bool:
    """Return whether *pid* runs and is not a zombie."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover - exists but not ours
        return True
    out = subprocess.run(  # noqa: S603 - fixed argv
        ["ps", "-o", "stat=", "-p", str(pid)],  # noqa: S607 - ps on PATH
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(out.stdout.strip()) and not out.stdout.strip().startswith("Z")


class FakeRuntime:
    """One fake ``llama-server`` install and its record files."""

    def __init__(self, folder: Path, name: str = "bin") -> None:
        self.folder = folder
        self.binary = install_fake_server(folder / name)
        self.logs = folder / "logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.starts_file = self.logs / f"{name}-starts.txt"
        self.model = folder / "models" / "q.gguf"
        self.model.parent.mkdir(parents=True, exist_ok=True)
        self.model.write_bytes(b"GGUF fake model")
        self.values: dict[str, object] = {}
        self.set_env()

    def set_env(self, **values: object) -> None:
        """Replace the fake's behaviour values (read at each server start)."""
        self.values = {"FAKE_LLAMA_STARTS": str(self.starts_file), **values}
        write_fake_env(self.binary, **self.values)

    def starts(self) -> list[dict[str, Any]]:
        """Return one entry (pid, argv) per server that started."""
        return read_start_log(self.starts_file)

    def single(self, port: int) -> RuntimeSpec:
        """Return a fixed-port managed single-server spec under the ``router`` id.

        The per-role runtime ids retired (one-llamacpp-router, D1). Lease tests
        that check id-free rules (join, adopt, crash, idle, stop) run the fake as
        one plain server under the one fixed-port id left.
        """
        binary = str(self.binary)
        argv = (
            binary,
            "-m",
            str(self.model),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "-c",
            "2048",
        )
        return RuntimeSpec(id="router", role="router", mode="managed", binary=binary, argv=argv)

    def ocr(self, *, flags: tuple[str, ...] = ("-np", "1"), build: int = 11941) -> RuntimeSpec:
        """Return a managed OCR spec on a free port with one declared file."""
        digest = hashlib.sha256(self.model.read_bytes()).hexdigest()
        return ocr_spec(
            engine_folder="fake-engine",
            binary=str(self.binary),
            build=build,
            flags=flags,
            files=(DeclaredFile(flag="-m", path=str(self.model), sha256=digest),),
        )

    def kill_all(self) -> None:
        """SIGKILL every server this install started that still runs."""
        for entry in self.starts():
            pid = int(entry["pid"])
            for kill in (os.killpg, os.kill):
                try:
                    kill(pid, signal.SIGKILL)
                    break
                except (ProcessLookupError, PermissionError):
                    continue


class ClientProcess:
    """One ``client.py`` process that answers one JSON line per command."""

    def __init__(self, *, new_group: bool = False) -> None:
        self.proc = subprocess.Popen(  # noqa: S603 - fixed argv, repo fixture
            [sys.executable, str(CLIENT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            start_new_session=new_group,
        )
        self.pid = self.proc.pid
        self._lines: queue.Queue[str | None] = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def send(self, command: dict[str, Any]) -> None:
        """Write one command and do not wait for its answer."""
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(command) + "\n")
        self.proc.stdin.flush()

    def read(self, timeout: float = 30.0) -> dict[str, Any]:
        """Return the next answer line."""
        line = self._lines.get(timeout=timeout)
        if line is None:
            raise EOFError("the client process ended")
        return json.loads(line)

    def call(self, command: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
        """Send *command* and return its answer."""
        self.send(command)
        return self.read(timeout)

    def join(self, spec: RuntimeSpec, timeout: float = 30.0) -> dict[str, Any]:
        """Join *spec* through the manager in the client."""
        return self.call({"cmd": "join", "spec": spec.to_dict()}, timeout)

    def chat(self, timeout: float = 30.0, request_timeout: float = 30.0) -> dict[str, Any]:
        """Send one chat request through the lease."""
        return self.call(
            {
                "cmd": "request",
                "path": "/v1/chat/completions",
                "body": {"messages": []},
                "timeout": request_timeout,
            },
            timeout,
        )

    def wait(self, timeout: float = 30.0) -> int:
        """Wait for the process to end."""
        return self.proc.wait(timeout=timeout)

    def close(self) -> None:
        """End the process (SIGKILL when it does not end by itself)."""
        if self.proc.poll() is None:
            try:
                assert self.proc.stdin is not None
                self.proc.stdin.close()
            except OSError:
                pass
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)


class RuntimeEnv:
    """Factory of fake installs and client processes with cleanup."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.fakes: list[FakeRuntime] = []
        self.clients: list[ClientProcess] = []
        self.managers: list[Any] = []

    def fake(self, name: str = "bin") -> FakeRuntime:
        """Install one fake server."""
        fake = FakeRuntime(self.folder, name)
        self.fakes.append(fake)
        return fake

    def client(self, *, new_group: bool = False, fast: bool = True) -> ClientProcess:
        """Start one client process (with short health polls when *fast*)."""
        client = ClientProcess(new_group=new_group)
        self.clients.append(client)
        if fast:
            assert client.call({"cmd": "config", "health_poll_seconds": 0.05})["ok"]
        return client

    def manager(self) -> Any:
        """Return an in-process manager with no exit hook (closed at teardown)."""
        from omrs.integrations.llamacpp_runtime.manager import RuntimeManager

        manager = RuntimeManager(exit_hook=False)
        self.managers.append(manager)
        return manager

    def cleanup(self) -> None:
        """Close every manager and client, then kill every fake server left."""
        for manager in self.managers:
            manager.close()
        for client in self.clients:
            client.close()
        for fake in self.fakes:
            fake.kill_all()


def runtime_env_fixture(tmp_path: Path, monkeypatch: Any) -> Iterator[RuntimeEnv]:
    """Body of the ``runtime_env`` fixture each test module declares."""
    from omrs.integrations.llamacpp_runtime import process

    monkeypatch.setattr(process, "HEALTH_POLL_SECONDS", 0.05)
    env = RuntimeEnv(tmp_path)
    try:
        yield env
    finally:
        env.cleanup()
