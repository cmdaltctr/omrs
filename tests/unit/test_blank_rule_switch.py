"""The ``blank`` rule obeys ``ocr_skip_blank_pages`` (change page-routing-panel, task 1.2).

Off, the rule returns an empty outcome before it calls the blank test, so no
page is rendered and no page is dropped. The rule keeps its place in the
fixed order: the maths and non-Latin rules then see every flagged page as
routed. The end-to-end test runs the page unit on the stubbed engines of
``test_page_unit_seam``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
    _stub_engine,
)

from omrs.integrations.pdf.page_rules import blank
from omrs.integrations.pdf.page_rules.base import RuleContext, RuleOutcome
from omrs.integrations.pdf.page_rules.pipeline import run_rules

FIND = "omrs.integrations.pdf.blank_pages.find_blank_pages"


class _Routes:
    def select(self, *, protocol: str) -> Any:
        return object()


def _ctx(settings: Any, flagged: tuple[int, ...] = (1, 2, 3)) -> RuleContext:
    pages = frozenset(flagged)
    return RuleContext(
        file=Path("doc.pdf"),
        evidence=[],
        flagged=pages,
        routed=pages,
        settings=settings,
        routes=_Routes(),
    )


def _spy(monkeypatch: pytest.MonkeyPatch, found: frozenset[int]) -> list[list[int]]:
    calls: list[list[int]] = []

    def fake(file: Any, pages: Any) -> frozenset[int]:
        calls.append(list(pages))
        return found

    monkeypatch.setattr(FIND, fake)
    return calls


def test_off_returns_an_empty_outcome_and_never_runs_the_blank_test(
    monkeypatch: pytest.MonkeyPatch, effective_settings: Any
) -> None:
    calls = _spy(monkeypatch, frozenset({2}))

    outcome = blank.RULE.run(_ctx(effective_settings(ocr_skip_blank_pages=False)))

    assert outcome == RuleOutcome()
    assert calls == []


def test_on_drops_what_the_blank_test_finds(
    monkeypatch: pytest.MonkeyPatch, effective_settings: Any
) -> None:
    calls = _spy(monkeypatch, frozenset({2}))

    outcome = blank.RULE.run(_ctx(effective_settings(ocr_skip_blank_pages=True)))

    assert outcome.drop == frozenset({2})
    assert calls == [[1, 2, 3]]


def test_off_through_run_rules_routes_every_flagged_page_to_the_later_rules(
    monkeypatch: pytest.MonkeyPatch, effective_settings: Any
) -> None:
    _spy(monkeypatch, frozenset({2}))
    monkeypatch.setattr(
        "omrs.integrations.pdf.maths_routing.detect_maths_pages",
        lambda file, settings: frozenset(),
    )
    settings = effective_settings(ocr_skip_blank_pages=False, ocr_maths_routing_enabled=True)

    plan = run_rules(Path("doc.pdf"), [], (1, 2, 3), settings, _Routes())

    assert plan.dropped == frozenset()
    assert plan.local == (1, 2, 3)
    seen = {run.name: run.ctx.routed for run in plan.runs}
    assert seen["blank"] == frozenset({1, 2, 3})
    assert seen["maths"] == frozenset({1, 2, 3})
    assert seen["non_latin"] == frozenset({1, 2, 3})


@pytest.fixture
def _no_maths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "omrs.integrations.pdf.maths_routing.detect_maths_pages",
        lambda file, settings: frozenset(),
    )


@pytest.mark.usefixtures("_no_maths")
def test_off_end_to_end_a_blank_flagged_page_reaches_the_local_tier(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, effective_settings: Any
) -> None:
    pytest.importorskip("pdf_inspector")
    scan = [
        _scan_page(0, "native 1", False),
        _scan_page(1, "", True),  # page 2: a blank sheet, flagged
        _scan_page(2, "native 3", False),
    ]
    engine = _EngineCalls(scan, ocr_pages_by_call=[[_ocr_page(2, "LOCAL two", 0.95)]])
    _stub_engine(monkeypatch, engine)
    calls = _spy(monkeypatch, frozenset({2}))
    worker = _FakeWorker()

    docs = _page_reader(
        _FakeInner(text="whole", metadata=_inner_metadata(3, flagged=1)),
        effective_settings(ocr_fallback_enabled=True, ocr_skip_blank_pages=False),
        worker,
    ).load_data(tmp_path / "doc.pdf")

    assert calls == []
    assert engine.ocr_calls[0]["page_numbers"] == [2]
    assert _counts(docs[0].metadata) == {
        "ocr_pages_native": 2,
        "ocr_pages_local": 1,
        "ocr_pages_worker": 0,
        "ocr_pages_blank": 0,
        "ocr_pages_unresolved": 0,
    }
