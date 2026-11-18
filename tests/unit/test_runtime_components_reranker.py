"""Each reranker backend reports its own runtime status (issue #215).

The runtime page asks the backend class for ``runtime_status`` and does not
branch on backend names. The llama.cpp backend reads the router model list.
"""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx
import pytest

from omrs.core.retrieval import registry as retrieval_registry
from omrs.core.retrieval import reranker_llamacpp
from omrs.core.retrieval.runtime_status import RerankerRuntimeStatus
from omrs.transports.api import runtime_components as rc

MODEL = "qwen3-reranker-4b"


class _Models(BaseHTTPRequestHandler):
    names: tuple[str, ...] = ()

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        payload = json.dumps(
            {"data": [{"id": n, "status": {"value": "unloaded"}} for n in self.names]}
        )
        body = payload.encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - http.server API
        return


def _router(names: tuple[str, ...]) -> Iterator[str]:
    handler = type("Handler", (_Models,), {"names": names})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def router_with_model() -> Iterator[str]:
    yield from _router((MODEL, "qwen3-4b"))


@pytest.fixture
def router_without_model() -> Iterator[str]:
    yield from _router(("qwen3-4b",))


def _closed_address() -> str:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return f"http://127.0.0.1:{sock.getsockname()[1]}"


def _item(effective_settings: Any, router_url: str) -> rc.RuntimeItem:
    settings = effective_settings(
        rerank_backend="llamacpp", rerank_model=MODEL, llamacpp_router_url=router_url
    )
    return rc._reranker_item(settings)


def test_llamacpp_reranker_is_ready_when_the_router_lists_the_model(
    router_with_model: str, effective_settings: Any
) -> None:
    item = _item(effective_settings, router_with_model)

    assert item.status == "ready"
    assert item.fix is None


def test_llamacpp_reranker_is_missing_when_the_router_lacks_the_model(
    router_without_model: str, effective_settings: Any
) -> None:
    item = _item(effective_settings, router_without_model)

    assert item.status == "missing"
    assert MODEL in (item.reason or "") and "llama.cpp router" in (item.reason or "")
    assert item.fix is None


def test_llamacpp_reranker_is_unknown_when_the_router_is_down(effective_settings: Any) -> None:
    item = _item(effective_settings, f"{_closed_address()}/v1")

    assert item.status == "unknown"
    assert "llama.cpp router" in (item.reason or "")
    assert item.fix is None


def test_llamacpp_router_check_gives_up_within_two_seconds(
    monkeypatch: pytest.MonkeyPatch, effective_settings: Any
) -> None:
    timeouts: list[float] = []

    def _timed_out(url: str, *, timeout: float) -> None:
        timeouts.append(timeout)
        raise httpx.ReadTimeout("router did not answer")

    monkeypatch.setattr(reranker_llamacpp.httpx, "get", _timed_out)
    item = _item(effective_settings, "http://127.0.0.1:9/v1")

    assert item.status == "unknown"
    assert timeouts and timeouts[0] < 2.0


def test_torch_reranker_without_the_extra_reports_the_onnx_fallback(
    monkeypatch: pytest.MonkeyPatch, effective_settings: Any
) -> None:
    """The torch extra is missing, so ONNX runs. The page says so and offers the ONNX download."""
    monkeypatch.setattr(
        "omrs.core.retrieval.backend._is_torch_extra_available", lambda: False, raising=True
    )
    monkeypatch.setattr(rc, "try_to_load_from_cache", lambda *a, **k: None)
    settings = effective_settings(rerank_backend="torch")

    item = rc._reranker_item(settings)

    assert item.status == "missing"
    assert "torch backend is not available" in (item.reason or "")
    assert "hf download" in (item.fix or "")


def test_a_backend_without_runtime_status_gives_unknown(
    monkeypatch: pytest.MonkeyPatch, effective_settings: Any
) -> None:
    class Dummy:
        pass

    monkeypatch.setattr("omrs.core.retrieval.backend.resolve_reranker_backend", lambda _b: Dummy)

    item = rc._reranker_item(effective_settings(rerank_backend="llamacpp"))

    assert item.status == "unknown"
    assert "llamacpp" in (item.reason or "")
    assert item.fix is None


def test_a_backend_status_is_shown_as_reported(
    monkeypatch: pytest.MonkeyPatch, effective_settings: Any
) -> None:
    """A new backend needs no edit in the page: its own status is mapped through."""

    class Custom:
        @classmethod
        def runtime_status(cls, settings: Any, cached: Any) -> RerankerRuntimeStatus:
            return RerankerRuntimeStatus("missing", "Own reason.", "own-fix")

    monkeypatch.setattr("omrs.core.retrieval.backend.resolve_reranker_backend", lambda _b: Custom)

    item = rc._reranker_item(effective_settings())

    assert (item.status, item.reason, item.fix) == ("missing", "Own reason.", "own-fix")


def test_every_registered_reranker_backend_reports_a_status() -> None:
    for name in ("reranker_onnx", "reranker_torch", "reranker_llamacpp"):
        assert callable(getattr(retrieval_registry.get(name), "runtime_status", None))
