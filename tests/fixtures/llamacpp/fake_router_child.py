"""One loaded model of the fake router: a tiny real child process.

The router (:mod:`fake_router`) starts one of these per loaded model with
``--router-child``, in the router's own process group, as the real
``llama-server`` router does. The child ends when its stdin pipe from the
router closes (the b11941 mechanism, ``server-common.cpp``), and on SIGTERM (the
default action; the child installs no handler).

Behaviour comes from environment variables the router passes on:

``FAKE_LLAMA_LOAD_DELAY``
    Seconds the child waits before it serves (a slow load).
``FAKE_LLAMA_LOAD_FAIL``
    Comma-separated model names whose load fails (exit 1 after the delay);
    ``*`` fails every model.
``FAKE_LLAMA_CONTENT`` and ``FAKE_LLAMA_TOKENS``
    The chat answer text and the token count, as in the single server.
``FAKE_LLAMA_REQUESTS``
    A file; each POST appends its JSON body as one line.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

#: Command-line flag that turns the fake program into a router child.
CHILD_FLAG = "--router-child"


def _arg(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1]


def _exit_when_stdin_closes() -> None:
    """End the process at end-of-file on stdin (the router died or unloaded)."""
    stream = sys.stdin.buffer
    while stream.read(4096):
        pass
    os._exit(0)


def load_fails(alias: str) -> bool:
    """Return whether ``FAKE_LLAMA_LOAD_FAIL`` names *alias* (or ``*``)."""
    names = [n.strip() for n in os.environ.get("FAKE_LLAMA_LOAD_FAIL", "").split(",")]
    return "*" in names or alias in names


def _answer(path: str, alias: str, embedding: list[float]) -> dict[str, Any]:
    """Return the fixed answer body for a POST to *path*."""
    if path == "/v1/embeddings":
        return {
            "object": "list",
            "data": [{"object": "embedding", "index": 0, "embedding": embedding}],
            "model": alias,
        }
    content = os.environ.get("FAKE_LLAMA_CONTENT", "[]")
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "text": content,
                "finish_reason": "stop",
            }
        ],
        "usage": {"completion_tokens": int(os.environ.get("FAKE_LLAMA_TOKENS", "5"))},
        "model": alias,
    }


def run_child(
    argv: list[str], embedding: list[float], server_class: type[ThreadingHTTPServer]
) -> int:
    """Run one model child until its stdin closes.

    Args:
        argv: The child's command line after the program name.
        embedding: The vector ``POST /v1/embeddings`` returns.
        server_class: The HTTP server class (the fake's DNS-free subclass).

    Returns:
        0 when the server stops. In practice the process ends with
        ``os._exit``: 0 at end of stdin, 1 when the load fails.
    """
    alias = _arg(argv, "--alias")
    port = int(_arg(argv, "--port"))
    threading.Thread(target=_exit_when_stdin_closes, daemon=True).start()
    time.sleep(float(os.environ.get("FAKE_LLAMA_LOAD_DELAY", "0") or "0"))
    if load_fails(alias):
        print(f"load_model: failed to load model {alias}", file=sys.stderr, flush=True)
        # A normal exit would wait on the stdin thread and abort (-6).
        os._exit(1)

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
            if self.path == "/health":
                self._send(200, {"status": "ok"})
            else:
                self._send(404, {"error": {"message": "not found"}})

        def do_POST(self) -> None:  # noqa: N802 - http.server API
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            record = os.environ.get("FAKE_LLAMA_REQUESTS")
            if record:
                with open(record, "a", encoding="utf-8") as handle:
                    handle.write(body.decode() + "\n")
            self._send(200, _answer(self.path, alias, embedding))

    server_class(("127.0.0.1", port), Handler).serve_forever()
    return 0
