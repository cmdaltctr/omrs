"""Fallback rules of a declared llama.cpp runtime (change managed-llamacpp-runtimes, 6.3).

Two test engines declare a fake ``llama-server`` each, so every test can count
the requests that reached each runtime. The one exception to "a failure after
dispatch is not retried" is the operator stop, and it happens once.
"""

from __future__ import annotations

import os
import re
import signal
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.llamacpp.harness import pid_alive, wait_until
from tests.fixtures.ocr_worker.runtime_engine import OcrRuntimeHarness, TestEngine

from omrs.integrations.llamacpp_runtime import process
from omrs.integrations.ocr_worker import OcrWorkerError
from omrs.integrations.ocr_worker.routes import backend_id_of

DELAY = {"FAKE_LLAMA_REQUEST_DELAY": 6}


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[OcrRuntimeHarness]:
    for name in ("OMRS_OCR_MODEL_CACHE", "OMRS_OCR_RUNTIME_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(process, "HEALTH_POLL_SECONDS", 0.05)
    env = OcrRuntimeHarness(tmp_path)
    try:
        yield env
    finally:
        env.cleanup()


class _Parse:
    """One parse on a thread, so the test can act while the request runs."""

    def __init__(self, client: Any, pdf: str) -> None:
        self.result: Any = None
        self.error: BaseException | None = None
        self.thread = threading.Thread(target=self._run, args=(client, pdf), daemon=True)
        self.thread.start()

    def _run(self, client: Any, pdf: str) -> None:
        try:
            self.result = client.parse(pdf, timeout=30)
        except BaseException as exc:  # noqa: BLE001 - the test inspects it
            self.error = exc

    def finish(self) -> None:
        self.thread.join(timeout=60)
        assert not self.thread.is_alive(), "the parse did not end"


def _pair(
    harness: OcrRuntimeHarness, effective_settings: Any, **primary: Any
) -> tuple[Any, TestEngine, TestEngine]:
    first = harness.engine("primary", **primary)
    second = harness.engine("fallback")
    routes = harness.pool().routes(harness.settings(effective_settings, "primary", "fallback"))
    return routes, first, second


def _in_flight(engine: TestEngine, pdf: str) -> bool:
    return engine.requests() == [pdf]


# ── Before dispatch ───────────────────────────────────────────────────────────


def test_a_changed_model_file_makes_the_primary_unavailable_and_the_fallback_parses(
    harness: OcrRuntimeHarness, effective_settings: Any
) -> None:
    routes, primary, fallback = _pair(harness, effective_settings)
    primary.model.write_bytes(b"GGUF changed after the manifest was written")
    pdf = harness.pdf("a.pdf")

    client = routes.select()
    result = client.parse(pdf, timeout=20)

    assert f"url={routes.fallback.lease.base_url}\n" in result.markdown
    assert backend_id_of(client) == "fallback"
    assert fallback.requests() == [pdf]
    assert primary.requests() == [] and primary.fake.starts() == []


# ── Operator stop ─────────────────────────────────────────────────────────────


def test_an_operator_stop_sends_the_request_once_to_the_fallback_and_later_ones_too(
    harness: OcrRuntimeHarness, effective_settings: Any
) -> None:
    routes, primary, fallback = _pair(harness, effective_settings)
    primary.set_fake(**DELAY)
    first, second = harness.pdf("a.pdf"), harness.pdf("b.pdf")
    running = _Parse(routes.select(), first)
    assert wait_until(lambda: _in_flight(primary, first))

    assert harness.manager.stop(primary.runtime_id) is True
    running.finish()

    assert running.error is None
    assert f"url={routes.fallback.lease.base_url}\n" in running.result.markdown
    assert fallback.requests() == [first], "the fallback got the request once"
    assert primary.requests() == [first]
    client = routes.select()
    later = client.parse(second, timeout=20)
    assert f"url={routes.fallback.lease.base_url}\n" in later.markdown
    assert backend_id_of(client) == "fallback"
    assert primary.requests() == [first], "nothing reached the stopped runtime"
    assert len(primary.fake.starts()) == 1, "the stopped runtime did not start again"


def test_the_retry_after_an_operator_stop_happens_once_only(
    harness: OcrRuntimeHarness, effective_settings: Any
) -> None:
    routes, primary, fallback = _pair(harness, effective_settings)
    primary.set_fake(**DELAY)
    fallback.set_fake(**DELAY)
    pdf = harness.pdf("a.pdf")
    running = _Parse(routes.select(), pdf)
    assert wait_until(lambda: _in_flight(primary, pdf))
    harness.manager.stop(primary.runtime_id)
    assert wait_until(lambda: _in_flight(fallback, pdf))

    harness.manager.stop(fallback.runtime_id)
    running.finish()

    assert isinstance(running.error, OcrWorkerError), "the file got a structured error"
    assert running.error.code == "runtime_stopped"
    assert fallback.requests() == [pdf], "the fallback recorded exactly one request"
    assert primary.requests() == [pdf], "the host did not send the file to the primary again"
    assert len(primary.fake.starts()) == 1


def test_a_fallback_failure_after_the_operator_stop_is_not_retried(
    harness: OcrRuntimeHarness, effective_settings: Any
) -> None:
    first = harness.engine("primary")
    harness.engine("fallback", mode="crash")
    routes = harness.pool().routes(harness.settings(effective_settings, "primary", "fallback"))
    first.set_fake(**DELAY)
    pdf = harness.pdf("a.pdf")
    running = _Parse(routes.select(), pdf)
    assert wait_until(lambda: _in_flight(first, pdf))

    harness.manager.stop(first.runtime_id)
    running.finish()

    assert isinstance(running.error, OcrWorkerError)
    assert running.error.code != "runtime_stopped", "the fallback worker failed on its own"
    assert first.requests() == [pdf], "the primary was not tried again"


# ── After dispatch, no fallback retry ─────────────────────────────────────────


def test_a_worker_crash_after_dispatch_is_a_structured_error_with_no_fallback_retry(
    harness: OcrRuntimeHarness, effective_settings: Any
) -> None:
    routes, primary, fallback = _pair(harness, effective_settings, mode="crash")

    with pytest.raises(OcrWorkerError) as caught:
        routes.select().parse(harness.pdf("a.pdf"), timeout=20)

    assert caught.value.code in {"worker_crashed", "worker_closed_output", "worker_closed_input"}
    assert fallback.requests() == [] and fallback.fake.starts() == []
    assert not routes.fallback.is_started


def test_a_server_crash_after_dispatch_restarts_for_the_next_request_only(
    harness: OcrRuntimeHarness, effective_settings: Any
) -> None:
    routes, primary, fallback = _pair(harness, effective_settings)
    primary.set_fake(FAKE_LLAMA_EXIT_AFTER=1)
    lease = routes.primary.lease
    routes.select().parse(harness.pdf("a.pdf"), timeout=20)
    server_pid = int(primary.fake.starts()[0]["pid"])
    assert wait_until(lambda: not pid_alive(server_pid))
    primary.set_fake()
    old_url = lease.base_url

    with pytest.raises(OcrWorkerError):
        routes.select().parse(harness.pdf("b.pdf"), timeout=20)
    result = routes.select().parse(harness.pdf("c.pdf"), timeout=20)

    assert lease.base_url != old_url and f"url={lease.base_url}\n" in result.markdown
    assert len(primary.fake.starts()) == 2, "exactly one restart"
    assert fallback.requests() == [], "no fallback retry"


# ── Worker kill and close order ───────────────────────────────────────────────


def test_a_killed_worker_leaves_the_runtime_running_until_the_pool_closes(
    harness: OcrRuntimeHarness, effective_settings: Any
) -> None:
    pool = harness.pool()
    primary = harness.engine("primary")
    routes = pool.routes(harness.settings(effective_settings, "primary"))
    first = routes.select().parse(harness.pdf("a.pdf"), timeout=20)
    server_pid = int(primary.fake.starts()[0]["pid"])
    worker_pid = int(re.search(r"pid=(\d+)", first.markdown).group(1))

    os.kill(worker_pid, signal.SIGKILL)

    assert wait_until(lambda: not pid_alive(worker_pid))
    assert pid_alive(server_pid), "the runtime runs while the host holds its lease"
    assert routes.primary.lease.joined
    again = routes.select().parse(harness.pdf("c.pdf"), timeout=20)
    assert "url=http://127.0.0.1:" in again.markdown
    assert re.search(r"pid=(\d+)", again.markdown).group(1) != str(worker_pid), "a new worker"
    assert len(primary.fake.starts()) == 1, "no other model server started"
    assert pid_alive(server_pid)

    pool.close()

    assert wait_until(lambda: not pid_alive(server_pid)), "the last client left, the server stopped"
