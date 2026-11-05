"""A read whose router failed stores the identity with ``runnable: false``.

Review finding 4 of document-reading-routers (design D9). The index identity
is computed before the read. When the router server goes down between the
identity step and the read, the read stamps ``router_status`` with a reason
and its pages stay unjudged. The source must then be stored under the
identity with ``runnable: false``, so the next explicit ingest, with the
router able to run, reads it again. Every decision request goes to an
``httpx.MockTransport``; the reader and the embedder are fakes.
"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from llama_index.core.schema import TextNode
from tests.fixtures.pipeline_parity.ingestion.snapshot import collect_rows, pin_detection

from omrs import compose_decision
from omrs.config.settings_maps import DecisionModelEntry, DocumentRouterEntry
from omrs.core.ingestion import graph_adapters, router_identity
from omrs.core.ingestion.graph_adapters_values import SourceWork
from omrs.core.ingestion.source_state import build_source_version
from omrs.core.ingestion.sources import SourceUnit, build_ingestion_context, prepare_source
from omrs.integrations.ocr_worker import routes as routes_module

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "smoke_text.pdf"
LOCAL = "http://127.0.0.1:18937"


@pytest.fixture(autouse=True)
def _clean():
    compose_decision.reset_decision_checks()
    routes_module.install_judge_factory(None)
    yield
    routes_module.install_judge_factory(None)
    compose_decision.reset_decision_checks()


class _Server:
    """A System One server that answers while ``up`` is true."""

    def __init__(self) -> None:
        self.up = True

    def handler(self, request: httpx.Request) -> httpx.Response:
        if not self.up:
            raise httpx.ConnectError("refused", request=request)
        reply = {"model": "Clef-Flash-Q8_0.gguf", "answers": {"fidelity": {"noul": 0.9}}}
        return httpx.Response(200, json=reply)


@pytest.fixture
def server() -> _Server:
    return _Server()


@pytest.fixture
def pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    pin_detection(monkeypatch)
    root = tmp_path / "pdfs"
    root.mkdir()
    shutil.copy(FIXTURE, root / "smoke_text.pdf")
    return root / "smoke_text.pdf"


def _settings(effective_settings: Any, **overrides: Any) -> Any:
    values = {
        "pdf_reader": "pdf_inspector",
        "ocr_fallback_enabled": True,
        "document_router": "r",
        "decision_models": {
            "m": DecisionModelEntry(kind="llamacpp", address=LOCAL, model="clef-flash")
        },
        "document_routers": {
            "r": DocumentRouterEntry(model="m", question="Is the text right?", threshold=0.172)
        },
        **overrides,
    }
    return effective_settings(**values)


def _install(server: _Server) -> None:
    """Install a judge factory whose judges send to *server* and never keep a check."""

    def factory(settings: Any) -> Any:
        compose_decision.reset_decision_checks()
        transport = httpx.MockTransport(server.handler)
        return compose_decision.build_page_judge(settings, transport=transport)

    routes_module.install_judge_factory(factory)


def _identity(settings: Any, pdf: Path) -> Any:
    context = build_ingestion_context(settings)
    return asyncio.run(prepare_source(pdf, content_type=None, context=context))


def _nodes(status: str | None) -> list[TextNode]:
    metadata = {} if status is None else {"router_status": status}
    return [TextNode(text="page text", metadata=metadata)]


# ── The settle step ──────────────────────────────────────────────────────


def test_a_failed_router_read_takes_the_runnable_false_identity(
    effective_settings: Any, server: _Server, pdf: Path
) -> None:
    settings = _settings(effective_settings)
    _install(server)
    ready = _identity(settings, pdf)
    server.up = False
    down = _identity(settings, pdf)
    assert ready.index_identity != down.index_identity

    settled = router_identity.settle_router_identity(ready, _nodes("unreachable"))

    assert settled.index_identity == down.index_identity
    assert settled.source_version == build_source_version(ready.content_hash, down.index_identity)
    assert settled.source_version == down.source_version


@pytest.mark.parametrize("status", ["ok", None])
def test_an_ok_or_unstamped_read_keeps_the_identity(
    effective_settings: Any, server: _Server, pdf: Path, status: str | None
) -> None:
    _install(server)
    ready = _identity(_settings(effective_settings), pdf)

    assert router_identity.settle_router_identity(ready, _nodes(status)) == ready


def test_a_read_with_no_router_keeps_the_identity(effective_settings: Any, pdf: Path) -> None:
    identity = _identity(_settings(effective_settings, document_router=""), pdf)

    assert identity.unrouted_identity is None
    assert router_identity.settle_router_identity(identity, _nodes("unreachable")) == identity


def test_an_identity_already_not_runnable_has_no_second_digest(
    effective_settings: Any, server: _Server, pdf: Path
) -> None:
    server.up = False
    _install(server)

    assert _identity(_settings(effective_settings), pdf).unrouted_identity is None


# ── The standard ingest path ─────────────────────────────────────────────


def test_ingest_stores_the_runnable_false_identity_and_reads_the_source_again(
    effective_settings: Any, server: _Server, pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs.core.ingestion import ingest_path_async
    from omrs.core.ingestion.chunker import _ChunkResult
    from omrs.core.vectordb import get_default_store

    settings = _settings(effective_settings)
    _install(server)
    stamped = ["unreachable"]

    async def read(file_path: Path, **kwargs: Any) -> Any:
        return _ChunkResult(_nodes(stamped[0]), metadata_degraded=False)

    monkeypatch.setattr("omrs.core.ingestion.pipeline.read_and_chunk_file_async", read)
    store = get_default_store()

    def ingest() -> list[str]:
        result = asyncio.run(
            ingest_path_async(
                str(pdf.parent), collection_name="router_failed", effective_settings=settings
            )
        )
        return [detail["status"] for detail in result["file_details"]]

    assert ingest() == ["indexed"]
    server.up = False
    down = _identity(settings, pdf)
    server.up = True
    rows = collect_rows(store, "router_failed", pdf.parent)
    assert {row["metadata"]["source_index_identity"] for row in rows} == {down.index_identity}

    stamped[0] = "ok"
    assert ingest() == ["indexed"], "the next ingest did not read the source again"
    assert ingest() == ["skipped_unchanged"]


# ── The graph ingest path ────────────────────────────────────────────────


def test_the_embed_step_stamps_the_runnable_false_identity(
    effective_settings: Any, server: _Server, pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(effective_settings)
    _install(server)
    ready = _identity(settings, pdf)
    server.up = False
    down = _identity(settings, pdf)
    seen: dict[str, Any] = {}

    def prepare(nodes: list, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return SimpleNamespace(chunk_count=len(nodes))

    monkeypatch.setattr(graph_adapters, "prepare_source_embeddings", prepare)
    store = SimpleNamespace(check_embedding_identity=lambda collection, identity: None)
    resources = {"store": store, "embedder": object()}
    context = SimpleNamespace(
        settings=settings,
        node_id="embed",
        resources=resources,
        resource=resources.get,
        progress=lambda *args: None,
    )
    unit = SourceUnit(0, pdf, pdf.name, None)
    work = SourceWork(unit, "c", identity=ready, nodes=_nodes("unreachable"))

    out = asyncio.run(graph_adapters.embed_adapter(context, {"chunks": work}, None))

    assert seen["index_identity"] == down.index_identity
    assert seen["source_version"] == down.source_version
    assert out.values["chunks"].identity.source_version == down.source_version


# ── The router check never blocks the event loop (CodeRabbit, PR 169) ────


def test_a_slow_router_check_does_not_block_the_event_loop(
    effective_settings: Any, pdf: Path
) -> None:
    import threading

    release = threading.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        release.wait(10)
        reply = {"model": "Clef-Flash-Q8_0.gguf", "answers": {"fidelity": {"noul": 0.9}}}
        return httpx.Response(200, json=reply)

    def factory(settings: Any) -> Any:
        transport = httpx.MockTransport(handler)
        return compose_decision.build_page_judge(settings, transport=transport)

    routes_module.install_judge_factory(factory)
    context = build_ingestion_context(_settings(effective_settings))

    async def run() -> bool:
        task = asyncio.create_task(prepare_source(pdf, content_type=None, context=context))
        await asyncio.sleep(0.2)  # a blocked loop would not come back here first
        loop_ran = not task.done()
        release.set()
        await task
        return loop_ran

    assert asyncio.run(run()) is True
