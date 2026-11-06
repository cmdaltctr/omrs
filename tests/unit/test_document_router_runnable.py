"""The router entry of the index identity records whether the router can run.

Review finding A of document-reading-routers (design D9). The ``parser`` entry
holds ``runnable``: true only when the OCR routes' judge hook gives a page judge
for the settings, its status is ``None``, an image router has a renderer, and
the PDF path wraps the reader in ``OcrRoutedPdfInspector``. A router that
cannot run therefore leaves the source stale, so a later run that can judge the
pages reads the source again. Every decision request goes to an
``httpx.MockTransport``.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from tests.unit.test_pdf_reader_identity import CODE_DEFAULT_PDF

from omrs import compose_decision
from omrs.config.settings_maps import DecisionModelEntry, DocumentRouterEntry
from omrs.core.ingestion import source_state
from omrs.core.ingestion.ocr_identity import document_router_payload
from omrs.core.ingestion.reader_identity import pdf_parser_payload
from omrs.integrations.ocr_worker import routes as routes_module
from omrs.integrations.pdf import page_images, page_routing

LOCAL = "http://127.0.0.1:18932"
HOSTED = "https://api.example.invalid"


@pytest.fixture(autouse=True)
def _unresolved_local_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hash with the local OCR model unresolved: the real probe depends on the host runtime."""
    page_routing.reset_local_model_resolution()
    monkeypatch.setattr(
        page_routing, "_probe_local_model_identity", lambda settings, backend="x": None
    )


@pytest.fixture(autouse=True)
def _clean():
    compose_decision.reset_decision_checks()
    routes_module.install_judge_factory(None)
    yield
    routes_module.install_judge_factory(None)
    compose_decision.reset_decision_checks()


class _Server:
    """A System One server that is down until ``up`` is set."""

    def __init__(self) -> None:
        self.up = False
        self.calls = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if not self.up:
            raise httpx.ConnectError("refused", request=request)
        reply = {"model": "Clef-Flash-Q8_0.gguf", "answers": {"fidelity": {"noul": 0.9}}}
        return httpx.Response(200, json=reply)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def _settings(effective_settings, *, address: str = LOCAL, **overrides: Any):
    values = {
        "pdf_reader": "pdf_inspector",
        "ocr_fallback_enabled": True,
        "document_router": "r",
        "decision_models": {
            "m": DecisionModelEntry(kind="llamacpp", address=address, model="clef-flash")
        },
        "document_routers": {
            "r": DocumentRouterEntry(model="m", question="Is the text right?", threshold=0.172)
        },
        **overrides,
    }
    return effective_settings(**values)


def _install(settings, server: _Server) -> None:
    judge = compose_decision.build_page_judge(settings, transport=server.transport)
    routes_module.install_judge_factory(lambda _settings: judge)


def _runnable(settings) -> bool:
    return document_router_payload(settings)["document_router"]["runnable"]


def _digest(settings) -> str:
    return source_state.build_index_identity(
        settings,
        content_type="application/pdf",
        chunk_size=512,
        chunk_overlap=100,
        pdf_reader_revision=2,
    )


def test_a_server_that_starts_later_turns_runnable_on_and_moves_the_digest(
    effective_settings, monkeypatch
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(compose_decision, "monotonic", lambda: clock[0])
    server = _Server()
    settings = _settings(effective_settings)
    _install(settings, server)

    down = _digest(settings)
    assert _runnable(settings) is False
    server.up = True
    clock[0] += compose_decision.FAILED_CHECK_SECONDS - 1
    assert _runnable(settings) is False  # the failed check is kept for a short time
    clock[0] += 2

    assert _runnable(settings) is True
    assert _digest(settings) != down


def test_a_ready_judge_is_runnable(effective_settings) -> None:
    server = _Server()
    server.up = True
    settings = _settings(effective_settings)
    _install(settings, server)

    assert _runnable(settings) is True


def test_a_hosted_router_without_the_opt_in_is_not_runnable(effective_settings) -> None:
    server = _Server()
    server.up = True
    settings = _settings(effective_settings, address=HOSTED)
    _install(settings, server)

    assert _runnable(settings) is False
    assert server.calls == 0


def test_no_judge_factory_means_not_runnable(effective_settings) -> None:
    assert _runnable(_settings(effective_settings)) is False


@pytest.mark.parametrize("overrides", [{"pdf_reader": "pypdf"}, {"ocr_fallback_enabled": False}])
def test_a_pdf_path_without_the_routing_seam_is_not_runnable(
    effective_settings, overrides: dict[str, Any]
) -> None:
    server = _Server()
    server.up = True
    settings = _settings(effective_settings, **overrides)
    _install(settings, server)

    assert _runnable(settings) is False


def test_an_image_router_without_a_renderer_is_not_runnable(
    effective_settings, monkeypatch
) -> None:
    server = _Server()
    server.up = True
    settings = _settings(
        effective_settings,
        decision_models={
            "m": DecisionModelEntry(kind="llamacpp", address=LOCAL, model="clef", images=True)
        },
        document_routers={
            "r": DocumentRouterEntry(model="m", question="Q?", threshold=0.172, images=True)
        },
    )
    monkeypatch.setattr(compose_decision.checks, "run_smoke_test", lambda ask: None)
    _install(settings, server)
    monkeypatch.setattr(page_images, "available", lambda: False)

    assert _runnable(settings) is False
    monkeypatch.setattr(page_images, "available", lambda: True)
    assert _runnable(settings) is True


def test_with_no_router_the_entry_is_absent_and_the_digest_holds(effective_settings) -> None:
    server = _Server()
    server.up = True
    _install(_settings(effective_settings), server)
    settings = _settings(effective_settings, document_router="")

    assert "document_router" not in pdf_parser_payload(settings)
    assert document_router_payload(settings) == {}
    base = effective_settings()
    assert _digest(base) == _digest(base.model_copy(update={"document_router": "none"}))


def test_the_pinned_default_digest_holds_with_a_factory_installed() -> None:
    from tests.unit.test_document_router_identity import _base
    from tests.unit.test_document_router_identity import _digest as pinned_digest

    routes_module.install_judge_factory(lambda _settings: None)

    assert pinned_digest(_base()) == CODE_DEFAULT_PDF
