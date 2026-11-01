"""Fake OCR worker that is a client of a ``llama-server`` (stdlib only).

It speaks the same JSON Lines protocol as ``stub_worker.py`` and, on each
request, posts the PDF path to ``$OMRS_OCR_RUNTIME_URL/v1/chat/completions``.
The fake ``llama-server`` of ``tests/fixtures/llamacpp`` records that body, so a
test can count what reached each runtime. The Markdown answer names the URL
the worker saw, its own pid and the completion text.

Modes (``--mode``):

- ``echo``: post to the runtime when the variable is set, then answer;
- ``crash``: exit with status 3 as soon as a request arrives (after dispatch).

``--backend-id ID`` sets the ``backend_id`` of the fingerprint. Unknown
arguments are ignored, so the engine launcher may pass ``-m
omrs_ocr_worker_core``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

from stub_worker import _emit, _failure, stub_fingerprint_payload

URL_ENV = "OMRS_OCR_RUNTIME_URL"


def _markdown(pdf_path: str, content: str) -> str:
    url = os.environ.get(URL_ENV, "<absent>")
    return f"url={url}\npid={os.getpid()}\npath={pdf_path}\n{content}"


def _post(url: str, pdf_path: str) -> str:
    body = json.dumps({"messages": [{"role": "user", "content": pdf_path}]}).encode()
    request = urllib.request.Request(  # noqa: S310 - loopback test URL
        f"{url}/v1/chat/completions", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        answer = json.loads(response.read())
    return str(answer["choices"][0]["message"]["content"])


def _answer(request: dict) -> dict:
    version = request.get("protocol_version", "1.0")
    url = os.environ.get(URL_ENV)
    try:
        content = _post(url, request["pdf_path"]) if url else ""
    except (OSError, urllib.error.URLError, KeyError, ValueError):
        failure = _failure(request["id"], version)
        failure["error"] = {"code": "runtime_request_failed", "message": "runtime unreachable"}
        return failure
    return {
        "id": request["id"],
        "protocol_version": version,
        "type": "parse_result",
        "ok": True,
        "markdown": _markdown(request["pdf_path"], content),
        "metadata": {
            "ocr_backend": "runtime-worker",
            "page_count": 1,
            "output_schema": {"id": "omrs.ocr.parse_output", "version": "1"},
        },
    }


def main() -> int:
    """Run the capability probe or the request loop."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("echo", "crash"), default="echo")
    parser.add_argument("--backend-id", default="runtime_worker")
    parser.add_argument("--capabilities", nargs="?", const="json", default=None)
    args, _ignored = parser.parse_known_args()
    if args.capabilities is not None:
        _emit(stub_fingerprint_payload(args.backend_id))
        return 0
    for raw in sys.stdin:
        if not raw.strip():
            continue
        request = json.loads(raw)
        if args.mode == "crash":
            sys.stderr.write("runtime-worker crashing on purpose\n")
            sys.exit(3)
        _emit(_answer(request))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
