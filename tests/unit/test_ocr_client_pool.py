"""The Engine-owned OCR client pool (task 5.1, design D5).

Change integrations-show-runtime-components. The pool keeps one lazy
worker client per resolved route command. Every node and the host routes
share it. One pool-wide lock makes sure that at most one worker parses at a
time, so two engines never hold peak memory together.

Route commands point at fake engine folders, the probe is a fake, and the
worker subprocess is an in-process double that records overlap.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_engine_pipelines_support import build_engine
from tests.unit.test_ingestion_graph_adapters_support import offline_settings

from omrs.integrations.ocr_worker import managed
from omrs.integrations.ocr_worker.fingerprint import OcrWorkerFingerprint
from omrs.integrations.ocr_worker.pool import OcrClientPool
from omrs.integrations.ocr_worker.protocol import make_success

_AVAILABLE = OcrWorkerFingerprint(
    available=True,
    protocol_version="1.1",
    packages=(),
    pipeline_identity="p",
    pipeline_revision="1",
    model_identity="m",
    model_revision="1",
    output_schema_id="s",
    output_schema_version="1",
    backend_id="fake",
)


class _FakeWorker:
    """In-process stand-in for the worker subprocess client."""

    started: list[_FakeWorker] = []
    active = 0
    most_active = 0
    guard = threading.Lock()

    def __init__(self, command: list[str], **kwargs: Any) -> None:
        self.command = command
        self.closed = False
        _FakeWorker.started.append(self)

    @property
    def is_started(self) -> bool:
        return not self.closed

    def parse(self, pdf_path: str, *, pages: Any = None, timeout: Any = None) -> Any:
        with _FakeWorker.guard:
            _FakeWorker.active += 1
            _FakeWorker.most_active = max(_FakeWorker.most_active, _FakeWorker.active)
        time.sleep(0.05)
        with _FakeWorker.guard:
            _FakeWorker.active -= 1
        return make_success("r", "text", ocr_backend="fake", page_count=1)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def workers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Return a workers folder with two provisioned engines and a fake worker."""
    root = tmp_path / "workers"
    for name in ("dots-mocr", "paddleocr-vl"):
        python = root / "engines" / name / ".venv" / "bin" / "python"
        python.parent.mkdir(parents=True)
        python.write_text("")
    _FakeWorker.started, _FakeWorker.active, _FakeWorker.most_active = [], 0, 0
    monkeypatch.setattr(managed, "OcrWorkerClient", _FakeWorker)
    return root


def _settings(effective_settings: Any, workers: Path, **overrides: Any) -> Any:
    ocr = {"ocr_fallback_enabled": True, "ocr_engine_primary": "dots-mocr", **overrides}
    return offline_settings(effective_settings, ocr_workers_dir=str(workers)).model_copy(update=ocr)


def _pool(probed: list[list[str]] | None = None) -> OcrClientPool:
    def probe(command: list[str]) -> OcrWorkerFingerprint:
        if probed is not None:
            probed.append(command)
        return _AVAILABLE

    return OcrClientPool(probe=probe)


def test_two_nodes_with_one_engine_share_one_client(effective_settings: Any, workers: Path) -> None:
    """Two node settings that name ``paddleocr-vl`` get the same client and one worker."""
    pool = _pool()
    first = pool.routes(_settings(effective_settings, workers, ocr_engine_primary="paddleocr-vl"))
    second = pool.routes(
        _settings(
            effective_settings,
            workers,
            ocr_engine_primary="paddleocr-vl",
            ocr_fallback_page_fraction=0.9,
        )
    )
    assert first.primary is second.primary
    assert _FakeWorker.started == [], "a worker starts only on its first dispatch"
    first.primary.parse("a.pdf")
    second.primary.parse("b.pdf")
    assert len(_FakeWorker.started) == 1
    pool.close()
    assert _FakeWorker.started[0].closed


def test_a_fallback_route_shares_the_client_of_the_same_engine(
    effective_settings: Any, workers: Path
) -> None:
    """A node's fallback ``dots-mocr`` is the host's primary ``dots-mocr`` client."""
    pool = _pool()
    host = pool.routes(_settings(effective_settings, workers))
    node = pool.routes(
        _settings(
            effective_settings,
            workers,
            ocr_engine_primary="paddleocr-vl",
            ocr_engine_fallback="dots-mocr",
        )
    )
    assert node.fallback is host.primary
    assert node.primary is not host.primary


def test_each_route_command_is_probed_once(effective_settings: Any, workers: Path) -> None:
    """The pool probes a route command when it builds its client, then reuses it."""
    probed: list[list[str]] = []
    pool = _pool(probed)
    for _ in range(3):
        pool.routes(_settings(effective_settings, workers, ocr_engine_fallback="paddleocr-vl"))
    assert sorted(Path(c[0]).parts[-4] for c in probed) == ["dots-mocr", "paddleocr-vl"]


def test_routes_with_ocr_off_hold_no_client(effective_settings: Any, workers: Path) -> None:
    """A node that turns OCR off gets no client, so it cannot poison the shared one."""
    probed: list[list[str]] = []
    pool = _pool(probed)
    off = pool.routes(_settings(effective_settings, workers, ocr_fallback_enabled=False))
    assert off.primary is None and off.fallback is None
    assert not off.fingerprint.available
    on = pool.routes(_settings(effective_settings, workers))
    assert on.fingerprint.available and probed


def test_two_engines_never_parse_at_the_same_time(effective_settings: Any, workers: Path) -> None:
    """``dots-mocr`` and ``paddleocr-vl`` dispatched from two threads never overlap."""
    pool = _pool()
    clients = [
        pool.routes(_settings(effective_settings, workers, ocr_engine_primary=name)).primary
        for name in ("dots-mocr", "paddleocr-vl")
    ]
    assert clients[0] is not clients[1]
    threads = [
        threading.Thread(target=client.parse, args=(f"{i}.pdf",))
        for i, client in enumerate(clients * 2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(_FakeWorker.started) == 2
    assert _FakeWorker.most_active == 1


# ── Engine wiring ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_host_routes_and_an_inheriting_node_share_one_client(
    monkeypatch: pytest.MonkeyPatch, effective_settings: Any, workers: Path, tmp_path: Path
) -> None:
    """``Engine.ingest`` and a graph node that inherits the engine use one client."""
    from omrs import capabilities
    from omrs.compose_pipeline_runs import plan_run
    from omrs.core.ingestion import pipeline
    from omrs.core.ingestion.graph_adapters import canonical_ingestion_definition

    seen: dict[str, Any] = {}

    async def _ingest(path: str, **kwargs: Any) -> dict:
        seen.update(kwargs)
        return {}

    monkeypatch.setattr(capabilities, "probe_ocr_worker", lambda command: _AVAILABLE)
    monkeypatch.setattr(pipeline, "ingest_path_async", _ingest)
    settings = _settings(effective_settings, workers)
    engine = build_engine(settings)
    await engine.ingest(str(tmp_path), collection_name="documents")
    host_routes = seen["ocr_client"]

    snapshot = engine.validate_pipeline(
        canonical_ingestion_definition("documents"), inputs={"path": str(tmp_path)}
    )
    graph_host = engine._graph_host(None)
    plan = plan_run(snapshot, engine._pipelines.catalogue(), graph_host)
    ocr = plan.resources.get("ocr", graph_host.resources["ocr"])
    node_routes = ocr.routes(snapshot.node("read").settings)
    assert host_routes.primary is not None
    assert node_routes.primary is host_routes.primary
    node_routes.primary.parse("a.pdf")
    engine.close()
    assert [w.closed for w in _FakeWorker.started] == [True]
