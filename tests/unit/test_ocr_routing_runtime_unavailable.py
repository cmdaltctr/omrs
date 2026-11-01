"""A route that is unavailable before dispatch degrades like a missing route.

Change managed-llamacpp-runtimes, design D10: a runtime that cannot start (for
example ``file-changed``) makes the route unavailable before dispatch. With no
fallback behind it, the file keeps its partial text exactly as it does when
``routes.select()`` gives no client. Any other worker error after dispatch
still fails the file.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.ocr_worker.runtime_engine import OcrRuntimeHarness
from tests.unit.test_ocr_route_dispatch import _Client, _Inner, _maths, _metadata, _read, _scan

from omrs.integrations.llamacpp_runtime import process
from omrs.integrations.ocr_worker.client import OcrWorkerError
from omrs.integrations.ocr_worker.routes import OcrRoutes
from omrs.integrations.pdf.ocr_routing import OcrPostDispatchError, OcrRoutedPdfInspector

pytest.importorskip("pdf_inspector", reason="pdf-inspector is a base dependency (ADR-050)")

_UNAVAILABLE = OcrWorkerError("worker_unavailable", "A model file changed: q.gguf.")


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


def _no_route_read(settings: Any, metadata: dict, tmp_path: Path) -> Any:
    return _read(settings, OcrRoutes(_Client("x", available=False), None), metadata, tmp_path)


def test_document_unit_degrades_when_the_only_route_is_unavailable_before_dispatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    _maths(monkeypatch, set())
    settings = effective_settings(ocr_fallback_enabled=True)
    metadata = _metadata(2, pdf_type="scanned")
    route = _Client("dots_mocr", error=_UNAVAILABLE)

    doc = _read(settings, OcrRoutes(route, None), metadata, tmp_path)

    assert doc.text == "partial native text"
    assert doc.metadata == _no_route_read(settings, metadata, tmp_path).metadata
    assert len(route.calls) == 1, "the route was asked once"


def test_document_unit_still_fails_the_file_on_a_worker_error_after_dispatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    _maths(monkeypatch, set())
    settings = effective_settings(ocr_fallback_enabled=True)
    route = _Client("dots_mocr", error=OcrWorkerError("worker_crashed", "exit 9"))

    with pytest.raises(OcrPostDispatchError) as caught:
        _read(settings, OcrRoutes(route, None), _metadata(2, pdf_type="scanned"), tmp_path)

    assert caught.value.code == "worker_crashed"


def test_page_unit_degrades_when_the_only_route_is_unavailable_before_dispatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    _scan(monkeypatch, 3, needs_ocr=set())
    _maths(monkeypatch, {2})
    settings = effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page")
    route = _Client("dots_mocr", error=_UNAVAILABLE)

    doc = _read(settings, OcrRoutes(route, None), _metadata(3), tmp_path)

    expected = _no_route_read(settings, _metadata(3), tmp_path)
    assert doc.text == expected.text
    assert doc.metadata == expected.metadata
    assert len(route.calls) == 1


def test_page_unit_still_fails_the_file_on_a_worker_error_after_dispatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    _scan(monkeypatch, 3, needs_ocr=set())
    _maths(monkeypatch, {2})
    settings = effective_settings(ocr_fallback_enabled=True, ocr_routing_unit="page")
    route = _Client("dots_mocr", error=OcrWorkerError("timeout", "no terminal response"))

    with pytest.raises(OcrPostDispatchError) as caught:
        _read(settings, OcrRoutes(route, None), _metadata(3), tmp_path)

    assert caught.value.code == "timeout"


def test_a_changed_model_file_with_no_fallback_keeps_the_partial_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    effective_settings: Any,
    harness: OcrRuntimeHarness,
) -> None:
    _maths(monkeypatch, set())
    engine = harness.engine("primary")
    engine.model.write_bytes(b"GGUF changed after the manifest was written")
    settings = harness.settings(effective_settings, "primary")
    routes = harness.pool().routes(settings)
    reader = OcrRoutedPdfInspector(
        _Inner(_metadata(2, pdf_type="scanned")), settings=settings, ocr_client=routes
    )

    docs = reader.load_data(tmp_path / "doc.pdf")

    assert docs[0].text == "partial native text"
    assert docs[0].metadata["ocr_required"] is True and docs[0].metadata["ocr_used"] is False
    assert engine.fake.starts() == [] and engine.requests() == []
