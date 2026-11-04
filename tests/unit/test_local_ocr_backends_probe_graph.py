"""The graph ingest path resolves the local OCR entries once per run.

Change local-ocr-backends, follow-up fix. ``identify_adapter`` builds one
ingestion context per source. The host computes the ingestion shape once per
admitted run, so the run holds the resolved routing payload and the
``local_ocr_backends`` entry there. A failed probe runs once per run, never
once per source, and the next run probes again.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.pipeline_parity.ingestion.snapshot import pin_detection
from tests.unit.test_ingestion_graph_adapters_support import (
    admit,
    build_catalogue,
    canonical_graph,
    invoke,
    offline_settings,
    resources,
)

from omrs.core import reading_parts
from omrs.core.ingestion.sources import SourceUnit
from omrs.core.reading_parts import LocalOcrBackendDescriptor
from omrs.core.vectordb import get_default_store
from omrs.integrations.pdf import page_routing

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "smoke_text.pdf"
_FAILING = LocalOcrBackendDescriptor(
    name="fake-fail",
    import_path="tests.fake:BACKEND",
    label="Fake that never resolves",
    help_key="local_ocr_backend.fake-fail",
    producer="fake_fail_ocr",
    min_confidence=0.8,
    calibrated_by="1-fake-experiment",
    keeps_scripts=None,
)
_LISTED = ("pp-ocrv6-small", "fake-fail")


@pytest.fixture(autouse=True)
def fake_table(monkeypatch: pytest.MonkeyPatch) -> Any:
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


@pytest.fixture
def pdf_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    pin_detection(monkeypatch)
    root = tmp_path / "pdfs"
    root.mkdir()
    for index in range(3):
        shutil.copy(FIXTURE, root / f"doc{index}.pdf")
    return root


def _host(effective_settings: Any, **update: Any) -> Any:
    """Offline settings with OCR routing on, so the local models resolve."""
    return offline_settings(effective_settings).model_copy(
        update={"ocr_fallback_enabled": True, **update}
    )


async def _run(root: Path, settings: Any) -> list[str]:
    """Identify the three sources under ONE run's resources; return their identities."""
    catalogue = build_catalogue()
    snapshot = admit(canonical_graph("probe_once"), settings, root, catalogue)
    run_resources = resources(snapshot, catalogue, get_default_store())
    identities = []
    for index in range(3):
        unit = SourceUnit(index, root / f"doc{index}.pdf", f"doc{index}.pdf", None)
        out = await invoke(snapshot, catalogue, run_resources, "identify", {"sources": (unit,)})
        identities.append(out.values["sources"].identity.index_identity)
    return identities


@pytest.mark.asyncio
async def test_failing_probe_runs_once_per_graph_run(
    pdf_root: Path, effective_settings: Any, probes: list[str]
) -> None:
    host = _host(effective_settings, ocr_local_backends=_LISTED)
    await _run(pdf_root, host)
    assert probes.count("fake-fail") == 1


@pytest.mark.asyncio
async def test_the_next_graph_run_probes_again(
    pdf_root: Path, effective_settings: Any, probes: list[str]
) -> None:
    host = _host(effective_settings, ocr_local_backends=_LISTED)
    await _run(pdf_root, host)
    await _run(pdf_root, host)
    assert probes.count("fake-fail") == 2
    assert probes.count("pp-ocrv6-small") == 1  # a success stays cached across runs


@pytest.mark.asyncio
async def test_default_tier_failure_resolves_once_per_graph_run(
    pdf_root: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fail(settings: Any, backend: str = "pp-ocrv6-small") -> None:
        calls.append(backend)

    monkeypatch.setattr(page_routing, "_probe_local_model_identity", fail)
    host = _host(effective_settings)
    await _run(pdf_root, host)
    assert calls == ["pp-ocrv6-small"]
