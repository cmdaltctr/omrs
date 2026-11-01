"""A fake ``llama-server`` for the shared runtime manager tests.

Tests copy this file to ``<tmp>/llama-server`` behind a Python shebang and
make it executable (see :mod:`tests.fixtures.llamacpp.install`). CI has no
GPU and no model, so this script stands in for the real binary. It speaks
only what the manager and its clients use:

- ``--version`` prints ``version: 0.7.0-dev (build <build>, commit fake)``;
- ``GET /health`` answers 503 until the health delay has passed, then 200;
- ``GET /props`` answers the build as ``{PROPS_BUILD_FIELD: "b<build>-fake"}``,
  the shape of a real llama-server (``build_info``, for example
  ``b11671-ba3c05f71``);
- ``POST /v1/chat/completions`` records the request body and answers a
  fixed completion;
- ``POST /v1/embeddings`` records the request body and answers a fixed
  vector.

Behaviour comes from environment variables, which the child process
inherits from the test:

``FAKE_LLAMA_BUILD``
    Build number for ``--version`` and ``GET /props`` (default 11941).
``FAKE_LLAMA_STARTS``
    A file; each server start appends one line ``<pid> <argv as JSON>``.
    Tests count the lines to prove how many servers started.
``FAKE_LLAMA_REQUESTS``
    A file; each POST appends its JSON body as one line.
``FAKE_LLAMA_HEALTH_DELAY``
    Seconds before ``/health`` turns healthy (default 0).
``FAKE_LLAMA_NEVER_HEALTHY``
    When set, ``/health`` answers 503 for ever.
``FAKE_LLAMA_REQUEST_DELAY``
    Seconds each POST sleeps before it answers, to hold a request busy.
``FAKE_LLAMA_BIND_FAILS``
    A file whose text is the number of starts that must fail. Each failed
    start prints llama-server's bind error line, decrements the file and
    exits 1.
``FAKE_LLAMA_EXIT_AFTER``
    A number of answered POSTs; the process then exits 1 at once, to act
    as a crash between two requests.
``FAKE_LLAMA_CONTENT`` and ``FAKE_LLAMA_TOKENS``
    The completion text and the ``completion_tokens`` usage value.
``FAKE_LLAMA_STATUS``
    When set, every chat request answers with this HTTP status and an
    error body.
``FAKE_LLAMA_BAD_JSON``
    When set, every chat request answers 200 with a body that is not JSON.
``FAKE_LLAMA_SPAM_BYTES``
    Bytes to write to standard error at start, to fill the log.
``FAKE_LLAMA_LOG_REQUESTS``
    When set, each POST prints one line ``request <path>`` to standard error.
``FAKE_LLAMA_CRASH_ON_REQUEST``
    When set, each POST exits the process at once with no answer.
``FAKE_LLAMA_HEALTH_SLEEP_FILE``
    A file path; while the file exists, each ``/health`` sleeps the seconds
    written in it before it answers (a slow, busy server).
``FAKE_LLAMA_EARLY_EXIT``
    A counter file; each start adds 1 to it and exits 1 with no bind line.
``FAKE_LLAMA_FDS``
    A file; each start writes a JSON object that names the type of each open
    descriptor from 0 to 63 (``fifo``, ``reg``, ``chr``, ``sock`` or
    ``other``), to prove what the child inherited.

``-np 1`` on the command line makes the fake answer one POST at a time, as a
one-slot llama-server queues a second request until the first ends.

The manager gives the child a minimal environment (``PATH``, ``HOME``,
``LANG``, ``TMPDIR``), so the variables above cannot travel from the test
through it. Tests therefore also write them to ``fake-llama.json`` beside the
program (see :func:`tests.fixtures.llamacpp.install.write_fake_env`); the
fake reads that file first.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

#: The ``GET /props`` field that holds the build. A real llama-server b11671
#: reports ``build_info``; task 6.4 of the change confirms it on b11941.
PROPS_BUILD_FIELD = "build_info"

#: The line a real llama-server prints when the port is taken (from the
#: ``server.cpp`` source; task 6.4 can check it on b11941). The manager
#: matches the fixed part ``couldn't bind HTTP server socket`` to decide on a
#: bind retry (design D5).
BIND_ERROR_LINE = "main: couldn't bind HTTP server socket, hostname: 127.0.0.1, port: {port}"

#: The fixed embedding vector of ``POST /v1/embeddings``.
EMBEDDING_VECTOR = [0.1, 0.2, 0.3]


def _arg(name: str) -> str:
    return sys.argv[sys.argv.index(name) + 1]


def _bind_fails() -> int | None:
    """Return the remaining number of starts that must fail, if any."""
    path = os.environ.get("FAKE_LLAMA_BIND_FAILS")
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return int(handle.read().strip() or "0")
    except (OSError, ValueError):
        return None


def _decrement_bind_fails(path: str) -> None:
    with open(path, encoding="utf-8") as handle:
        left = int(handle.read().strip() or "0")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(str(max(0, left - 1)))


#: The side file beside the program that carries the ``FAKE_LLAMA_*`` values.
SIDE_ENV_FILE = "fake-llama.json"


def _load_side_env() -> None:
    """Merge ``fake-llama.json`` beside the program into the environment."""
    path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), SIDE_ENV_FILE)
    try:
        with open(path, encoding="utf-8") as handle:
            values = json.load(handle)
    except (OSError, ValueError):
        return
    for name, value in values.items():
        if name.startswith("FAKE_LLAMA_"):
            os.environ[name] = str(value)


def _descriptor_types() -> dict[str, str]:
    """Return the type of every open descriptor from 0 to 63."""
    kinds: dict[str, str] = {}
    for fd in range(64):
        try:
            mode = os.fstat(fd).st_mode
        except OSError:
            continue
        if stat.S_ISFIFO(mode):
            kinds[str(fd)] = "fifo"
        elif stat.S_ISREG(mode):
            kinds[str(fd)] = "reg"
        elif stat.S_ISCHR(mode):
            kinds[str(fd)] = "chr"
        elif stat.S_ISSOCK(mode):
            kinds[str(fd)] = "sock"
        else:
            kinds[str(fd)] = "other"
    return kinds


def _bump_counter(path: str) -> None:
    try:
        with open(path, encoding="utf-8") as handle:
            count = int(handle.read().strip() or "0")
    except (OSError, ValueError):
        count = 0
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(str(count + 1))


def main() -> int:
    """Run the fake server (or print its version)."""
    fds = _descriptor_types()
    _load_side_env()
    if "--version" in sys.argv:
        build = os.environ.get("FAKE_LLAMA_BUILD", "11941")
        print(f"version: 0.7.0-dev (build {build}, commit fake)")
        return 0
    if os.environ.get("FAKE_LLAMA_FDS"):
        with open(os.environ["FAKE_LLAMA_FDS"], "w", encoding="utf-8") as handle:
            json.dump(fds, handle)
    if os.environ.get("FAKE_LLAMA_EARLY_EXIT"):
        _bump_counter(os.environ["FAKE_LLAMA_EARLY_EXIT"])
        print("main: model failed to load", file=sys.stderr)
        return 1
    bind = _bind_fails()
    if bind is not None and bind > 0:
        _decrement_bind_fails(os.environ["FAKE_LLAMA_BIND_FAILS"])
        print(BIND_ERROR_LINE.format(port=_arg("--port")), file=sys.stderr)
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
    exit_after = int(os.environ.get("FAKE_LLAMA_EXIT_AFTER", "0") or "0")
    served = 0
    served_lock = threading.Lock()
    one_slot = "-np" in sys.argv and _arg("-np") == "1"
    slot = threading.Lock()

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
                sleep_file = os.environ.get("FAKE_LLAMA_HEALTH_SLEEP_FILE")
                if sleep_file and os.path.exists(sleep_file):
                    with open(sleep_file, encoding="utf-8") as handle:
                        time.sleep(float(handle.read().strip() or "0"))
                healthy = not never and time.monotonic() >= ready_at
                self._send(200 if healthy else 503, {"status": "ok" if healthy else "loading"})
            elif self.path == "/props":
                build = int(os.environ.get("FAKE_LLAMA_BUILD", "11941"))
                self._send(200, {PROPS_BUILD_FIELD: f"b{build}-fake"})
            else:
                self._send(404, {})

        def do_POST(self) -> None:  # noqa: N802 - http.server API
            if one_slot:
                with slot:
                    self._post()
            else:
                self._post()

        def _post(self) -> None:
            nonlocal served
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if os.environ.get("FAKE_LLAMA_CRASH_ON_REQUEST"):
                os._exit(1)
            if os.environ.get("FAKE_LLAMA_LOG_REQUESTS"):
                print(f"request {self.path}", file=sys.stderr, flush=True)
            requests = os.environ.get("FAKE_LLAMA_REQUESTS")
            if requests:
                with open(requests, "a", encoding="utf-8") as handle:
                    handle.write(body.decode() + "\n")
            delay = float(os.environ.get("FAKE_LLAMA_REQUEST_DELAY", "0") or "0")
            if delay:
                time.sleep(delay)
            if os.environ.get("FAKE_LLAMA_STATUS"):
                self._send(int(os.environ["FAKE_LLAMA_STATUS"]), {"error": {"message": "boom"}})
            elif os.environ.get("FAKE_LLAMA_BAD_JSON"):
                data = b"this is not json"
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            elif self.path == "/v1/embeddings":
                self._send(
                    200,
                    {
                        "object": "list",
                        "data": [
                            {"object": "embedding", "index": 0, "embedding": EMBEDDING_VECTOR}
                        ],
                        "model": "fake",
                    },
                )
            else:
                self._send(
                    200,
                    {
                        "choices": [
                            {
                                "message": {"content": os.environ.get("FAKE_LLAMA_CONTENT", "[]")},
                                # ``/v1/completions`` clients read ``text``.
                                "text": os.environ.get("FAKE_LLAMA_CONTENT", "[]"),
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "completion_tokens": int(os.environ.get("FAKE_LLAMA_TOKENS", "5"))
                        },
                    },
                )
            with served_lock:
                served += 1
                crash = exit_after > 0 and served >= exit_after
            if crash:
                # Act as a crash between two requests: die with the answer on
                # the wire and the socket still half open.
                os._exit(1)

    server = ThreadingHTTPServer(("127.0.0.1", int(_arg("--port"))), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    while True:
        time.sleep(0.2)


if __name__ == "__main__":
    raise SystemExit(main())
