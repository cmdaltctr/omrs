"""A non-default local OCR list resolves its identity entry once per operation.

Change local-ocr-backends, follow-up fix. The ``local_ocr_backends`` entry of
the PDF ``parser`` block probes each listed backend's model. A failed probe is
never cached, so a per-source probe would run once per PDF source in one
ingest. The entry resolves once in ``build_ingestion_context``, next to the
default tier's routing payload, and every source of the operation reuses it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from omrs.core import reading_parts
from omrs.core.ingestion.sources import build_ingestion_context, prepare_source
from omrs.core.reading_parts import LocalOcrBackendDescriptor
from omrs.integrations.pdf import page_routing

_FAILING = LocalOcrBackendDescriptor(
    name="fake-fail",
    import_path="tests.fake:BACKEND",
    label="Fake that never resolves",
    help_key="local_ocr_backend.fake-fail",
    producer="fake_fail_ocr",
    min_confidence=0.8,
    calibrated_by="1-fake-experiment",
)
_LISTED = ("pp-ocrv6-small", "fake-fail")


@pytest.fixture(autouse=True)
def fake_table(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        reading_parts, "LOCAL_OCR_BACKENDS", (*reading_parts.LOCAL_OCR_BACKENDS, _FAILING)
    )
    page_routing.reset_local_model_resolution()
    yield
    page_routing.reset_local_model_resolution()


@pytest.fixture
def probes(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Patch the probe the resolver calls (gotcha 8b); record each backend probed."""
    calls: list[str] = []

    def fake_probe(settings: Any, backend: str = "pp-ocrv6-small") -> str | None:
        calls.append(backend)
        return None if backend == "fake-fail" else f"{backend}@rev"

    monkeypatch.setattr(page_routing, "_probe_local_model_identity", fake_probe)
    return calls


def _pdfs(folder: Path, count: int) -> list[Path]:
    paths = []
    for index in range(count):
        path = folder / f"doc{index}.pdf"
        path.write_bytes(b"%PDF-1.4 " + str(index).encode())
        paths.append(path)
    return paths


async def _identify(settings: Any, paths: list[Path]) -> list[str]:
    """Identify every path under one ingestion context, as one operation does."""
    context = build_ingestion_context(settings, embed_model=None)
    return [
        (await prepare_source(path, content_type=None, context=context)).index_identity
        for path in paths
    ]


@pytest.mark.asyncio
async def test_failing_probe_runs_once_for_three_sources(
    effective_settings: Any, probes: list[str], tmp_path: Path
) -> None:
    settings = effective_settings(ocr_fallback_enabled=True, ocr_local_backends=_LISTED)
    await _identify(settings, _pdfs(tmp_path, 3))
    assert probes.count("fake-fail") == 1


@pytest.mark.asyncio
async def test_a_second_operation_probes_again(
    effective_settings: Any, probes: list[str], tmp_path: Path
) -> None:
    settings = effective_settings(ocr_fallback_enabled=True, ocr_local_backends=_LISTED)
    paths = _pdfs(tmp_path, 3)
    await _identify(settings, paths)
    await _identify(settings, paths)
    assert probes.count("fake-fail") == 2
    assert probes.count("pp-ocrv6-small") == 1  # a success is cached across operations


@pytest.mark.asyncio
async def test_a_backend_that_appears_later_is_picked_up_next_operation(
    effective_settings: Any, probes: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = effective_settings(ocr_fallback_enabled=True, ocr_local_backends=_LISTED)
    paths = _pdfs(tmp_path, 2)
    before = await _identify(settings, paths)
    monkeypatch.setattr(page_routing, "_probe_local_model_identity", lambda *_: "fake-fail@rev")
    after = await _identify(settings, paths)
    assert before[0] != after[0]


@pytest.mark.asyncio
async def test_default_list_probes_nothing_extra(
    effective_settings: Any, probes: list[str], tmp_path: Path
) -> None:
    settings = effective_settings(ocr_fallback_enabled=True)
    await _identify(settings, _pdfs(tmp_path, 3))
    assert "fake-fail" not in probes
    assert probes.count("pp-ocrv6-small") == 1
