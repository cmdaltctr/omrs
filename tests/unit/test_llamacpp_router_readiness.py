"""A model is made ready before its request is timed (task 4.2; design D8).

Before the first request to model X in a lease, OMRS reads ``GET /v1/models``,
sends ``POST /models/load`` when X is not loaded and polls until ``loaded`` or
``failed``, up to ``MODEL_LOAD_TIMEOUT_SECONDS = 300``. The request's own
timeout starts after the load ends. A failed load gives ``model-load-failed``
for X only.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from tests.unit.test_llamacpp_router_worker import (
    CHAT,
    CLEF,
    EMBED,
    RouterRig,
    as_entries,
    rig_fixture,
)

from omrs.integrations.llamacpp_runtime import process, readiness
from omrs.integrations.llamacpp_runtime.model_reasons import ModelUnavailable
from omrs.integrations.llamacpp_runtime.router_lease import open_router

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file locks")

LOAD_DELAY = 1.5


@pytest.fixture
def rig(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[RouterRig]:
    yield from rig_fixture(tmp_path, monkeypatch)


def _status(url: str, model: str) -> str:
    items = httpx.get(f"{url}/v1/models", timeout=10).json()["data"]
    return next(i["status"]["value"] for i in items if i["id"] == model)


def test_load_timeout_is_a_fixed_constant() -> None:
    assert readiness.MODEL_LOAD_TIMEOUT_SECONDS == 300


def test_router_start_loads_no_model(rig: RouterRig) -> None:
    """Spec scenario "Healthy start": every listed model is unloaded."""
    url = open_router(rig.manager(), rig.spec(), as_entries(rig.entries())).join()
    assert {_status(url, m) for m in (EMBED, CHAT, CLEF)} == {"unloaded"}


def test_slow_load_does_not_eat_the_request_timeout(rig: RouterRig) -> None:
    """Spec scenario "Slow load does not eat the decision timeout"."""
    rig.set_env(FAKE_LLAMA_LOAD_DELAY=str(LOAD_DELAY))
    router = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    began = time.monotonic()

    def send(url: str) -> httpx.Response:
        assert _status(url, CLEF) == "loaded"  # the load ended before the request
        return httpx.post(f"{url}/v1/systemone", json={"model": CLEF}, timeout=0.5)

    reply = router.request_model(CLEF, send)

    assert reply.status_code == 200
    assert time.monotonic() - began >= LOAD_DELAY


def test_ready_once_per_lease(rig: RouterRig, monkeypatch: pytest.MonkeyPatch) -> None:
    router = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    calls: list[str] = []
    real = readiness.ensure_loaded

    def counting(url: str, model: str) -> None:
        calls.append(model)
        real(url, model)

    monkeypatch.setattr(readiness, "ensure_loaded", counting)
    for _ in range(3):
        with router.model_session(CHAT):
            pass
    assert calls == [CHAT]


def test_load_failure_isolated(rig: RouterRig, monkeypatch: pytest.MonkeyPatch) -> None:
    """Spec scenario "Load failure isolated"; the failure shows at once, not after the wait."""
    monkeypatch.setattr(readiness, "MODEL_LOAD_TIMEOUT_SECONDS", 6)
    rig.set_env(FAKE_LLAMA_LOAD_FAIL=CLEF)
    router = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    router.join()
    began = time.monotonic()
    with pytest.raises(ModelUnavailable) as caught:
        with router.model_session(CLEF):
            pass
    assert (caught.value.model, caught.value.reason) == (CLEF, "model-load-failed")
    assert time.monotonic() - began < 3  # the router reports b11941's ``failed: true`` at once
    with router.model_session(EMBED) as url:
        reply = httpx.post(f"{url}/v1/embeddings", json={"model": EMBED, "input": "x"})
    assert reply.status_code == 200


def test_load_that_never_ends_fails_after_the_wait(
    rig: RouterRig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(readiness, "MODEL_LOAD_TIMEOUT_SECONDS", 0.5)
    rig.set_env(FAKE_LLAMA_LOAD_DELAY="5")
    router = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    with pytest.raises(ModelUnavailable) as caught:
        router.ensure_ready(CHAT)
    assert caught.value.reason == "model-load-failed"


def test_unlisted_model_refused_before_any_contact(rig: RouterRig) -> None:
    router = open_router(rig.manager(), rig.spec(), as_entries(rig.entries()))
    with pytest.raises(ModelUnavailable) as caught:
        with router.model_session("no-such/model:Q8_0"):
            pass
    assert caught.value.reason == "model-not-listed"
    assert rig.starts() == 0


def test_changed_file_refused_and_others_serve(rig: RouterRig) -> None:
    """Spec scenario "Changed file isolated" through the router."""
    entries = rig.entries()
    entries[1]["sha256"] = "0" * 64
    router = open_router(rig.manager(), rig.spec(), as_entries(entries))
    with pytest.raises(ModelUnavailable) as caught:
        with router.model_session(CHAT):
            pass
    assert caught.value.reason == "file-changed"
    with router.model_session(EMBED) as url:
        assert httpx.post(f"{url}/v1/embeddings", json={"model": EMBED}).status_code == 200


def test_external_router_checks_no_name_and_loads_nothing(rig: RouterRig) -> None:
    from omrs.integrations.llamacpp_runtime.router_spec import external_router_spec

    spec = external_router_spec("http://127.0.0.1:9/v1")
    router = open_router(rig.manager(), spec, as_entries(rig.entries()))
    with router.model_session("any/model:Q8_0") as url:
        assert url == "http://127.0.0.1:9/v1"
    assert rig.starts() == 0


def _stub_router(monkeypatch: pytest.MonkeyPatch, statuses: list[dict[str, object]]) -> list[str]:
    """Answer each status read with the next of *statuses* (the last repeats); log load posts."""
    posts: list[str] = []
    reads = iter(statuses)
    last: dict[str, object] = {}

    def listing(_url: str) -> dict[str, dict[str, object]]:
        nonlocal last
        last = next(reads, last)
        return {CLEF: last}

    monkeypatch.setattr(readiness, "router_models", listing)
    monkeypatch.setattr(readiness, "_post_load", lambda _url, model: posts.append(model) or 200)
    monkeypatch.setattr(readiness, "LOAD_POLL_SECONDS", 0.01)
    monkeypatch.setattr(readiness, "MODEL_LOAD_TIMEOUT_SECONDS", 2)
    return posts


def test_a_failed_flag_after_the_load_was_asked_is_refused_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """b11941 reports a failed load as ``unloaded`` with ``failed: true``, never ``failed``."""
    failed = {"value": "unloaded", "failed": True, "exit_code": 1}
    posts = _stub_router(monkeypatch, [{"value": "unloaded"}, failed])
    began = time.monotonic()

    with pytest.raises(ModelUnavailable) as caught:
        readiness.ensure_loaded("http://127.0.0.1:1", CLEF)

    assert (caught.value.model, caught.value.reason) == (CLEF, "model-load-failed")
    assert posts == [CLEF]
    assert time.monotonic() - began < 1.0


def test_a_failure_left_from_an_earlier_load_does_not_block_a_new_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The flag stays on the router until the next load; only a read after the ask counts."""
    old = {"value": "unloaded", "failed": True, "exit_code": 1}
    posts = _stub_router(monkeypatch, [old, {"value": "loading"}, {"value": "loaded"}])

    readiness.ensure_loaded("http://127.0.0.1:1", CLEF)

    assert posts == [CLEF]


def test_a_reply_cut_after_its_headers_is_unreachable() -> None:
    """Design D8: a body that never arrives reads as "unreachable", not as a crash."""
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)

        def answer_headers_only() -> None:
            conn, _ = server.accept()
            with conn:
                conn.recv(4096)
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 1898\r\n\r\n")

        threading.Thread(target=answer_headers_only, daemon=True).start()
        url = f"http://127.0.0.1:{server.getsockname()[1]}/v1/models"
        assert process.http_get_json(url, timeout=5.0) == (0, {})
