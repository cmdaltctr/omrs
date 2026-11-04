"""Non-Latin routing under the page unit (change non-latin-script-routing, tasks 2.1 to 2.4).

pdf-inspector, the blank test and the worker are stubbed, as in
``test_page_unit_seam``. ``extract_text_with_positions`` is stubbed too: it is
the one call ``detect`` makes before the local tier.
"""

from __future__ import annotations

import logging
import sys
from types import SimpleNamespace

import pytest
from tests.unit.test_page_unit_seam import (
    _counts,
    _EngineCalls,
    _FakeInner,
    _FakeWorker,
    _inner_metadata,
    _ocr_page,
    _page_reader,
    _scan_page,
)

from omrs.integrations.pdf import ocr_routing
from omrs.integrations.pdf.page_routing import local_ocr
from omrs.integrations.pdf.script_routing import (
    NON_LATIN_OUTPUT_REASON,
    PAGES_NON_LATIN_KEY,
    stamp_non_latin_count,
)

pytest.importorskip("pdf_inspector", reason="pdf-inspector is a base dependency (ADR-050)")

ARABIC = "ب" * 120
DEVANAGARI = "क" * 400
LATIN = "The quick brown fox jumps over the lazy dog. " * 6


def _item(page: int, text: str) -> SimpleNamespace:
    """One ``extract_text_with_positions`` item; ``page`` counts from 1."""
    return SimpleNamespace(page=page, text=text)


class _Engine(_EngineCalls):
    """The pdf_inspector stub plus ``extract_text_with_positions``."""

    def __init__(self, scan_pages, ocr_pages_by_call=None, items=(), items_error=None):
        super().__init__(scan_pages, ocr_pages_by_call)
        self.position_calls: list[tuple[str, list[int] | None]] = []
        self._items = list(items)
        self._items_error = items_error

    def extract_text_with_positions(self, path: str, pages=None):
        self.position_calls.append((path, list(pages) if pages is not None else None))
        if self._items_error is not None:
            raise self._items_error
        return [item for item in self._items if pages is None or item.page in pages]


def _stub(monkeypatch, engine: _Engine) -> None:
    monkeypatch.setitem(
        sys.modules,
        "pdf_inspector",
        SimpleNamespace(
            extract_pages_markdown=engine.extract_pages_markdown,
            process_pdf_with_ocr=engine.process_pdf_with_ocr,
            extract_text_with_positions=engine.extract_text_with_positions,
        ),
    )


@pytest.fixture(autouse=True)
def _blank_test_finds_nothing(monkeypatch):
    monkeypatch.setattr(
        "omrs.integrations.pdf.blank_pages.find_blank_pages", lambda file, pages: frozenset()
    )


def _read(effective_settings, tmp_path, scan, engine, worker, *, mode, **overrides):
    inner = _FakeInner(text="", metadata=_inner_metadata(len(scan), flagged=0))
    settings = effective_settings(
        ocr_fallback_enabled=True, ocr_non_latin_routing=mode, **overrides
    )
    return _page_reader(inner, settings, worker).load_data(tmp_path / "doc.pdf")


def _scan(*flags: bool):
    return [_scan_page(i, "" if flag else f"native {i + 1}", flag) for i, flag in enumerate(flags)]


# ── detect: the text layer, before the local tier (task 2.1) ──────────────


def test_detect_sends_a_flagged_arabic_text_layer_direct(monkeypatch, tmp_path, effective_settings):
    scan = _scan(False, True, True, False)
    engine = _Engine(
        scan,
        ocr_pages_by_call=[[_ocr_page(3, "LOCAL three", 0.95)]],
        items=[_item(2, ARABIC)],
    )
    _stub(monkeypatch, engine)
    worker = _FakeWorker(pages_markdown=["WORKER two"])

    docs = _read(effective_settings, tmp_path, scan, engine, worker, mode="detect")

    assert worker.calls[0]["pages"] == [2]
    assert [call["page_numbers"] for call in engine.ocr_calls] == [[3]]
    assert engine.position_calls == [(str(tmp_path / "doc.pdf"), [2, 3])]
    meta = docs[0].metadata
    assert _counts(meta) == {
        "ocr_pages_native": 2,
        "ocr_pages_local": 1,
        "ocr_pages_worker": 1,
        "ocr_pages_blank": 0,
        "ocr_pages_unresolved": 0,
    }
    assert meta[PAGES_NON_LATIN_KEY] == 1


def test_detect_leaves_a_scanned_page_on_the_local_tier(monkeypatch, tmp_path, effective_settings):
    """No text layer and a 7-letter watermark give no verdict: today's routing."""
    scan = _scan(True, True)
    engine = _Engine(
        scan,
        ocr_pages_by_call=[[_ocr_page(1, "LOCAL one", 0.95), _ocr_page(2, "LOCAL two", 0.95)]],
        items=[_item(1, "STAMP A")],
    )
    _stub(monkeypatch, engine)
    worker = _FakeWorker()

    docs = _read(effective_settings, tmp_path, scan, engine, worker, mode="detect")

    assert worker.calls == []
    assert engine.ocr_calls[0]["page_numbers"] == [1, 2]
    assert _counts(docs[0].metadata)["ocr_pages_local"] == 2
    assert docs[0].metadata[PAGES_NON_LATIN_KEY] == 0


def test_detect_leaves_a_latin_text_layer_on_the_local_tier(
    monkeypatch, tmp_path, effective_settings
):
    scan = _scan(True)
    engine = _Engine(
        scan, ocr_pages_by_call=[[_ocr_page(1, "LOCAL one", 0.95)]], items=[_item(1, LATIN)]
    )
    _stub(monkeypatch, engine)
    worker = _FakeWorker()

    _read(effective_settings, tmp_path, scan, engine, worker, mode="detect")

    assert worker.calls == []
    assert engine.ocr_calls[0]["page_numbers"] == [1]


def test_detect_reads_only_the_flagged_pages_and_skips_blank_ones(
    monkeypatch, tmp_path, effective_settings
):
    """Page 2 is flagged and blank: it leaves the route before the text check."""
    scan = _scan(False, True, True)
    monkeypatch.setattr(
        "omrs.integrations.pdf.blank_pages.find_blank_pages", lambda file, pages: frozenset({2})
    )
    engine = _Engine(
        scan,
        ocr_pages_by_call=[],
        items=[_item(2, ARABIC), _item(3, ARABIC)],
    )
    _stub(monkeypatch, engine)
    worker = _FakeWorker(pages_markdown=["WORKER three"])

    _read(effective_settings, tmp_path, scan, engine, worker, mode="detect")

    assert engine.position_calls[0][1] == [3]
    assert worker.calls[0]["pages"] == [3]
    assert engine.ocr_calls == []


def test_detect_makes_no_text_call_when_nothing_is_flagged(
    monkeypatch, tmp_path, effective_settings
):
    scan = _scan(False, False)
    engine = _Engine(scan)
    _stub(monkeypatch, engine)

    _read(effective_settings, tmp_path, scan, engine, _FakeWorker(), mode="detect")

    assert engine.position_calls == []


def test_a_failed_text_call_keeps_todays_routing(monkeypatch, tmp_path, effective_settings, caplog):
    scan = _scan(True)
    engine = _Engine(
        scan,
        ocr_pages_by_call=[[_ocr_page(1, "LOCAL one", 0.95)]],
        items_error=RuntimeError("boom"),
    )
    _stub(monkeypatch, engine)
    worker = _FakeWorker()

    with caplog.at_level(logging.WARNING):
        docs = _read(effective_settings, tmp_path, scan, engine, worker, mode="detect")

    assert worker.calls == []
    assert _counts(docs[0].metadata)["ocr_pages_local"] == 1
    assert "Non-Latin check skipped" in caplog.text


# ── always: every flagged page (task 2.1) ─────────────────────────────────


def test_always_sends_every_flagged_page_direct_and_runs_no_local_tier(
    monkeypatch, tmp_path, effective_settings
):
    scan = _scan(False, True, True, True)
    engine = _Engine(scan)
    _stub(monkeypatch, engine)
    worker = _FakeWorker(pages_markdown=["W2", "W3", "W4"])

    docs = _read(effective_settings, tmp_path, scan, engine, worker, mode="always")

    assert engine.ocr_calls == []
    assert engine.position_calls == []
    assert len(worker.calls) == 1
    assert worker.calls[0]["pages"] == [2, 3, 4]
    meta = docs[0].metadata
    assert _counts(meta)["ocr_pages_native"] == 1
    assert _counts(meta)["ocr_pages_worker"] == 3
    assert meta[PAGES_NON_LATIN_KEY] == 3
    assert "native 1" in docs[0].text


def test_always_keeps_unflagged_pages_native(monkeypatch, tmp_path, effective_settings):
    scan = _scan(False, False)
    engine = _Engine(scan)
    _stub(monkeypatch, engine)
    worker = _FakeWorker()

    docs = _read(effective_settings, tmp_path, scan, engine, worker, mode="always")

    assert worker.calls == []
    assert _counts(docs[0].metadata)["ocr_pages_native"] == 2
    assert docs[0].metadata[PAGES_NON_LATIN_KEY] == 0


def test_always_does_not_send_a_blank_page(monkeypatch, tmp_path, effective_settings):
    scan = _scan(True, True)
    monkeypatch.setattr(
        "omrs.integrations.pdf.blank_pages.find_blank_pages", lambda file, pages: frozenset({1})
    )
    engine = _Engine(scan)
    _stub(monkeypatch, engine)
    worker = _FakeWorker(pages_markdown=["W2"])

    docs = _read(effective_settings, tmp_path, scan, engine, worker, mode="always")

    assert worker.calls[0]["pages"] == [2]
    assert _counts(docs[0].metadata)["ocr_pages_blank"] == 1


def test_a_maths_page_that_is_also_non_latin_goes_once(monkeypatch, tmp_path, effective_settings):
    scan = _scan(True, True, True)
    monkeypatch.setattr(
        "omrs.integrations.pdf.maths_routing.detect_maths_pages",
        lambda file, settings: frozenset({2}),
    )
    engine = _Engine(scan)
    _stub(monkeypatch, engine)
    worker = _FakeWorker(pages_markdown=["W1", "W2", "W3"])

    docs = _read(
        effective_settings,
        tmp_path,
        scan,
        engine,
        worker,
        mode="always",
        ocr_maths_routing_enabled=True,
    )

    assert len(worker.calls) == 1
    assert worker.calls[0]["pages"] == [1, 2, 3]
    assert _counts(docs[0].metadata)["ocr_pages_worker"] == 3


# ── degrade: the engine gives no text for a direct page (spec: degrades to local) ──


def test_a_direct_page_the_engine_cannot_read_gets_local_text(
    monkeypatch, tmp_path, effective_settings, caplog
):
    scan = _scan(True)
    engine = _Engine(scan, ocr_pages_by_call=[[_ocr_page(1, "LOCAL one", 0.95)]])
    _stub(monkeypatch, engine)
    worker = _FakeWorker(pages_markdown=None)

    with caplog.at_level(logging.WARNING):
        docs = _read(effective_settings, tmp_path, scan, engine, worker, mode="always")

    assert worker.calls[0]["pages"] == [1]
    assert [call["page_numbers"] for call in engine.ocr_calls] == [[1]]
    assert docs[0].text == "LOCAL one"
    counts = _counts(docs[0].metadata)
    assert (counts["ocr_pages_local"], counts["ocr_pages_unresolved"]) == (1, 0)
    fallback = [r for r in caplog.records if "went to the local tier" in r.getMessage()]
    assert len(fallback) == 1
    assert "doc.pdf" in fallback[0].getMessage()


def test_a_maths_page_the_engine_cannot_read_gets_no_local_run(
    monkeypatch, tmp_path, effective_settings
):
    """Maths pages keep today's behaviour: only the non-Latin page falls back."""
    scan = _scan(True, True)
    monkeypatch.setattr(
        "omrs.integrations.pdf.maths_routing.detect_maths_pages",
        lambda file, settings: frozenset({2}),
    )
    engine = _Engine(scan, ocr_pages_by_call=[[_ocr_page(1, "LOCAL one", 0.95)]])
    _stub(monkeypatch, engine)
    worker = _FakeWorker(pages_markdown=None)

    docs = _read(
        effective_settings,
        tmp_path,
        scan,
        engine,
        worker,
        mode="always",
        ocr_maths_routing_enabled=True,
    )

    assert [call["page_numbers"] for call in engine.ocr_calls] == [[1]]
    counts = _counts(docs[0].metadata)
    assert (counts["ocr_pages_local"], counts["ocr_pages_unresolved"]) == (1, 1)


def test_a_direct_page_the_engine_read_runs_no_local_tier(
    monkeypatch, tmp_path, effective_settings
):
    scan = _scan(True)
    engine = _Engine(scan, ocr_pages_by_call=[[_ocr_page(1, "LOCAL one", 0.95)]])
    _stub(monkeypatch, engine)
    worker = _FakeWorker(pages_markdown=["WORKER one"])

    docs = _read(effective_settings, tmp_path, scan, engine, worker, mode="always")

    assert engine.ocr_calls == []
    assert docs[0].text == "WORKER one"
    assert _counts(docs[0].metadata)["ocr_pages_worker"] == 1


def test_the_local_fallback_respects_a_switched_off_local_tier(
    monkeypatch, tmp_path, effective_settings
):
    scan = _scan(True)
    engine = _Engine(scan, ocr_pages_by_call=[[_ocr_page(1, "LOCAL one", 0.95)]])
    _stub(monkeypatch, engine)
    monkeypatch.setattr(ocr_routing, "local_tier_off_reason", lambda *_: "switched off")
    worker = _FakeWorker(pages_markdown=None)

    docs = _read(effective_settings, tmp_path, scan, engine, worker, mode="always")

    assert engine.ocr_calls == []
    assert _counts(docs[0].metadata)["ocr_pages_unresolved"] == 1


# ── off: nothing changes (task 2.1) ───────────────────────────────────────


def test_off_changes_nothing(monkeypatch, tmp_path, effective_settings):
    scan = _scan(True)
    engine = _Engine(
        scan, ocr_pages_by_call=[[_ocr_page(1, DEVANAGARI, 0.95)]], items=[_item(1, ARABIC)]
    )
    _stub(monkeypatch, engine)
    worker = _FakeWorker()

    docs = _read(effective_settings, tmp_path, scan, engine, worker, mode="off")

    assert engine.position_calls == []
    assert worker.calls == []
    assert docs[0].text == DEVANAGARI
    assert PAGES_NON_LATIN_KEY not in docs[0].metadata


# ── degrade: no engine (task 2.3) ─────────────────────────────────────────


@pytest.mark.parametrize("mode", ["always", "detect"])
def test_no_engine_falls_back_to_the_local_tier_with_one_warning(
    monkeypatch, tmp_path, effective_settings, caplog, mode
):
    scan = _scan(True, True)
    engine = _Engine(
        scan,
        ocr_pages_by_call=[[_ocr_page(1, "LOCAL one", 0.95), _ocr_page(2, "LOCAL two", 0.95)]],
        items=[_item(1, ARABIC), _item(2, ARABIC)],
    )
    _stub(monkeypatch, engine)

    with caplog.at_level(logging.WARNING):
        docs = _read(
            effective_settings,
            tmp_path,
            scan,
            engine,
            None,
            mode=mode,
            ocr_engines=("dots-mocr", "paddleocr-vl"),
        )

    assert engine.ocr_calls[0]["page_numbers"] == [1, 2]
    meta = docs[0].metadata
    assert _counts(meta)["ocr_pages_local"] == 2
    assert meta[PAGES_NON_LATIN_KEY] == 0
    warnings = [r for r in caplog.records if "Non-Latin routing" in r.getMessage()]
    assert len(warnings) == 1
    assert "dots-mocr, paddleocr-vl" in warnings[0].getMessage()


def test_an_old_protocol_engine_counts_as_no_engine(
    monkeypatch, tmp_path, effective_settings, caplog
):
    scan = _scan(True)
    engine = _Engine(scan, ocr_pages_by_call=[[_ocr_page(1, "LOCAL one", 0.95)]])
    _stub(monkeypatch, engine)
    worker = _FakeWorker(protocol_version="1.0")

    docs = _read(effective_settings, tmp_path, scan, engine, worker, mode="always")

    assert worker.calls == []
    assert _counts(docs[0].metadata)["ocr_pages_local"] == 1


def test_no_warning_when_detect_finds_nothing(monkeypatch, tmp_path, effective_settings, caplog):
    scan = _scan(True)
    engine = _Engine(scan, ocr_pages_by_call=[[_ocr_page(1, "LOCAL", 0.95)]], items=[])
    _stub(monkeypatch, engine)

    with caplog.at_level(logging.WARNING):
        _read(effective_settings, tmp_path, scan, engine, None, mode="detect")

    assert "Non-Latin routing" not in caplog.text


# ── the post-local check (task 2.2) ───────────────────────────────────────


def test_detect_escalates_a_confident_non_latin_local_result(
    monkeypatch, tmp_path, effective_settings
):
    scan = _scan(True)
    engine = _Engine(scan, ocr_pages_by_call=[[_ocr_page(1, DEVANAGARI, 0.95)]])
    _stub(monkeypatch, engine)
    worker = _FakeWorker(pages_markdown=["WORKER one"])

    docs = _read(effective_settings, tmp_path, scan, engine, worker, mode="detect")

    assert worker.calls[0]["pages"] == [1]
    assert docs[0].text == "WORKER one"
    assert docs[0].metadata[PAGES_NON_LATIN_KEY] == 1


def test_detect_keeps_a_confident_latin_local_result(monkeypatch, tmp_path, effective_settings):
    scan = _scan(True)
    engine = _Engine(scan, ocr_pages_by_call=[[_ocr_page(1, LATIN, 0.95)]])
    _stub(monkeypatch, engine)
    worker = _FakeWorker()

    docs = _read(effective_settings, tmp_path, scan, engine, worker, mode="detect")

    assert worker.calls == []
    assert docs[0].text == LATIN.strip() or docs[0].text == LATIN
    assert docs[0].metadata[PAGES_NON_LATIN_KEY] == 0


def test_detect_without_an_engine_keeps_a_non_latin_local_result(
    monkeypatch, tmp_path, effective_settings
):
    """No engine to escalate to: the post-check runs as if the setting were off."""
    scan = _scan(True)
    engine = _Engine(scan, ocr_pages_by_call=[[_ocr_page(1, DEVANAGARI, 0.95)]])
    _stub(monkeypatch, engine)

    docs = _read(effective_settings, tmp_path, scan, engine, None, mode="detect")

    assert _counts(docs[0].metadata)["ocr_pages_local"] == 1
    assert docs[0].metadata[PAGES_NON_LATIN_KEY] == 0


def _local(monkeypatch, tmp_path, effective_settings, text, confidence, **overrides):
    engine = _Engine([], ocr_pages_by_call=[[_ocr_page(1, text, confidence)]])
    _stub(monkeypatch, engine)
    return local_ocr(tmp_path / "doc.pdf", [1], settings=effective_settings(**overrides))[0]


def test_local_ocr_adds_the_reason_whatever_the_confidence(
    monkeypatch, tmp_path, effective_settings
):
    page = _local(
        monkeypatch, tmp_path, effective_settings, DEVANAGARI, 0.95, ocr_non_latin_routing="detect"
    )
    assert (page.escalates, page.reasons) == (True, (NON_LATIN_OUTPUT_REASON,))


def test_local_ocr_lists_both_reasons_when_confidence_is_low_too(
    monkeypatch, tmp_path, effective_settings
):
    page = _local(
        monkeypatch, tmp_path, effective_settings, DEVANAGARI, 0.2, ocr_non_latin_routing="detect"
    )
    assert page.reasons == ("low_confidence", NON_LATIN_OUTPUT_REASON)


@pytest.mark.parametrize("mode", ["off", "always"])
def test_local_ocr_checks_the_script_only_under_detect(
    monkeypatch, tmp_path, effective_settings, mode
):
    page = _local(
        monkeypatch, tmp_path, effective_settings, DEVANAGARI, 0.95, ocr_non_latin_routing=mode
    )
    assert (page.escalates, page.reasons) == (False, ())


def test_local_ocr_gives_no_verdict_on_short_text(monkeypatch, tmp_path, effective_settings):
    page = _local(
        monkeypatch, tmp_path, effective_settings, "क" * 10, 0.95, ocr_non_latin_routing="detect"
    )
    assert page.escalates is False


# ── the count (task 2.4) ──────────────────────────────────────────────────


def test_the_count_is_stamped_only_when_the_setting_is_on(effective_settings):
    off: dict = {}
    stamp_non_latin_count(off, effective_settings(ocr_non_latin_routing="off"), {1, 2}, [])
    assert off == {}
    on: dict = {}
    escalated = [
        SimpleNamespace(reasons=(NON_LATIN_OUTPUT_REASON,)),
        SimpleNamespace(reasons=("low_confidence",)),
        None,
    ]
    stamp_non_latin_count(on, effective_settings(ocr_non_latin_routing="detect"), {5}, escalated)
    assert on == {PAGES_NON_LATIN_KEY: 2}
