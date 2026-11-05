"""The ``add`` amendment of the page-rule hook (document-reading-routers, task 3.1, D4).

A rule that declares ``adds_pages`` may return ``add``: pages the scan did not
flag that it sends to the OCR engine list. Added pages join the direct set once,
a later drop removes them, and ``claimed`` tells later rules which pages earlier
rules took. Any other use of ``add`` is a bad outcome: a built-in rule fails the
file and a discovered rule is skipped and switched off.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from omrs.integrations.part_registry import PartRegistry
from omrs.integrations.pdf.page_rules import registry
from omrs.integrations.pdf.page_rules.base import RuleContext, RuleOutcome
from omrs.integrations.pdf.page_rules.pipeline import run_rules

FILE = Path("doc.pdf")


def _page(number: int, text: str = "native text") -> SimpleNamespace:
    return SimpleNamespace(page=number, markdown=text, needs_ocr=False)


#: Pages 1 and 2 are flagged by the scan; 3 to 5 have text; page 6 is blank.
EVIDENCE = [_page(1), _page(2), _page(3), _page(4), _page(5), _page(6, "  ")]
FLAGGED = {1, 2}


@dataclass
class FakeRule:
    """A page rule with fixed answers that records the context it saw."""

    name: str
    drop: frozenset[int] = frozenset()
    direct: frozenset[int] = frozenset()
    add: frozenset[int] = frozenset()
    seen: list[RuleContext] = field(default_factory=list)

    def run(self, ctx: RuleContext) -> RuleOutcome:
        self.seen.append(ctx)
        return RuleOutcome(drop=self.drop, direct=self.direct, add=self.add)

    def degrade(self, ctx: RuleContext, outcome: RuleOutcome, unread: list[int]) -> list[int]:
        return list(unread)


@pytest.fixture(autouse=True)
def _empty_registry():
    saved = registry.RULES.snapshot()
    registry.RULES.restore(PartRegistry("page rule").snapshot())
    yield
    registry.RULES.restore(saved)


def _add(rule: FakeRule, order: int, *, source: str = "built-in", **flags: bool) -> FakeRule:
    registry.register(rule.name, f"fake.module:{rule.name}", order=order, source=source, **flags)
    registry.RULES.cache[rule.name] = rule
    return rule


def _run(settings: Any = None, judge: Any = None, flagged=FLAGGED):
    return run_rules(FILE, EVIDENCE, flagged, settings, None, judge=judge)


def _enabled(*names: str) -> SimpleNamespace:
    return SimpleNamespace(reading_part_options={name: {"enabled": True} for name in names})


# ── The new fields default to nothing ──────────────────────────────────────


def test_the_new_fields_default_to_empty() -> None:
    assert RuleOutcome().add == frozenset()
    ctx = RuleContext(FILE, [], frozenset(), frozenset(), None, None)
    assert ctx.claimed == frozenset()
    assert ctx.judge is None


def test_the_registration_carries_adds_pages() -> None:
    _add(FakeRule("adder"), 40, adds_pages=True)
    _add(FakeRule("plain"), 50)

    assert registry.describe("adder")["adds_pages"] is True
    assert registry.describe("plain")["adds_pages"] is False


def test_the_judge_reaches_every_rule_context() -> None:
    rule = _add(FakeRule("first"), 10)
    judge = object()

    _run(judge=judge)

    assert rule.seen[0].judge is judge
    assert rule.seen[0].claimed == frozenset()


# ── An added page joins the direct set once ────────────────────────────────


def test_an_added_page_joins_the_direct_set_and_leaves_the_local_set() -> None:
    _add(FakeRule("adder", add=frozenset({3})), 40, adds_pages=True)

    plan = _run()

    assert plan.direct == {3}
    assert plan.local == (1, 2), "added pages never reach the local tier"
    assert plan.runs[0].direct == {3}


def test_two_adding_rules_send_their_pages_once_each() -> None:
    _add(FakeRule("first", add=frozenset({3})), 30, adds_pages=True)
    _add(FakeRule("second", add=frozenset({4})), 40, adds_pages=True)

    plan = _run()

    assert plan.direct == {3, 4}
    assert [run.direct for run in plan.runs] == [{3}, {4}]


def test_an_added_page_and_a_direct_page_share_one_direct_set() -> None:
    _add(FakeRule("maths", direct=frozenset({1})), 20, sends_direct=True)
    _add(FakeRule("adder", add=frozenset({3})), 40, adds_pages=True)

    plan = _run()

    assert plan.direct == {1, 3}
    assert plan.local == (2,)


def test_a_later_drop_removes_an_added_page() -> None:
    _add(FakeRule("adder", add=frozenset({3, 4})), 40, adds_pages=True)
    _add(FakeRule("dropper", drop=frozenset({3})), 50, drops_pages=True)

    plan = _run()

    assert plan.direct == {4}, "the final direct set loses every dropped page"
    assert plan.dropped == {3}
    assert plan.local == (1, 2)


def test_degrade_goes_to_the_rule_that_added_the_page() -> None:
    adder = _add(FakeRule("adder", add=frozenset({3})), 40, adds_pages=True, has_degrade=True)

    plan = _run()

    assert plan.degrade([3]) == [3]
    assert adder.seen, "the adder ran"


# ── The claimed set ────────────────────────────────────────────────────────


def test_claimed_holds_earlier_drops_direct_and_added_pages() -> None:
    blank = _add(FakeRule("blank", drop=frozenset({1})), 10, drops_pages=True)
    maths = _add(FakeRule("maths", direct=frozenset({2})), 20, sends_direct=True)
    adder = _add(FakeRule("adder", add=frozenset({3})), 30, adds_pages=True)
    last = _add(FakeRule("last"), 40)

    _run()

    assert blank.seen[0].claimed == frozenset()
    assert maths.seen[0].claimed == {1}
    assert adder.seen[0].claimed == {1, 2}
    assert last.seen[0].claimed == {1, 2, 3}


# ── A bad outcome ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(frozenset({1}), id="a flagged page"),
        pytest.param(frozenset({99}), id="a page not in the scan"),
        pytest.param(frozenset({6}), id="a page with no text"),
    ],
)
def test_a_stray_added_page_fails_a_built_in_rule(bad) -> None:
    _add(FakeRule("adder", add=bad), 40, adds_pages=True)

    with pytest.raises(ValueError, match="add"):
        _run()


def test_an_added_page_that_an_earlier_rule_claimed_fails_a_built_in_rule() -> None:
    _add(FakeRule("first", add=frozenset({3})), 30, adds_pages=True)
    _add(FakeRule("second", add=frozenset({3})), 40, adds_pages=True)

    with pytest.raises(ValueError, match="claimed"):
        _run()


def test_a_rule_without_adds_pages_that_returns_add_fails_a_built_in_rule() -> None:
    _add(FakeRule("plain", add=frozenset({3})), 40)

    with pytest.raises(ValueError, match="adds_pages"):
        _run()


def test_a_discovered_rule_without_adds_pages_is_skipped_and_switched_off(caplog) -> None:
    rule = _add(FakeRule("acme", add=frozenset({3})), 40, source="acme-dist")
    other = _add(FakeRule("other", direct=frozenset({1})), 20, sends_direct=True)

    with caplog.at_level(logging.WARNING, logger="omrs.integrations.pdf.page_rules.pipeline"):
        plan = _run(_enabled("acme"))

    assert plan.direct == {1}, "the other rule still ran, the bad one added nothing"
    assert other.seen and rule.seen
    assert registry.RULES.off_reason("acme") is not None
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


def test_a_discovered_rule_with_a_stray_added_page_is_skipped(caplog) -> None:
    _add(FakeRule("acme", add=frozenset({1})), 40, source="acme-dist", adds_pages=True)

    with caplog.at_level(logging.WARNING, logger="omrs.integrations.pdf.page_rules.pipeline"):
        plan = _run(_enabled("acme"))

    assert plan.direct == frozenset()
    assert registry.RULES.off_reason("acme") is not None


def test_a_discovered_rule_may_drop_a_page_that_an_earlier_rule_added() -> None:
    _add(FakeRule("adder", add=frozenset({3})), 40, adds_pages=True)
    _add(FakeRule("acme", drop=frozenset({3})), 50, source="acme-dist", drops_pages=True)

    plan = _run(_enabled("acme"))

    assert plan.direct == frozenset()
    assert plan.dropped == {3}
    assert registry.RULES.off_reason("acme") is None, "a valid later drop is not a bad outcome"
