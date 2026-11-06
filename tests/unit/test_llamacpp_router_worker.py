"""Shared helpers of the router tests, and a worker process (tasks 3.5, 4.1 to 4.3).

The file has no tests of its own. Run as a script (``python <this file>``), it
is one extra OMRS process: it reads one JSON command per line and answers one
JSON line per command, through the real ``RuntimeManager`` and
``RouterLease``. Several commands may run at once; each answer carries the
command's ``tag``.

Commands: ``open`` (spec dict, entries, decision models), ``request`` (model,
path, ``hold`` seconds inside the model session), ``update`` (entries),
``leave``, ``abandon`` (exit with no leave) and ``exit``.
"""

from __future__ import annotations

import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

EMBED = "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0"
CHAT = "Qwen/Qwen3-4B-GGUF:Q8_0"
CLEF = "Clef/Flash-GGUF:Q8_0"


def free_port() -> int:
    """Return a loopback port that was free a moment ago."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def entry(model: str, file: str, **preset: Any) -> dict[str, Any]:
    """Return one entry as plain data (preset keys with ``_`` become ``-``)."""
    return {
        "model": model,
        "file": file,
        "projector": None,
        "sha256": None,
        "projector_sha256": None,
        "preset": {key.replace("_", "-"): value for key, value in preset.items()},
    }


def fixed_spec(fake: Any, port: int) -> Any:
    """Return the fake's fixed-port single-server spec (see ``FakeLlama.single``)."""
    return fake.single(port)


def as_entries(items: list[dict[str, Any]]) -> list[SimpleNamespace]:
    """Turn plain entry dicts into attribute objects the writer reads."""
    return [SimpleNamespace(**item) for item in items]


class Worker:
    """One worker process driven over standard input and output."""

    def __init__(self) -> None:
        self.proc = subprocess.Popen(  # noqa: S603 - fixed argv, repo test file
            [sys.executable, str(Path(__file__).resolve())],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
        )
        self._answers: dict[str, queue.Queue[dict[str, Any]]] = {}
        self._guard = threading.Lock()
        self._count = 0
        threading.Thread(target=self._pump, daemon=True).start()

    def _box(self, tag: str) -> queue.Queue[dict[str, Any]]:
        with self._guard:
            return self._answers.setdefault(tag, queue.Queue())

    def _pump(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            answer = json.loads(line)
            self._box(str(answer.get("tag"))).put(answer)

    def send(self, cmd: str, **payload: Any) -> str:
        """Send one command; return its tag."""
        with self._guard:
            self._count += 1
            tag = str(self._count)
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps({"cmd": cmd, "tag": tag, **payload}) + "\n")
        self.proc.stdin.flush()
        return tag

    def read(self, tag: str, timeout: float = 60.0) -> dict[str, Any]:
        """Wait for the answer of *tag*."""
        return self._box(tag).get(timeout=timeout)

    def call(self, cmd: str, timeout: float = 60.0, **payload: Any) -> dict[str, Any]:
        """Send one command and wait for its answer."""
        return self.read(self.send(cmd, **payload), timeout)

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


class RouterRig:
    """A fake router install, model files and worker processes, with cleanup."""

    def __init__(self, folder: Path) -> None:
        from tests.fixtures.llamacpp.install import install_fake_server, write_fake_env

        self.folder = folder
        self.binary = install_fake_server(folder / "bin")
        self.starts_file = folder / "starts.txt"
        self.models = folder / "models"
        self.models.mkdir()
        self.port = free_port()
        self.workers: list[Worker] = []
        self.managers: list[Any] = []
        self._write_fake_env = write_fake_env
        self.set_env()

    def set_env(self, **values: object) -> None:
        """Set the fake's behaviour for the next router start."""
        self._write_fake_env(self.binary, FAKE_LLAMA_STARTS=str(self.starts_file), **values)

    def starts(self) -> int:
        """Return how many router processes started."""
        if not self.starts_file.exists():
            return 0
        return len(self.starts_file.read_text(encoding="utf-8").splitlines())

    def file(self, name: str) -> str:
        """Return the path of a model file, created on first use."""
        path = self.models / name
        if not path.exists():
            path.write_bytes(b"GGUF " + name.encode())
        return str(path)

    def spec(self, **overrides: Any) -> Any:
        """Return the managed router spec for this rig."""
        from omrs.integrations.llamacpp_runtime.router_spec import router_spec
        from omrs.integrations.llamacpp_runtime.state import state_root

        values: dict[str, Any] = {
            "binary": str(self.binary),
            "root": state_root(),
            "port": self.port,
            "models_max": 4,
            "memory_margin_mib": 0,
        }
        values.update(overrides)
        return router_spec(**values)

    def entries(self, chat_ctx: int = 8192) -> list[dict[str, Any]]:
        """Return the three standard entries."""
        return [
            entry(
                EMBED,
                self.file("e.gguf"),
                embeddings=True,
                pooling="last",
                ctx_size=8192,
                batch_size=8192,
                ubatch_size=8192,
                parallel=1,
            ),
            entry(CHAT, self.file("c.gguf"), ctx_size=chat_ctx, parallel=2),
            entry(CLEF, self.file("clef.gguf"), parallel=1),
        ]

    def manager(self) -> Any:
        """Return an in-process manager closed at cleanup."""
        from omrs.integrations.llamacpp_runtime.manager import RuntimeManager

        manager = RuntimeManager(exit_hook=False)
        self.managers.append(manager)
        return manager

    def worker(self, **open_args: Any) -> Worker:
        """Start one worker and open the router in it."""
        worker = Worker()
        self.workers.append(worker)
        answer = worker.call(
            "open",
            spec=open_args.pop("spec", self.spec()).to_dict(),
            entries=open_args.pop("entries", self.entries()),
            decision=open_args.pop("decision", []),
        )
        assert answer["ok"], answer
        return worker

    def cleanup(self) -> None:
        """Close managers and workers, then kill any router left."""
        from omrs.integrations.llamacpp_runtime.router_spec import router_dir
        from omrs.integrations.llamacpp_runtime.state import read_server_record, state_root

        for manager in self.managers:
            manager.close()
        for worker in self.workers:
            worker.close()
        record = read_server_record(router_dir(state_root()))
        if record is not None and record.pid > 0:
            import signal

            try:
                os.killpg(record.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


def rig_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    """Body of the ``rig`` fixture the router test files declare."""
    from omrs.integrations.llamacpp_runtime import process, readiness

    monkeypatch.setattr(process, "HEALTH_POLL_SECONDS", 0.05)
    monkeypatch.setattr(readiness, "LOAD_POLL_SECONDS", 0.05)
    rig = RouterRig(tmp_path)
    try:
        yield rig
    finally:
        rig.cleanup()


# ── The worker process ──────────────────────────────────────────────────


def _say(lock: threading.Lock, payload: dict[str, Any]) -> None:
    with lock:
        print(json.dumps(payload, default=str), flush=True)


def _request(router: Any, payload: dict[str, Any]) -> dict[str, Any]:
    import httpx

    from omrs.integrations.llamacpp_runtime.lease import RuntimeUnavailable
    from omrs.integrations.llamacpp_runtime.model_reasons import ModelUnavailable

    model = payload["model"]
    try:
        with router.model_session(model) as url:
            entered = time.monotonic()
            reply = httpx.post(
                f"{url}{payload.get('path', '/v1/chat/completions')}",
                json={"model": model},
                timeout=30,
            )
            time.sleep(float(payload.get("hold", 0)))
            left = time.monotonic()
    except (ModelUnavailable, RuntimeUnavailable) as error:
        return {"ok": False, "reason": error.reason}
    except httpx.HTTPError as error:
        return {"ok": False, "reason": f"http-{type(error).__name__}"}
    return {"ok": True, "status": reply.status_code, "entered": entered, "left": left}


class _Active:
    """Counts request threads, so ``leave`` waits for them (a caller rule)."""

    def __init__(self) -> None:
        self.count = 0
        self.cond = threading.Condition()

    def wait_idle(self) -> None:
        with self.cond:
            self.cond.wait_for(lambda: self.count == 0)


def main() -> int:
    """Read commands until ``exit`` or end of input."""
    from omrs.integrations.llamacpp_runtime import process, readiness
    from omrs.integrations.llamacpp_runtime.manager import RuntimeManager
    from omrs.integrations.llamacpp_runtime.router_lease import open_router
    from omrs.integrations.llamacpp_runtime.spec import RuntimeSpec

    process.HEALTH_POLL_SECONDS = 0.05
    readiness.LOAD_POLL_SECONDS = 0.05
    manager = RuntimeManager()
    lock = threading.Lock()
    active = _Active()
    router: Any = None
    for raw in sys.stdin:
        payload = json.loads(raw)
        tag, cmd = payload.get("tag"), payload.get("cmd")
        if cmd == "open":
            router = open_router(
                manager,
                RuntimeSpec.from_dict(payload["spec"]),
                as_entries(payload["entries"]),
                decision_models=payload.get("decision", ()),
            )
            _say(lock, {"tag": tag, "ok": True})
        elif cmd == "request":

            def run(body: dict[str, Any] = payload, tag: Any = tag, lease: Any = router) -> None:
                _say(lock, {"tag": tag, **_request(lease, body)})

            with active.cond:
                active.count += 1

            def counted(work: Any = run) -> None:
                try:
                    work()
                finally:
                    with active.cond:
                        active.count -= 1
                        active.cond.notify_all()

            threading.Thread(target=counted, daemon=True).start()
        elif cmd == "update":
            result = router.update_entries(as_entries(payload["entries"]))
            _say(lock, {"tag": tag, "ok": True, "result": result})
        elif cmd == "leave":
            active.wait_idle()
            router.leave()
            _say(lock, {"tag": tag, "ok": True})
        elif cmd == "abandon":
            sys.stdout.flush()
            os._exit(0)
        elif cmd == "exit":
            _say(lock, {"tag": tag, "ok": True})
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
