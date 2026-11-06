"""The ordered local OCR backend list (changes local-ocr-backends and local-ocr-per-backend-cuts).

``page_routing.local_ocr`` runs the chain: the first listed backend reads every
page in one call, the shared escalation rule runs on its results, a kept page
names the backend's producer, and every other page passes to the next backend in
one call. The real ``pp-ocrv6-small`` registration runs on a ``pdf_inspector``
stub; the other backend is a fake registered with snapshot and restore.
"""

from __future__ import annotations

import logging
import sys
from types import SimpleNamespace

import pytest

from omrs.integrations.pdf import page_routing
from omrs.integrations.pdf.local_ocr import chain, registry
from omrs.integrations.pdf.local_ocr.base import BackendPage

ARABIC = "ب" * 300
BENGALI = "ক" * 300
DEVANAGARI = "क" * 400
LATIN = "a" * 300

#: A fake backend named after Indra, with the facts design D19 gives it.
FAKE = "fake-indra"
FAKE_PRODUCER = "indra_ocr"
PP = "pp-ocrv6-small"


class _Panic(BaseException):
    """Stands in for ``pyo3_runtime.PanicException``: not an ``Exception``."""


class _Backend:
    """A fake backend replaying one result per call, recording each call."""

    def __init__(self, *calls) -> None:
        self.calls: list[list[int]] = []
        self._calls = list(calls)

    def read_pages(self, file, pages, *, settings):
        self.calls.append(list(pages))
        result = self._calls.pop(0)
        if isinstance(result, BaseException):
            raise result
        return [BackendPage(page, text, conf, "fake@1") for page, (text, conf) in result.items()]

    def identity(self, settings):
        return "fake@1"


class _PdfInspector:
    """A ``pdf_inspector`` stub for the real PP-OCRv6 backend."""

    def __init__(self, *calls) -> None:
        self.calls: list[list[int]] = []
        self._calls = list(calls)

    def process_pdf_with_ocr(self, path, **kwargs):
        self.calls.append(list(kwargs["page_numbers"]))
        result = self._calls.pop(0)
        if isinstance(result, BaseException):
            raise result
        pages = []
        for page, (text, conf) in result.items():
            provenance = SimpleNamespace(
                ocr_confidence=conf,
                ocr_model=SimpleNamespace(name="pp-ocrv6-small", revision="r"),
                hosted_recommended=False,
            )
            pages.append(SimpleNamespace(page_number=page, markdown=text, provenance=provenance))
        return SimpleNamespace(pages=pages)


@pytest.fixture(autouse=True)
def isolated_registry():
    state = registry.BACKENDS.snapshot()
    chain.reset_skip_warnings()
    yield
    registry.BACKENDS.restore(state)
    chain.reset_skip_warnings()


def _fake(backend, *, cut=0.94, name=FAKE, producer=None):
    registry.register(
        name,
        f"fake.{name}:BACKEND",
        producer=producer or FAKE_PRODUCER,
        min_confidence=cut,
        calibrated_by="46a-local-ocr-per-backend-cuts-2026-11-06",
    )
    registry.BACKENDS.cache[name] = backend
    return backend


def _pp(monkeypatch, *calls) -> _PdfInspector:
    stub = _PdfInspector(*calls)
    monkeypatch.setitem(sys.modules, "pdf_inspector", stub)
    return stub


def _settings(*backends, cuts=None, mode="off"):
    return SimpleNamespace(
        ocr_local_backends=tuple(backends),
        ocr_local_cuts=cuts or {},
        ocr_non_latin_routing=mode,
        ocr_local_model_directory="",
        ocr_local_offline=False,
    )


def _read(settings, pages, tmp_path):
    return {p.page: p for p in page_routing.local_ocr(tmp_path / "a.pdf", pages, settings=settings)}


# ── Pass-on and confidence cuts (design D8 steps 1 to 4) ───────────────────


def test_the_second_backend_keeps_a_latin_page(monkeypatch, tmp_path) -> None:
    fake = _fake(_Backend({1: (LATIN, 0.80)}))
    pp = _pp(monkeypatch, {1: ("latin text " * 10, 0.95)})

    page = _read(_settings(FAKE, PP), [1], tmp_path)[1]

    assert fake.calls == [[1]]
    assert pp.calls == [[1]]
    assert page.escalates is False
    assert page.producer == "pdf_inspector_ocr"
    assert page.text.startswith("latin text")


def test_both_backends_escalate_with_the_last_backend_reasons(monkeypatch, tmp_path) -> None:
    _fake(_Backend({1: (BENGALI, 0.80)}))
    _pp(monkeypatch, {1: ("some text", 0.6)})

    page = _read(_settings(FAKE, PP), [1], tmp_path)[1]

    assert page.escalates is True
    assert page.reasons == ("low_confidence",)


def test_a_backend_keeps_a_latin_page_above_its_cut(monkeypatch, tmp_path) -> None:
    _fake(_Backend({1: (LATIN, 0.95)}))
    pp = _pp(monkeypatch)

    page = _read(_settings(FAKE, PP), [1], tmp_path)[1]

    assert page.escalates is False
    assert page.producer == FAKE_PRODUCER
    assert page.text == LATIN
    assert pp.calls == [], "a kept page does not pass on"


def test_a_backend_keeps_a_bengali_page_above_its_cut(tmp_path) -> None:
    _fake(_Backend({1: (BENGALI, 0.95)}))

    page = _read(_settings(FAKE), [1], tmp_path)[1]

    assert page.escalates is False
    assert page.reasons == ()
    assert page.producer == FAKE_PRODUCER


def test_an_arabic_page_below_the_cut_passes_on_with_low_confidence(monkeypatch, tmp_path) -> None:
    _fake(_Backend({1: (ARABIC, 0.93)}))
    pp = _pp(monkeypatch, {1: ("pp text", 0.5)})

    page = _read(_settings(FAKE, PP), [1], tmp_path)[1]

    assert pp.calls == [[1]]
    assert page.reasons == ("low_confidence",)


def test_no_page_carries_the_retired_script_reason(tmp_path) -> None:
    _fake(_Backend({1: (BENGALI, 0.5), 2: ("ب" * 12, 0.95), 3: (LATIN, 0.95)}))

    pages = _read(_settings(FAKE), [1, 2, 3], tmp_path)

    assert pages[1].reasons == ("low_confidence",)
    assert pages[2].reasons == ()
    assert pages[3].reasons == ()


def test_only_escalated_pages_pass_on_in_one_call(monkeypatch, tmp_path) -> None:
    _fake(_Backend({1: (ARABIC, 0.95), 2: (LATIN, 0.80), 3: (ARABIC, 0.5)}))
    pp = _pp(monkeypatch, {2: ("two", 0.95), 3: ("three", 0.95)})

    pages = _read(_settings(FAKE, PP), [3, 1, 2], tmp_path)

    assert pp.calls == [[2, 3]]
    producers = [pages[n].producer for n in (1, 2, 3)]
    assert producers == [FAKE_PRODUCER, "pdf_inspector_ocr", "pdf_inspector_ocr"]


def test_each_backend_uses_its_own_cut_unless_it_has_an_entry(tmp_path) -> None:
    _fake(_Backend({1: (ARABIC, 0.91)}, {1: (ARABIC, 0.91)}, {1: (ARABIC, 0.91)}), cut=0.90)

    assert _read(_settings(FAKE), [1], tmp_path)[1].escalates is False
    assert _read(_settings(FAKE, cuts={FAKE: 0.95}), [1], tmp_path)[1].reasons == (
        "low_confidence",
    )
    # An entry for another backend leaves this backend's own cut alone.
    assert _read(_settings(FAKE, cuts={PP: 0.99}), [1], tmp_path)[1].escalates is False


def test_the_default_backend_keeps_a_page_at_its_cut_and_escalates_one_below(
    monkeypatch, tmp_path
) -> None:
    _pp(monkeypatch, {1: ("kept", 0.92), 2: ("lost", 0.91)})

    pages = _read(_settings(PP), [1, 2], tmp_path)

    assert pages[1].escalates is False
    assert pages[2].reasons == ("low_confidence",)


def test_a_missing_page_passes_on(monkeypatch, tmp_path) -> None:
    _fake(_Backend({}))
    _pp(monkeypatch, {1: ("found", 0.95)})

    page = _read(_settings(FAKE, PP), [1], tmp_path)[1]

    assert page.escalates is False
    assert page.text == "found"


# ── Unresolved text (design D8 step 5) ─────────────────────────────────────


def test_an_unresolved_page_keeps_the_first_backend_text(monkeypatch, tmp_path) -> None:
    _fake(_Backend({1: (ARABIC, 0.80)}))
    _pp(monkeypatch, {1: ("pp text", 0.5)})

    page = _read(_settings(FAKE, PP), [1], tmp_path)[1]

    assert page.escalates is True
    assert page.text == ARABIC
    assert page.producer == FAKE_PRODUCER


def test_an_empty_first_text_falls_to_the_next_backend_text(monkeypatch, tmp_path) -> None:
    _fake(_Backend({1: ("", 0.95)}))
    _pp(monkeypatch, {1: ("pp text", 0.5)})

    page = _read(_settings(FAKE, PP), [1], tmp_path)[1]

    assert page.text == "pp text"
    assert page.producer == "pdf_inspector_ocr"


def test_a_page_no_backend_gave_text_names_no_producer(monkeypatch, tmp_path) -> None:
    _fake(_Backend({1: ("", 0.95)}))
    _pp(monkeypatch, {1: (" ", 0.95)})

    page = _read(_settings(FAKE, PP), [1], tmp_path)[1]

    assert page.text.strip() == ""
    assert page.producer is None


# ── Skipped and switched-off backends (design D8 step 6) ───────────────────


def test_a_backend_not_installed_is_skipped_with_one_warning(monkeypatch, tmp_path, caplog) -> None:
    missing = ImportError("indra_ocr is not installed")
    _fake(_Backend(missing, missing))
    pp = _pp(monkeypatch, {1: ("one", 0.95)}, {1: ("one", 0.95)})

    with caplog.at_level(logging.WARNING):
        first = _read(_settings(FAKE, PP), [1], tmp_path)[1]
        second = _read(_settings(FAKE, PP), [1], tmp_path)[1]

    assert pp.calls == [[1], [1]]
    assert first.producer == second.producer == "pdf_inspector_ocr"
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, warnings
    assert FAKE in warnings[0]


def test_a_panic_switches_one_backend_off_and_the_other_reads_the_next_file(
    monkeypatch, tmp_path
) -> None:
    fake = _fake(_Backend({1: (ARABIC, 0.5)}, {1: (ARABIC, 0.5)}))
    pp = _pp(monkeypatch, _Panic("engine lock poisoned"))

    first = _read(_settings(FAKE, PP), [1], tmp_path)[1]
    second = _read(_settings(FAKE, PP), [1], tmp_path)[1]

    assert registry.off_reason(PP) == "_Panic: engine lock poisoned"
    assert registry.off_reason(FAKE) is None
    assert fake.calls == [[1], [1]]
    assert pp.calls == [[1]], "a switched-off backend is not called again"
    assert first.reasons == second.reasons == ("low_confidence",)
    assert page_routing.local_tier_off_reason(_settings(FAKE, PP)) is None


def test_every_listed_backend_failing_raises_the_first_failure(tmp_path) -> None:
    _fake(_Backend(ImportError("first missing")))
    _fake(_Backend(ImportError("second missing")), name="fake-two", producer="two")

    with pytest.raises(ImportError, match="first missing"):
        _read(_settings(FAKE, "fake-two"), [1], tmp_path)


def test_the_default_list_without_its_runtime_raises_as_before(monkeypatch, tmp_path) -> None:
    monkeypatch.setitem(sys.modules, "pdf_inspector", None)

    with pytest.raises(ImportError, match="pdf_inspector is not installed. Install with: uv sync"):
        _read(_settings(PP), [1], tmp_path)


def test_a_panic_in_the_only_backend_switches_the_tier_off(monkeypatch, tmp_path) -> None:
    _pp(monkeypatch, _Panic("poisoned"))

    with pytest.raises(_Panic):
        _read(_settings(PP), [1], tmp_path)

    assert page_routing.local_tier_off_reason(_settings(PP)) == "_Panic: poisoned"


# ── Post-checks under detect: no backend is exempt ─────────────────────────


def test_detect_escalates_non_latin_output_of_every_backend(monkeypatch, tmp_path) -> None:
    _fake(_Backend({1: (DEVANAGARI, 0.95)}))
    pp = _pp(monkeypatch, {1: ("latin text " * 10, 0.95)})

    page = _read(_settings(FAKE, PP, mode="detect"), [1], tmp_path)[1]

    assert pp.calls == [[1]], "the Indra-like backend is not exempt, so the page passes on"
    assert page.escalates is False
    assert page.producer == "pdf_inspector_ocr"


def test_detect_names_non_latin_output_when_the_last_backend_gives_it(tmp_path) -> None:
    _fake(_Backend({1: (DEVANAGARI, 0.95)}))

    page = _read(_settings(FAKE, mode="detect"), [1], tmp_path)[1]

    assert page.reasons == ("non_latin_output",)


def test_detect_still_escalates_non_latin_output_of_the_default_backend(
    monkeypatch, tmp_path
) -> None:
    _pp(monkeypatch, {1: (DEVANAGARI, 0.95)})

    page = _read(_settings(PP, mode="detect"), [1], tmp_path)[1]

    assert page.reasons == ("non_latin_output",)


def test_each_post_check_receives_the_backend_facts(tmp_path) -> None:
    _fake(_Backend({1: (ARABIC, 0.95)}))
    seen: list = []

    def _check(text, facts):
        seen.append(facts)
        return None

    page_routing.local_ocr(tmp_path / "a.pdf", [1], settings=_settings(FAKE), post_checks=(_check,))

    assert "keeps_scripts" not in seen[0]
    assert seen[0]["min_confidence"] == 0.94
    assert seen[0]["producer"] == FAKE_PRODUCER
