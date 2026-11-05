"""The composition root puts the page judge on the OCR routes (document-reading-routers, D12).

``OcrRoutes.judge`` reaches the page rules through ``OcrRoutedPdfInspector``.
``compose_runtimes.install_gates`` (run when the process's Engine is built)
installs ``compose_decision.page_judge_for`` as the judge factory of the OCR
routes. Both builders of routes for ingestion read it:
``capabilities.build_ocr_routes`` (an operation without an Engine) and the
Engine's ``OcrClientPool`` (the host routes and every Read step). With no
router the routes stay as they were, with ``judge=None``.

Every decision request goes to an ``httpx.MockTransport``.
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import httpx
import pytest
from llama_index.core import Document

from omrs import compose_decision, compose_runtimes
from omrs.compose_pipelines import EnginePipelines
from omrs.config.settings_maps import DecisionModelEntry, DocumentRouterEntry
from omrs.integrations.ocr_worker import pool as pool_module
from omrs.integrations.ocr_worker import routes as routes_module
from omrs.integrations.ocr_worker.protocol import make_success
from omrs.integrations.ocr_worker.routes import OcrRoutes, RouteCommand
from omrs.integrations.pdf import ocr_routing
from omrs.integrations.pdf.ocr_routing import OcrRoutedPdfInspector

LOCAL = "http://127.0.0.1:18931"
#: The page text the fake model rejects.
JUNK = "native 3"


@pytest.fixture(autouse=True)
def _installed():
    """Install the process hooks as the process's Engine does; remove them after."""
    compose_decision.reset_decision_checks()
    compose_runtimes.install_gates(None)
    yield
    compose_runtimes.reset()
    compose_decision.reset_decision_checks()


class _Worker:
    """An OCR worker that speaks protocol 1.1 and records each page list."""

    def __init__(self) -> None:
        self.fingerprint = SimpleNamespace(
            available=True, protocol_version="1.1", backend_id="paddleocr_vl"
        )
        self.calls: list[list[int]] = []

    def parse(self, pdf_path: str, *, pages=None, timeout=None):
        self.calls.append(list(pages))
        markdown = [f"WORKER {page}" for page in pages]
        return make_success(
            "req", "\n\n".join(markdown), ocr_backend="x", page_count=len(pages),
            pages_markdown=markdown,
        )  # fmt: skip

    def close(self) -> None:
        """Nothing to close."""


class _Inner:
    def load_data(self, file, *args, **kwargs) -> list:
        metadata = {"pdf_reader": "pdf_inspector", "page_count": 4, "pages_needing_ocr": 0}
        return [Document(text="whole", metadata=metadata)]


class _Server:
    """A System One server that rejects the junk page and passes the probe."""

    def __init__(self) -> None:
        self.texts: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        text = json.loads(request.content)["state"]["text"]
        self.texts.append(text)
        score = 0.05 if text == JUNK else 0.9
        reply = {"model": "Clef-Flash-Q8_0.gguf", "answers": {"fidelity": {"noul": score}}}
        return httpx.Response(200, json=reply)


@pytest.fixture
def server(monkeypatch) -> _Server:
    """Send every request of a compose-built judge to the fake server."""
    fake = _Server()
    real = httpx.Client

    def client(*args, transport=None, **kwargs):
        return real(*args, transport=httpx.MockTransport(fake.handler), **kwargs)

    monkeypatch.setattr(compose_decision.httpx, "Client", client)
    return fake


@pytest.fixture
def scan(monkeypatch) -> None:
    """Four pages with text; none is flagged."""
    pages = [
        SimpleNamespace(page=n - 1, markdown=f"native {n}", needs_ocr=False, ocr_reason=None)
        for n in range(1, 5)
    ]
    stub = SimpleNamespace(extract_pages_markdown=lambda path: SimpleNamespace(pages=pages))
    monkeypatch.setitem(sys.modules, "pdf_inspector", stub)
    monkeypatch.setattr(
        "omrs.integrations.pdf.blank_pages.find_blank_pages", lambda file, pages: frozenset()
    )
    monkeypatch.setattr(ocr_routing, "local_ocr", _no_local_ocr)


def _no_local_ocr(file, pages, **kwargs):
    raise AssertionError("no page goes to the local tier")


def _settings(effective_settings, *, router: str = "r"):
    return effective_settings(
        ocr_fallback_enabled=True,
        ocr_maths_routing_enabled=False,
        ocr_non_latin_routing="off",
        document_router=router,
        decision_models={
            "m": DecisionModelEntry(kind="llamacpp", address=LOCAL, model="clef-flash")
        },
        document_routers={
            "r": DocumentRouterEntry(model="m", question="Is the text right?", threshold=0.172)
        },
    )


def _route(name, settings, manager=None) -> RouteCommand:
    return RouteCommand(("w",), None)


@pytest.fixture
def composed(monkeypatch) -> _Worker:
    """Make ``build_route_clients`` build one fake worker for every engine."""
    worker = _Worker()
    monkeypatch.setattr(routes_module, "resolve_route_command", _route)
    monkeypatch.setattr(routes_module, "_client", lambda route, settings, **kw: worker)
    monkeypatch.setattr("omrs.compose_runtime_manager.runtime_manager", lambda: None)
    return worker


@pytest.fixture
def pooled(monkeypatch) -> _Worker:
    """Make the Engine's OCR pool hand out one fake worker for every engine."""
    worker = _Worker()
    monkeypatch.setattr(pool_module, "resolve_route_command", _route)
    monkeypatch.setattr(pool_module.OcrClientPool, "_client", lambda self, route, s: worker)
    monkeypatch.setattr("omrs.compose_runtime_manager.runtime_manager", lambda: None)
    return worker


def test_build_ocr_routes_carries_the_judge_of_the_selected_router(effective_settings, composed):
    from omrs.capabilities import build_ocr_routes

    routes = build_ocr_routes(_settings(effective_settings))

    assert routes.routes == (composed, composed)
    assert routes.judge is not None
    assert routes.judge.name == "r"


def test_with_no_router_build_ocr_routes_returns_the_routes_unchanged(effective_settings, composed):
    from omrs.capabilities import build_ocr_routes

    routes = build_ocr_routes(_settings(effective_settings, router=""))

    assert routes == OcrRoutes(routes=(composed, composed))
    assert routes.judge is None


def test_the_engine_pool_routes_carry_the_judge_of_the_settings(effective_settings, pooled):
    pool = EnginePipelines().ocr_pool()

    with_router = pool.routes(_settings(effective_settings))
    without = pool.routes(_settings(effective_settings, router="none"))

    assert with_router.judge is not None and with_router.judge.name == "r"
    assert without == OcrRoutes(routes=(pooled, pooled))
    assert without.judge is None


def test_one_judge_object_serves_repeated_routes_for_the_same_settings(effective_settings, pooled):
    pool = EnginePipelines().ocr_pool()
    settings = _settings(effective_settings)

    first = pool.routes(settings).judge

    assert first is not None
    assert pool.routes(settings).judge is first


@pytest.mark.parametrize("path", ["build_ocr_routes", "engine_pool"])
def test_a_page_the_router_rejects_goes_to_the_page_listed_request(
    effective_settings, server, scan, composed, pooled, path, tmp_path
):
    settings = _settings(effective_settings)
    if path == "build_ocr_routes":
        from omrs.capabilities import build_ocr_routes

        routes, worker = build_ocr_routes(settings), composed
    else:
        routes, worker = EnginePipelines().ocr_pool().routes(settings), pooled

    docs = OcrRoutedPdfInspector(_Inner(), settings=settings, ocr_client=routes).load_data(
        tmp_path / "doc.pdf"
    )

    assert JUNK in server.texts, "the rule asked the decision model about page 3"
    assert worker.calls == [[3]], "only the rejected page goes to the engine"
    assert [doc.text for doc in docs] == ["native 1", "native 2", "WORKER 3", "native 4"]
    metadata = docs[0].metadata
    assert metadata["router_status"] == "ok"
    assert metadata["router_pages_rejected"] == 1
    assert metadata["router_pages_accepted"] == 3


def test_install_gates_installs_the_judge_factory_and_reset_removes_it(effective_settings):
    settings = _settings(effective_settings)
    assert routes_module.page_judge(settings) is not None

    compose_runtimes.reset()

    assert routes_module.page_judge(settings) is None
