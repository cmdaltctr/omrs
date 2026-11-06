"""Golden behaviour snapshots of the page unit (change local-ocr-backends, tasks 1.4, 1.5).

The fixture PDF ``tests/fixtures/page_routing/routing_fixture.pdf`` has one page of
each kind the page unit routes: native text, scanned and flagged, blank and
flagged, maths font, and an Arabic text layer (flagged). Task 1.4 tests prove each
page is what its name says, using the real detectors.

Task 1.5 reads the fixture through ``OcrRoutedPdfInspector`` once per combination
and compares every emitted document, text and metadata, with a committed JSON
snapshot. The page scan, blank test, maths detector and script detector all run for
real, and so does the inner pdf-inspector reader. Only two things are fake:

- the local OCR engine, faked at the engine call (``pdf_inspector.process_pdf_with_ocr``)
  so the escalation rule in ``page_routing.local_ocr`` still runs;
- the OCR engine (the worker), an injected ``ocr_client``.

The snapshots must stay byte-identical while the page rules and the local backend
chain move into new modules, so this file names no internal helper of either.

Write or refresh the snapshots with ``OMRS_WRITE_GOLDEN=1``. Without it, a missing
snapshot fails.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from omrs.integrations.ocr_worker.protocol import make_success
from omrs.integrations.pdf import page_routing
from omrs.integrations.pdf.blank_pages import find_blank_pages
from omrs.integrations.pdf.maths_pages import maths_font_pages
from omrs.integrations.pdf.ocr_routing import OcrRoutedPdfInspector
from omrs.integrations.pdf.page_routing import page_evidence
from omrs.integrations.pdf.pdf_inspector import PdfInspectorReader
from omrs.integrations.pdf.script_routing import is_non_latin

pdf_inspector = pytest.importorskip(
    "pdf_inspector", reason="pdf-inspector is a base dependency (ADR-050)"
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "page_routing"
FIXTURE_PDF = FIXTURE_DIR / "routing_fixture.pdf"
GOLDEN_DIR = FIXTURE_DIR / "golden"

SCANNED_PAGE = 2
BLANK_PAGE = 3
MATHS_PAGE = 4
ARABIC_PAGE = 5

#: 60 Arabic letters: past the detector's 40-letter floor, no Latin letter.
ARABIC_TEXT = "ب" * 60

#: Placeholders for absolute paths that metadata may carry.
FIXTURE_MARK = "<fixture>"
FIXTURE_DIR_MARK = "<fixture dir>"


# ── Task 1.4: the fixture is what its name says ───────────────────────────


def test_fixture_has_five_pages_and_the_scan_flags_the_expected_ones():
    evidence = page_evidence(FIXTURE_PDF)

    assert [entry.page for entry in evidence] == [1, 2, 3, 4, 5]
    assert [entry.page for entry in evidence if entry.needs_ocr] == [
        SCANNED_PAGE,
        BLANK_PAGE,
        ARABIC_PAGE,
    ]
    native = evidence[0]
    assert "native text" in native.markdown


def test_blank_test_marks_only_the_blank_page():
    assert find_blank_pages(FIXTURE_PDF, [SCANNED_PAGE, BLANK_PAGE, ARABIC_PAGE]) == {BLANK_PAGE}


def test_maths_detector_marks_only_the_maths_page():
    assert maths_font_pages(FIXTURE_PDF) == {MATHS_PAGE}


def test_script_detector_marks_the_arabic_text_layer_and_no_other_page():
    items = pdf_inspector.extract_text_with_positions(str(FIXTURE_PDF), [1, 2, 3, 4, 5])
    by_page: dict[int, list[str]] = {}
    for item in items:
        by_page.setdefault(item.page, []).append(item.text)

    verdicts = {page: is_non_latin(" ".join(texts)) for page, texts in by_page.items()}

    assert verdicts[ARABIC_PAGE] is True
    assert verdicts[1] is False
    assert verdicts[MATHS_PAGE] is False


# ── Task 1.5: the fakes ───────────────────────────────────────────────────


class _LocalPanic(BaseException):
    """Stands in for ``pyo3_runtime.PanicException``: a BaseException, not an Exception."""


def _local_page(number: int, markdown: str, confidence: float, hosted: bool = False) -> Any:
    """One ``process_pdf_with_ocr`` page, in the shape ``local_ocr`` reads."""
    provenance = SimpleNamespace(
        source="ocr",
        ocr_confidence=confidence,
        ocr_model=SimpleNamespace(name="golden-model", revision="golden-rev"),
        hosted_recommended=hosted,
        warnings=[],
    )
    return SimpleNamespace(page_number=number, markdown=markdown, provenance=provenance)


#: The fixed local OCR output for each page the tier may be asked to read. Pages 3
#: and 4 are normally not read here (blank, and unflagged), so a snapshot changes
#: when a rule stops removing or redirecting them.
_LOCAL_OUTPUT = {
    SCANNED_PAGE: ("Local text for the scanned page.", 0.95, False),
    BLANK_PAGE: ("", 0.3, True),
    MATHS_PAGE: ("Local text for the maths page.", 0.5, False),
    ARABIC_PAGE: (ARABIC_TEXT, 0.95, False),
}


class _FakeEngine:
    """Replaces ``pdf_inspector.process_pdf_with_ocr`` and logs each page list."""

    def __init__(self, failure: BaseException | None = None) -> None:
        self.calls: list[list[int]] = []
        self._failure = failure

    def __call__(self, path: str, **kwargs: Any) -> Any:
        pages = sorted(kwargs["page_numbers"])
        self.calls.append(pages)
        if self._failure is not None:
            raise self._failure
        return SimpleNamespace(
            pages=[_local_page(number, *_LOCAL_OUTPUT[number]) for number in pages],
            pages_recommending_hosted=[],
        )


class _FakeWorker:
    """An in-process OCR engine returning ``worker text page N`` per requested page."""

    def __init__(self) -> None:
        self.fingerprint = SimpleNamespace(
            available=True, protocol_version="1.1", backend_id="paddleocr_vl"
        )
        self.calls: list[list[int]] = []

    def parse(self, pdf_path: str, *, pages: list[int] | None = None, timeout: Any = None) -> Any:
        assert pages is not None, "page routing never sends a whole-PDF request"
        self.calls.append(list(pages))
        return make_success(
            "golden",
            "\n\n".join(f"worker text page {page}" for page in pages),
            ocr_backend="paddleocr-vl",
            page_count=len(pages),
            pages_markdown=[f"worker text page {page}" for page in pages],
        )


def _reset_routing_state() -> None:
    """Reset the process state the local tier keeps between cases.

    The panic switch lives in the local OCR registry, per backend (design D17).
    """
    from omrs.integrations.pdf.local_ocr import registry as local_ocr_registry

    local_ocr_registry.BACKENDS.reset_off()
    page_routing.reset_local_model_resolution()


@pytest.fixture(autouse=True)
def _clean_routing_state():
    _reset_routing_state()
    yield
    _reset_routing_state()


# ── Task 1.5: the combinations ────────────────────────────────────────────

_NORMAL = "normal"
_MISSING = "local-missing"
_PANIC = "local-panic"

#: (combination name, maths routing on, non-Latin mode, engine available, local tier)
COMBINATIONS = [
    *(
        (
            f"maths-{'on' if maths else 'off'}_nonlatin-{mode}_engine-{'yes' if engine else 'no'}",
            maths,
            mode,
            engine,
            _NORMAL,
        )
        for maths in (False, True)
        for mode in ("off", "detect", "always")
        for engine in (True, False)
    ),
    ("maths-off_nonlatin-off_engine-yes_local-missing", False, "off", True, _MISSING),
    ("maths-off_nonlatin-off_engine-yes_local-panic", False, "off", True, _PANIC),
]


def _first_difference(expected: Any, actual: Any, path: str = "$") -> str | None:
    """Return the JSON path of the first difference between two values, or ``None``."""
    if type(expected) is not type(actual):
        return f"{path}: expected {expected!r}, got {actual!r}"
    if isinstance(expected, dict):
        for key in sorted(set(expected) | set(actual)):
            if key not in expected:
                return f"{path}.{key}: unexpected key, value {actual[key]!r}"
            if key not in actual:
                return f"{path}.{key}: key missing, expected {expected[key]!r}"
            found = _first_difference(expected[key], actual[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(expected, list):
        for index, (left, right) in enumerate(zip(expected, actual, strict=False)):
            found = _first_difference(left, right, f"{path}[{index}]")
            if found:
                return found
        if len(expected) != len(actual):
            return f"{path}: expected {len(expected)} item(s), got {len(actual)}"
        return None
    return None if expected == actual else f"{path}: expected {expected!r}, got {actual!r}"


def _normalise(value: Any) -> Any:
    """Replace the fixture's absolute path in a metadata value with a placeholder."""
    if isinstance(value, str):
        return value.replace(str(FIXTURE_PDF), FIXTURE_MARK).replace(
            str(FIXTURE_DIR), FIXTURE_DIR_MARK
        )
    return value


def _snapshot(documents: list, worker: _FakeWorker | None, engine: _FakeEngine) -> dict[str, Any]:
    """Return what a combination emitted, as plain JSON values."""
    return {
        "documents": [
            {
                "text": document.text,
                "metadata": {key: _normalise(value) for key, value in document.metadata.items()},
            }
            for document in documents
        ],
        "engine_calls": worker.calls if worker is not None else [],
        "local_calls": engine.calls,
    }


def _dump(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


@pytest.mark.parametrize(
    ("name", "maths", "mode", "engine_available", "local_tier"),
    COMBINATIONS,
    ids=[combination[0] for combination in COMBINATIONS],
)
def test_golden_snapshot(
    name, maths, mode, engine_available, local_tier, monkeypatch, effective_settings
):
    failures = {
        _NORMAL: None,
        _MISSING: RuntimeError("local OCR runtime is not installed"),
        _PANIC: _LocalPanic("the engine lock is poisoned"),
    }
    local = _FakeEngine(failure=failures[local_tier])
    monkeypatch.setattr(pdf_inspector, "process_pdf_with_ocr", local)
    worker = _FakeWorker() if engine_available else None
    # Change local-ocr-per-backend-cuts: the snapshots were taken at the old default cut
    # 0.9. An explicit entry keeps them as proof that the chain logic did not move.
    settings = effective_settings(
        ocr_fallback_enabled=True,
        ocr_maths_routing_enabled=maths,
        ocr_non_latin_routing=mode,
        ocr_local_cuts={"pp-ocrv6-small": 0.9},
    )
    reader = OcrRoutedPdfInspector(PdfInspectorReader(), settings=settings, ocr_client=worker)

    documents = reader.load_data(FIXTURE_PDF)

    # Only a panic (a BaseException) switches the local tier off for the process.
    assert (page_routing.local_tier_off_reason() is not None) == (local_tier == _PANIC)
    actual = json.loads(_dump(_snapshot(documents, worker, local)))
    golden = GOLDEN_DIR / f"{name}.json"
    if os.environ.get("OMRS_WRITE_GOLDEN") == "1":
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(_dump(actual), encoding="utf-8")
    assert golden.exists(), f"snapshot {golden.name} is missing; run with OMRS_WRITE_GOLDEN=1"
    text = golden.read_text(encoding="utf-8")
    difference = _first_difference(json.loads(text), actual)
    assert difference is None, f"{golden.name} differs at {difference}"
    assert text == _dump(actual), f"{golden.name} differs in layout only"
