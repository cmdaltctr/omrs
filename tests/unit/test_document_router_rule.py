"""The ``document_router`` page rule (change document-reading-routers, tasks 3.3 and 3.4).

The rule judges the unflagged pages with native text that no earlier rule
claimed, one page at a time, and adds the pages whose P(yes) is below the
threshold. With no judge, or a judge that cannot run, it returns an empty
outcome without reading a page and the page unit reads as before. Every judge
here is a fake: no test contacts a model.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from omrs.integrations.pdf.page_rules import document_router, registry
from omrs.integrations.pdf.page_rules.base import RuleContext, RuleOutcome
from omrs.integrations.pdf.page_rules.pipeline import run_rules

RULE = document_router.RULE
STAMP_KEYS = (
    "router_pages_judged",
    "router_pages_accepted",
    "router_pages_rejected",
    "router_pages_unjudged",
    "router_status",
)
REASONS = (
    "unknown-model",
    "unreachable",
    "quantisation-refused",
    "projector-not-loaded",
    "wrong-build",
    "renderer-missing",
    "needs-opt-in",
    "request-failed",
    "malformed-reply",
)
RENDERER = "omrs.integrations.pdf.page_images"


class FakeJudge:
    """A page judge with fixed answers per page text; it records each call."""

    def __init__(
        self,
        answers: dict[str, float | None] | None = None,
        *,
        threshold: float = 0.17,
        images: bool = False,
        max_chars: int = 2000,
        status: str | None = None,
        default: float | None = 0.9,
    ) -> None:
        self.name = "junk"
        self.question = "Does the text match the page image?"
        self.threshold = threshold
        self.images = images
        self.max_chars = max_chars
        self.hosted = False
        self.status = status
        self.identity = {"kind": "llamacpp", "model": "clef-flash-q8_0"}
        self.calls: list[tuple[str, bytes | None]] = []
        self._answers = answers or {}
        self._default = default

    def judge(self, text: str, image: bytes | None) -> float | None:
        self.calls.append((text, image))
        return self._answers.get(text, self._default)


def _page(number: int, text: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(page=number, markdown=f"page {number}" if text is None else text)


def _ctx(
    evidence: list[SimpleNamespace],
    judge: Any,
    *,
    flagged: frozenset[int] = frozenset(),
    claimed: frozenset[int] = frozenset(),
) -> RuleContext:
    return RuleContext(
        file=Path("doc.pdf"),
        evidence=evidence,
        flagged=flagged,
        routed=flagged,
        settings=SimpleNamespace(),
        routes=None,
        claimed=claimed,
        judge=judge,
    )


def _stamp(ctx: RuleContext, outcome: RuleOutcome) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    RULE.stamp(metadata, ctx, outcome, ())
    return metadata


@pytest.fixture
def renderer(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Install a fake page renderer that records the pages it renders."""
    fake = ModuleType(RENDERER)
    fake.rendered = []  # type: ignore[attr-defined]
    fake.available = lambda: True  # type: ignore[attr-defined]

    def render_page(file: Path, page: int) -> bytes:
        fake.rendered.append((file, page))  # type: ignore[attr-defined]
        return f"PNG {page}".encode()

    fake.render_page = render_page  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, RENDERER, fake)
    return fake


# ── No router ────────────────────────────────────────────────────────────


class _Untouchable(list):
    """Evidence that fails the test when the rule reads it."""

    def __iter__(self):
        raise AssertionError("the rule read a page with no router")


def test_no_router_returns_an_empty_outcome_without_reading_a_page() -> None:
    ctx = _ctx(_Untouchable([_page(1)]), None)

    outcome = RULE.run(ctx)

    assert outcome == RuleOutcome()
    assert _stamp(ctx, outcome) == {}, "no router stamps nothing"


def test_the_registered_rule_with_no_judge_changes_no_plan(effective_settings: Any) -> None:
    evidence = [_page(1), _page(2)]
    settings = effective_settings(ocr_maths_routing_enabled=False)

    plan = run_rules(Path("doc.pdf"), evidence, set(), settings, None)

    run = next(run for run in plan.runs if run.name == "document_router")
    assert run.outcome == RuleOutcome()
    assert plan.direct == frozenset()


# ── Which pages are judged ───────────────────────────────────────────────


def test_only_unflagged_text_pages_are_judged_in_page_order() -> None:
    judge = FakeJudge()
    evidence = [_page(3), _page(1), _page(2, "  \n"), _page(4, ""), _page(5)]

    RULE.run(_ctx(evidence, judge, flagged=frozenset({5})))

    assert [text for text, _ in judge.calls] == ["page 1", "page 3"]


def test_flagged_pages_are_never_judged() -> None:
    """Scenario "Flagged pages are not judged": 3 flagged, 10 unflagged."""
    judge = FakeJudge()
    evidence = [_page(n) for n in range(1, 14)]

    RULE.run(_ctx(evidence, judge, flagged=frozenset({1, 2, 3})))

    assert [text for text, _ in judge.calls] == [f"page {n}" for n in range(4, 14)]


def test_claimed_pages_are_never_judged() -> None:
    """Scenario "Pages of earlier rules are not judged"."""
    judge = FakeJudge()
    evidence = [_page(n) for n in range(1, 5)]

    RULE.run(_ctx(evidence, judge, claimed=frozenset({2, 4})))

    assert [text for text, _ in judge.calls] == ["page 1", "page 3"]


def test_text_is_cut_to_the_character_limit() -> None:
    judge = FakeJudge(max_chars=5)

    RULE.run(_ctx([_page(1, "abcdefghij")], judge))

    assert judge.calls == [("abcde", None)]


def test_a_text_router_sends_no_image() -> None:
    judge = FakeJudge(images=False)

    RULE.run(_ctx([_page(1)], judge))

    assert judge.calls == [("page 1", None)]


def test_an_image_router_sends_each_page_image(renderer: ModuleType) -> None:
    judge = FakeJudge(images=True)

    RULE.run(_ctx([_page(1), _page(2)], judge))

    assert judge.calls == [("page 1", b"PNG 1"), ("page 2", b"PNG 2")]
    assert renderer.rendered == [(Path("doc.pdf"), 1), (Path("doc.pdf"), 2)]


def test_requests_go_one_at_a_time() -> None:
    """Each request ends before the next starts (ADR-074 rule 5)."""
    active: list[int] = []
    peak: list[int] = []

    class Serial(FakeJudge):
        def judge(self, text: str, image: bytes | None) -> float | None:
            active.append(1)
            peak.append(len(active))
            active.pop()
            return super().judge(text, image)

    RULE.run(_ctx([_page(n) for n in range(1, 6)], Serial()))

    assert peak == [1] * 5


# ── Verdicts and counts ──────────────────────────────────────────────────


def test_below_the_threshold_is_added_and_at_or_above_is_kept() -> None:
    """Scenario "Below the threshold": P(yes) 0.05 under threshold 0.17 goes to OCR."""
    judge = FakeJudge({"page 1": 0.05, "page 2": 0.17, "page 3": 0.9}, threshold=0.17)
    ctx = _ctx([_page(1), _page(2), _page(3)], judge)

    outcome = RULE.run(ctx)

    assert outcome.add == frozenset({1})
    assert outcome.drop == frozenset() and outcome.direct == frozenset()
    assert _stamp(ctx, outcome) == {
        "router_pages_judged": 3,
        "router_pages_accepted": 2,
        "router_pages_rejected": 1,
        "router_pages_unjudged": 0,
        "router_status": "ok",
    }


def test_the_counts_of_the_spec_scenario() -> None:
    """Scenario "Counts stamped": 44 judged, 40 rejected, 4 accepted."""
    answers = {f"page {n}": (0.9 if n <= 4 else 0.01) for n in range(1, 45)}
    judge = FakeJudge(answers)
    ctx = _ctx([_page(n) for n in range(1, 45)], judge)

    outcome = RULE.run(ctx)

    assert len(outcome.add) == 40
    stamped = _stamp(ctx, outcome)
    assert [stamped[key] for key in STAMP_KEYS[:4]] == [44, 4, 40, 0]


def test_a_failed_request_keeps_the_page_and_counts_it_unjudged() -> None:
    judge = FakeJudge({"page 1": None, "page 2": 0.01})
    ctx = _ctx([_page(1), _page(2), _page(3)], judge)

    outcome = RULE.run(ctx)

    assert outcome.add == frozenset({2})
    stamped = _stamp(ctx, outcome)
    assert [stamped[key] for key in STAMP_KEYS] == [2, 1, 1, 1, "ok"]


def test_a_page_whose_image_fails_to_render_counts_unjudged(
    renderer: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(file: Path, page: int) -> bytes:
        raise RuntimeError("render failed")

    monkeypatch.setattr(renderer, "render_page", broken)
    judge = FakeJudge(images=True)
    ctx = _ctx([_page(1)], judge)

    outcome = RULE.run(ctx)

    assert judge.calls == [] and outcome.add == frozenset()
    assert _stamp(ctx, outcome)["router_pages_unjudged"] == 1


def test_every_request_failing_gives_request_failed() -> None:
    judge = FakeJudge(default=None)
    ctx = _ctx([_page(1), _page(2)], judge)

    outcome = RULE.run(ctx)

    assert outcome.add == frozenset()
    stamped = _stamp(ctx, outcome)
    assert [stamped[key] for key in STAMP_KEYS] == [0, 0, 0, 2, "request-failed"]


def test_no_candidate_page_stamps_zero_counts() -> None:
    judge = FakeJudge()
    ctx = _ctx([_page(1, "")], judge, flagged=frozenset({1}))

    outcome = RULE.run(ctx)

    assert judge.calls == []
    assert [_stamp(ctx, outcome)[key] for key in STAMP_KEYS] == [0, 0, 0, 0, "ok"]


# ── Degradation (task 3.4) ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "reason", [reason for reason in REASONS if reason not in ("renderer-missing", "request-failed")]
)
def test_a_judge_that_cannot_run_is_never_called(reason: str) -> None:
    judge = FakeJudge({"page 1": 0.0}, status=reason)
    ctx = _ctx(_Untouchable([_page(1)]), judge)

    outcome = RULE.run(ctx)

    assert judge.calls == []
    assert outcome.add == frozenset() and outcome.drop == frozenset()
    assert _stamp(ctx, outcome) == {
        "router_pages_judged": 0,
        "router_pages_accepted": 0,
        "router_pages_rejected": 0,
        "router_pages_unjudged": 0,
        "router_status": reason,
    }


def test_needs_opt_in_sends_nothing() -> None:
    """A hosted router without the opt-in: the rule never asks the judge."""
    judge = FakeJudge({"page 1": 0.0}, status="needs-opt-in")
    judge.hosted = True

    RULE.run(_ctx([_page(1), _page(2)], judge))

    assert judge.calls == []


def test_an_image_router_with_no_renderer_gives_renderer_missing(
    renderer: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(renderer, "available", lambda: False)
    judge = FakeJudge({"page 1": 0.0}, images=True)
    ctx = _ctx([_page(1)], judge)

    outcome = RULE.run(ctx)

    assert judge.calls == [] and renderer.rendered == []
    assert outcome.add == frozenset()
    assert _stamp(ctx, outcome)["router_status"] == "renderer-missing"


def test_an_image_router_with_no_renderer_package_gives_renderer_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, RENDERER, None)  # the import raises ImportError
    judge = FakeJudge({"page 1": 0.0}, images=True)
    ctx = _ctx([_page(1)], judge)

    outcome = RULE.run(ctx)

    assert judge.calls == []
    assert _stamp(ctx, outcome)["router_status"] == "renderer-missing"


def test_degrade_sends_unread_added_pages_to_the_local_tier_with_one_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    ctx = _ctx([_page(1)], FakeJudge())

    with caplog.at_level(logging.WARNING):
        pages = RULE.degrade(ctx, RuleOutcome(add=frozenset({1, 4})), [1, 4])

    assert pages == [1, 4]
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1 and "doc.pdf" in warnings[0].getMessage()


def test_logs_hold_no_page_text(caplog: pytest.LogCaptureFixture) -> None:
    judge = FakeJudge({"SECRET page text": None})

    with caplog.at_level(logging.DEBUG):
        ctx = _ctx([_page(1, "SECRET page text")], judge)
        RULE.degrade(ctx, RULE.run(ctx), [1])

    assert "SECRET" not in caplog.text


# ── Through the pipeline ─────────────────────────────────────────────────


def test_the_registered_rule_adds_rejected_pages_to_the_direct_set(
    effective_settings: Any,
) -> None:
    """Scenario "Several junk pages stay page by page": 5 of 20 pages rejected."""
    rejected = {2, 5, 9, 14, 20}
    judge = FakeJudge({f"page {n}": 0.01 for n in rejected})
    evidence = [_page(n) for n in range(1, 21)]

    settings = effective_settings(ocr_maths_routing_enabled=False)

    plan = run_rules(Path("doc.pdf"), evidence, set(), settings, None, judge=judge)

    assert plan.direct == frozenset(rejected)
    assert plan.local == ()


def test_the_registration_declares_the_router_facts() -> None:
    facts = registry.describe("document_router")

    assert facts["order"] == 40
    assert (facts["adds_pages"], facts["has_degrade"]) == (True, True)
    assert (facts["drops_pages"], facts["sends_direct"], facts["has_post_check"]) == (
        False,
        False,
        False,
    )


# ── Review finding 2: a hung server does not cost every page ─────────────


def test_three_failed_requests_in_a_row_stop_the_router() -> None:
    judge = FakeJudge(default=None)
    ctx = _ctx([_page(n) for n in range(1, 51)], judge)

    outcome = RULE.run(ctx)

    assert len(judge.calls) == 3
    assert document_router.MAX_FAILED_IN_A_ROW == 3
    stamped = _stamp(ctx, outcome)
    assert [stamped[key] for key in STAMP_KEYS] == [0, 0, 0, 50, "unreachable"]


def test_a_stop_after_judged_pages_keeps_ok_and_counts_the_rest_unjudged() -> None:
    judge = FakeJudge({"page 1": 0.9, "page 2": 0.01}, default=None)
    ctx = _ctx([_page(n) for n in range(1, 11)], judge)

    outcome = RULE.run(ctx)

    assert len(judge.calls) == 5
    assert outcome.add == frozenset({2})
    stamped = _stamp(ctx, outcome)
    assert [stamped[key] for key in STAMP_KEYS] == [2, 1, 1, 8, "ok"]


def test_an_answer_between_failures_resets_the_count() -> None:
    answers = {f"page {n}": None for n in (1, 2, 4, 5, 7, 8)}
    judge = FakeJudge(answers)
    ctx = _ctx([_page(n) for n in range(1, 10)], judge)

    RULE.run(ctx)

    assert len(judge.calls) == 9


def test_pages_whose_image_fails_to_render_do_not_stop_the_router(
    renderer: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(file: Path, page: int) -> bytes:
        if page <= 4:
            raise RuntimeError("render failed")
        return b"PNG"

    monkeypatch.setattr(renderer, "render_page", broken)
    judge = FakeJudge(images=True)
    ctx = _ctx([_page(n) for n in range(1, 7)], judge)

    outcome = RULE.run(ctx)

    assert len(judge.calls) == 2
    assert _stamp(ctx, outcome)["router_pages_unjudged"] == 4


class _BrokenStatusJudge:
    """A judge whose model checks raise an unexpected error when read."""

    images = False
    max_chars = 2000
    threshold = 0.5

    @property
    def status(self) -> str | None:
        raise RuntimeError("unexpected check error")

    def judge(self, text: str, image: bytes | None) -> float | None:
        raise AssertionError("a judge that failed its checks is never asked")


def test_an_error_in_the_checks_degrades_and_does_not_fail_the_file() -> None:
    ctx = _ctx([_page(1), _page(2)], judge=_BrokenStatusJudge())

    outcome = document_router.RULE.run(ctx)

    assert outcome.add == frozenset()
    assert _stamp(ctx, outcome)["router_status"] == document_router.REQUEST_FAILED
