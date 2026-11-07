"""Router mode of the fake ``llama-server`` (design D16, b11941 behaviour).

Started as ``llama-server --models-preset <ini> [--models-max N]
[--models-memory-margin MiB] --host H --port P``. The INI file has one
section per model (the section name is the model name; ``model = <path>``
and other keys are the preset). The router starts empty: ``/health`` answers
200 with no model loaded.

Served routes, copied from the spike evidence (``evidence/spike-1.2.md``):

- ``GET /health`` and ``GET /props`` (``role`` is ``router``);
- ``GET /v1/models`` and ``GET /models`` list every section with ``status``
  (``value`` unloaded, loading, loaded or failed; ``args``; ``preset``);
- ``GET /models?reload=1`` re-reads the file. It unloads only models whose
  options changed or that left the file, keeps unchanged children (same pid)
  and lists added sections as unloaded. The router compares parsed options,
  so a reorder or a comment line unloads nothing;
- ``POST /models/load`` and ``POST /models/unload`` with ``{"model": ...}``:
  an unknown name gives 404 on load and 400 on unload;
- ``POST /v1/embeddings``, ``/v1/chat/completions``, ``/v1/completions`` and
  ``/v1/systemone`` route by the ``model`` field. A model that is not loaded
  loads first (autoload). An unknown name gives 400.

Each loaded model is one real child process (:mod:`fake_router_child`) in the
router's process group, so a group SIGTERM ends all of them. A child ends
when its stdin pipe from the router closes, so SIGKILL of the router alone
leaves none behind. ``--models-memory-margin`` is accepted and ignored; so is
the load limit ``--models-max`` (it only shows in ``GET /props``).

The load behaviour comes from ``FAKE_LLAMA_LOAD_DELAY`` and
``FAKE_LLAMA_LOAD_FAIL`` (see :mod:`fake_router_child`). The router also
honours ``FAKE_LLAMA_HEALTH_DELAY`` and ``FAKE_LLAMA_NEVER_HEALTHY`` through
the values its caller passes.
"""

from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from fake_router_child import CHILD_FLAG

#: Paths the router routes by the ``model`` field.
ROUTED_PATHS = ("/v1/embeddings", "/v1/chat/completions", "/v1/completions", "/v1/systemone")

#: Longest a request waits for an autoloading model, in seconds.
AUTOLOAD_WAIT_SECONDS = 60.0

#: Longest an unloading child gets to end before the router kills it.
UNLOAD_WAIT_SECONDS = 5.0


def parse_preset(text: str) -> dict[str, dict[str, str]]:
    """Parse the INI *text* into ``{section: {key: value}}``.

    Keys keep their case and order. Lines before the first section, blank
    lines and ``#`` or ``;`` comments are skipped.
    """
    sections: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1].strip(), {})
        elif current is not None and "=" in line:
            key, _, value = line.partition("=")
            current[key.strip()] = value.strip()
    return sections


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Model:
    """One preset section and, while loaded, its child process."""

    def __init__(self, name: str, options: dict[str, str]) -> None:
        self.name = name
        self.options = options
        self.state = "unloaded"
        self.proc: subprocess.Popen[bytes] | None = None
        self.port = 0
        self.exit_code: int | None = None


class Router:
    """The model table, with the load, unload and reload rules."""

    def __init__(self, preset: str, binary: str, embedding: list[float]) -> None:
        self.preset = preset
        self.binary = binary
        self.embedding = embedding
        self.cond = threading.Condition()
        self.models = {n: Model(n, o) for n, o in self._read().items()}

    def _read(self) -> dict[str, dict[str, str]]:
        with open(self.preset, encoding="utf-8") as handle:
            return parse_preset(handle.read())

    def _args(self, model: Model) -> list[str]:
        args = [self.binary, "--host", "127.0.0.1", "--log-colors", "off"]
        args += ["--port", str(model.port), "--alias", model.name]
        for key, value in model.options.items():
            if value.lower() == "true":
                args.append(f"--{key}")
            elif value.lower() != "false":
                args += [f"--{key}", value]
        return args

    def entry(self, model: Model) -> dict[str, Any]:
        """Return the ``GET /v1/models`` item of *model* (call under the lock)."""
        failed = model.state == "failed"
        # b11941 has no ``failed`` value: a failed load is ``unloaded`` with ``failed: true``
        # and the child's ``exit_code`` (server-models.cpp ~2162, ``is_failed()`` in the header).
        status: dict[str, Any] = {
            "value": "unloaded" if failed else model.state,
            "args": self._args(model),
        }
        status["preset"] = f"[{model.name}]\n" + "".join(
            f"{k} = {v}\n" for k, v in model.options.items()
        )
        if failed:
            status["failed"] = True
            status["exit_code"] = model.exit_code
        return {
            "id": model.name,
            "aliases": [],
            "tags": [],
            "object": "model",
            "owned_by": "llamacpp",
            "created": 0,
            "status": status,
            "source": "preset",
            "can_remove": False,
        }

    def listing(self) -> dict[str, Any]:
        """Return the model list body."""
        with self.cond:
            return {"object": "list", "data": [self.entry(m) for m in self.models.values()]}

    def start_load(self, model: Model) -> None:
        """Start the child of *model* (call under the lock; state must be idle)."""
        model.port = _free_port()
        model.exit_code = None
        model.state = "loading"
        script = os.path.abspath(sys.argv[0])
        model.proc = subprocess.Popen(  # noqa: S603 - fixed argv
            [
                sys.executable,
                script,
                CHILD_FLAG,
                "--host",
                "127.0.0.1",
                "--port",
                str(model.port),
                "--alias",
                model.name,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=None,
        )
        threading.Thread(target=self._watch, args=(model, model.proc), daemon=True).start()

    def _watch(self, model: Model, proc: subprocess.Popen[bytes]) -> None:
        """Mark *model* loaded when its child answers ``/health``, failed if it ends."""
        while True:
            code = proc.poll()
            ready = code is None and self._healthy(model.port)
            with self.cond:
                if model.proc is not proc:
                    return  # unloaded or replaced meanwhile
                if code is not None:
                    model.state, model.exit_code, model.proc = "failed", code, None
                elif ready:
                    model.state = "loaded"
                if code is not None or ready:
                    self.cond.notify_all()
                    return
            time.sleep(0.05)

    @staticmethod
    def _healthy(port: int) -> bool:
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            conn.request("GET", "/health")
            return conn.getresponse().status == 200
        except OSError:
            return False

    def stop(self, model: Model) -> None:
        """Stop the child of *model* by closing its stdin (call under the lock)."""
        proc, model.proc = model.proc, None
        model.state = "unloaded"
        if proc is not None and proc.stdin is not None:
            proc.stdin.close()
            try:
                proc.wait(UNLOAD_WAIT_SECONDS)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        self.cond.notify_all()

    def load(self, name: str) -> tuple[int, dict[str, Any]]:
        """Handle ``POST /models/load``."""
        with self.cond:
            model = self.models.get(name)
            if model is None:
                return 404, _error(404, "File Not Found", "not_found_error")
            if model.state in ("loading", "loaded"):
                return 400, _error(400, "model is already running")
            self.start_load(model)
        return 200, {"success": True}

    def unload(self, name: str) -> tuple[int, dict[str, Any]]:
        """Handle ``POST /models/unload``."""
        with self.cond:
            model = self.models.get(name)
            if model is None:
                return 400, _error(400, "model is not found")
            if model.state not in ("loading", "loaded"):
                return 400, _error(400, "model is not running")
            self.stop(model)
        return 200, {"success": True}

    def reload(self) -> None:
        """Re-read the file; unload changed or removed models, add new ones."""
        fresh = self._read()
        with self.cond:
            for name, model in list(self.models.items()):
                if name not in fresh:
                    self.stop(model)
                    del self.models[name]
                elif fresh[name] != model.options:
                    self.stop(model)
                    model.options = fresh[name]
            for name, options in fresh.items():
                self.models.setdefault(name, Model(name, options))

    def ready_port(self, name: str) -> tuple[int, dict[str, Any] | None]:
        """Return ``(port, None)`` for a loaded model, else ``(0, error body)``.

        Autoload: an idle model starts loading and the call waits for it.
        """
        with self.cond:
            model = self.models.get(name)
            if model is None:
                return 0, _error(400, f"model '{name}' not found")
            if model.state in ("unloaded", "failed"):
                self.start_load(model)
            self.cond.wait_for(lambda: model.state != "loading", AUTOLOAD_WAIT_SECONDS)
            if model.state != "loaded":
                return 0, _error(500, f"model '{name}' failed to load", "server_error")
            return model.port, None


def _error(code: int, message: str, kind: str = "invalid_request_error") -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "type": kind}}


def run_router(
    argv: list[str],
    ready_at: float,
    never: bool,
    props: dict[str, str],
    embedding: list[float],
    server_class: type[ThreadingHTTPServer],
) -> int:
    """Serve the router until it is killed.

    Args:
        argv: The command line after the program name.
        ready_at: ``time.monotonic()`` value after which ``/health`` answers 200.
        never: When true, ``/health`` always answers 503.
        props: The build field for ``GET /props``.
        embedding: The vector the children return for embeddings.
        server_class: The HTTP server class (the fake's DNS-free subclass).
    """
    options = {a: argv[i + 1] for i, a in enumerate(argv[:-1]) if a.startswith("--")}
    router = Router(options["--models-preset"], os.path.abspath(sys.argv[0]), embedding)
    max_models = int(options.get("--models-max", "4"))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:  # noqa: D102
            return

        def _send(self, status: int, body: dict[str, Any]) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802 - http.server API
            url = urlparse(self.path)
            if url.path == "/health":
                healthy = not never and time.monotonic() >= ready_at
                self._send(200 if healthy else 503, {"status": "ok" if healthy else "loading"})
            elif url.path == "/props":
                role = {"role": "router", "max_instances": max_models, "models_autoload": True}
                self._send(200, {**role, **props})
            elif url.path in ("/v1/models", "/models"):
                if parse_qs(url.query).get("reload") == ["1"]:
                    router.reload()
                self._send(200, router.listing())
            else:
                self._send(404, _error(404, "File Not Found", "not_found_error"))

        def do_POST(self) -> None:  # noqa: N802 - http.server API
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                body = {}
            name = body.get("model") if isinstance(body, dict) else None
            path = urlparse(self.path).path
            if path in ("/models/load", "/models/unload"):
                action = router.load if path == "/models/load" else router.unload
                self._send(*action(str(name)))
            elif path in ROUTED_PATHS:
                if not name:
                    self._send(400, _error(400, "model name missing request"))
                    return
                port, error = router.ready_port(str(name))
                if error is not None:
                    self._send(int(error["error"]["code"]), error)
                    return
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
                conn.request("POST", path, raw, {"Content-Type": "application/json"})
                reply = conn.getresponse()
                data = reply.read()
                self.send_response(reply.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self._send(404, _error(404, "File Not Found", "not_found_error"))

    server = server_class(("127.0.0.1", int(options["--port"])), Handler)
    server.daemon_threads = True
    server.serve_forever()
    return 0
