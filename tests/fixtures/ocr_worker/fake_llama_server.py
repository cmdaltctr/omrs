"""A fake ``llama-server`` for the dots-mocr-llamacpp engine tests.

Tests copy this file to ``<tmp>/llama-server`` behind a Python shebang and
make it executable. CI has no GPU and no model, so this script stands in
for the real binary. It speaks only what the engine uses:

- ``--version`` prints ``version: 0.7.0-dev (build <build>, commit fake)``;
- ``GET /health`` answers 503 until the start delay has passed, then 200;
- ``POST /v1/chat/completions`` records the request body and answers a
  fixed completion.

Behaviour comes from environment variables, which the child process
inherits from the test:

``FAKE_LLAMA_BUILD``
    Build number for ``--version`` (default 11941).
``FAKE_LLAMA_STARTS``
    A file; each server start appends one line ``<pid> <argv as JSON>``.
``FAKE_LLAMA_REQUESTS``
    A file; each chat request appends its JSON body as one line.
``FAKE_LLAMA_HEALTH_DELAY``
    Seconds before ``/health`` turns healthy (default 0).
``FAKE_LLAMA_NEVER_HEALTHY``
    When set, ``/health`` answers 503 for ever.
``FAKE_LLAMA_FAIL_ONCE``
    A file path. If it does not exist, create it and exit with status 1
    straight away, as a server does when its port is taken.
``FAKE_LLAMA_CONTENT`` and ``FAKE_LLAMA_TOKENS``
    The completion text and the ``completion_tokens`` usage value.
``FAKE_LLAMA_STATUS``
    When set, every chat request answers with this HTTP status and an error body.
``FAKE_LLAMA_BAD_JSON``
    When set, every chat request answers 200 with a body that is not JSON.
``FAKE_LLAMA_SPAM_BYTES``
    Bytes to write to standard error at start, to fill the log.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _arg(name: str) -> str:
    return sys.argv[sys.argv.index(name) + 1]


def main() -> int:
    """Run the fake server (or print its version)."""
    if "--version" in sys.argv:
        build = os.environ.get("FAKE_LLAMA_BUILD", "11941")
        print(f"version: 0.7.0-dev (build {build}, commit fake)")
        return 0
    fail_once = os.environ.get("FAKE_LLAMA_FAIL_ONCE")
    if fail_once and not os.path.exists(fail_once):
        open(fail_once, "w").close()
        print("couldn't bind HTTP server socket: address already in use", file=sys.stderr)
        return 1
    starts = os.environ.get("FAKE_LLAMA_STARTS")
    if starts:
        with open(starts, "a", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()} {json.dumps(sys.argv[1:])}\n")
    spam = int(os.environ.get("FAKE_LLAMA_SPAM_BYTES", "0"))
    for _ in range(spam // 100):
        print("x" * 99, file=sys.stderr, flush=True)
    ready_at = time.monotonic() + float(os.environ.get("FAKE_LLAMA_HEALTH_DELAY", "0"))
    never = bool(os.environ.get("FAKE_LLAMA_NEVER_HEALTHY"))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - base signature
            return

        def _send(self, status: int, body: dict[str, object]) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802 - http.server API
            if self.path == "/health":
                healthy = not never and time.monotonic() >= ready_at
                self._send(200 if healthy else 503, {"status": "ok" if healthy else "loading"})
            else:
                self._send(404, {})

        def do_POST(self) -> None:  # noqa: N802 - http.server API
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            requests = os.environ.get("FAKE_LLAMA_REQUESTS")
            if requests:
                with open(requests, "a", encoding="utf-8") as handle:
                    handle.write(body.decode() + "\n")
            if os.environ.get("FAKE_LLAMA_STATUS"):
                self._send(int(os.environ["FAKE_LLAMA_STATUS"]), {"error": {"message": "boom"}})
                return
            if os.environ.get("FAKE_LLAMA_BAD_JSON"):
                data = b"this is not json"
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self._send(
                200,
                {
                    "choices": [
                        {
                            "message": {"content": os.environ.get("FAKE_LLAMA_CONTENT", "[]")},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"completion_tokens": int(os.environ.get("FAKE_LLAMA_TOKENS", "5"))},
                },
            )

    server = ThreadingHTTPServer(("127.0.0.1", int(_arg("--port"))), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    while True:
        time.sleep(0.2)


if __name__ == "__main__":
    raise SystemExit(main())
