"""The page-rule pipeline with fake rules (change local-ocr-backends, task 3.1, design D5).

Each test empties the page-rule registry, registers fake rules, and runs the
pipeline. The four fixed semantics of D5 each have a test: drops leave later
``routed`` sets, a rule's ``direct`` set loses earlier drops, ``direct`` is the
union, and degrade goes to the first claimant only. Post-checks come back in
rule order. A built-in rule that raises fails the file as before; an external
rule that raises is skipped for the file, logs one warning and is switched off.
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


@dataclass
class FakeRule:
    """A page rule with fixed answers that records every call."""

    name: str
    log: list[tuple[str, str, Any]]
    drop: frozenset[int] = frozenset()
    direct: frozenset[int] = frozenset()
    check: Any = None
    degrade_answer: list[int] | None = None
    error: Exception | None = None
    hook_errors: dict[str, Exception] = field(default_factory=dict)
    seen: list[RuleContext] = field(default_factory=list)

    def run(self, ctx: RuleContext) -> RuleOutcome:
        self.seen.append(ctx)
        self.log.append(("run", self.name, None))
        if self.error is not None:
            raise self.error
        return RuleOutcome(drop=self.drop, direct=self.direct, state=self.name)

    def post_check(self, ctx: RuleContext, outcome: RuleOutcome) -> Any:
        self.log.append(("post_check", self.name, None))
        if "post_check" in self.hook_errors:
            raise self.hook_errors["post_check"]
        return self.check

    def degrade(self, ctx: RuleContext, outcome: RuleOutcome, unread: list[int]) -> list[int]:
        self.log.append(("degrade", self.name, list(unread)))
        if "degrade" in self.hook_errors:
            raise self.hook_errors["degrade"]
        return list(unread) if self.degrade_answer is None else self.degrade_answer

    def stamp(self, metadata: dict, ctx: RuleContext, outcome: RuleOutcome, escalated) -> None:
        self.log.append(("stamp", self.name, outcome.state))
        if "stamp" in self.hook_errors:
            raise self.hook_errors["stamp"]
        metadata[f"stamp_{self.name}"] = len(list(escalated))


@pytest.fixture(autouse=True)
def _empty_registry():
    """Run each test on an empty page-rule registry, then put the built-ins back."""
    saved = registry.RULES.snapshot()
    registry.RULES.restore(PartRegistry("page rule").snapshot())
    yield
    registry.RULES.restore(saved)


@pytest.fixture
def log() -> list[tuple[str, str, Any]]:
    return []


def _add(rule: FakeRule, order: int, *, source: str = "built-in", **flags: bool) -> FakeRule:
    """Register *rule* under its name and put the object in the registry cache."""
    registry.register(rule.name, f"fake.module:{rule.name}", order=order, source=source, **flags)
    registry.RULES.cache[rule.name] = rule
    return rule


def _run(flagged: set[int], settings: Any = None):
    return run_rules(FILE, [], flagged, settings=settings, routes=None)


def _enabled(*names: str) -> SimpleNamespace:
    """Settings that switch on the named external rules (design D12)."""
    return SimpleNamespace(reading_part_options={name: {"enabled": True} for name in names})


def test_rules_run_in_ascending_order_whatever_the_registration_order(log):
    _add(FakeRule("third", log), 30)
    _add(FakeRule("first", log), 10)
    _add(FakeRule("second", log), 20)

    _run({1})

    assert [name for kind, name, _ in log if kind == "run"] == ["first", "second", "third"]


def test_a_dropped_page_leaves_the_routed_set_of_every_later_rule(log):
    first = _add(FakeRule("first", log, drop=frozenset({2})), 10, drops_pages=True)
    second = _add(FakeRule("second", log), 20)
    third = _add(FakeRule("third", log, drop=frozenset({3})), 30, drops_pages=True)
    fourth = _add(FakeRule("fourth", log), 40)

    plan = _run({1, 2, 3})

    assert first.seen[0].routed == {1, 2, 3}
    assert second.seen[0].routed == {1, 3}
    assert third.seen[0].routed == {1, 3}
    assert fourth.seen[0].routed == {1}
    assert all(rule.seen[0].flagged == {1, 2, 3} for rule in (first, second, third, fourth))
    assert plan.dropped == {2, 3}
    assert plan.local == (1,)


def test_a_direct_set_loses_the_pages_earlier_rules_dropped(log):
    """Maths detects on every page, then loses the blank ones (D5 semantic 2)."""
    _add(FakeRule("blank", log, drop=frozenset({2})), 10, drops_pages=True)
    maths = _add(FakeRule("maths", log, direct=frozenset({2, 4})), 20, sends_direct=True)

    plan = _run({1, 2})

    assert plan.direct == {4}
    assert plan.local == (1,)
    # The rule's own outcome keeps what it found, for its stamp.
    assert plan.runs[1].outcome.direct == {2, 4}
    assert plan.runs[1].rule is maths


def test_direct_is_the_union_and_the_local_tier_reads_the_rest(log):
    _add(FakeRule("a", log, direct=frozenset({1})), 10, sends_direct=True)
    _add(FakeRule("b", log, direct=frozenset({1, 3})), 20, sends_direct=True)

    plan = _run({1, 2, 3, 5})

    assert plan.direct == {1, 3}
    assert plan.local == (2, 5)


def test_degrade_goes_to_the_first_claimant_only(log):
    _add(FakeRule("a", log, direct=frozenset({1, 3})), 10, sends_direct=True, has_degrade=True)
    _add(FakeRule("b", log, direct=frozenset({1, 2})), 20, sends_direct=True, has_degrade=True)

    plan = _run({1, 2, 3})
    pages = plan.degrade([1, 2, 3])

    assert [entry for entry in log if entry[0] == "degrade"] == [
        ("degrade", "a", [1, 3]),
        ("degrade", "b", [2]),
    ]
    assert pages == [1, 2, 3]


def test_a_rule_without_degrade_still_claims_its_pages_first(log):
    """Maths claims first: the later degrade hook never sees a maths page."""
    _add(FakeRule("maths", log, direct=frozenset({4})), 20, sends_direct=True)
    _add(FakeRule("script", log, direct=frozenset({4, 5})), 30, sends_direct=True, has_degrade=True)

    plan = _run({4, 5})

    assert plan.degrade([4, 5]) == [5]
    assert [entry for entry in log if entry[0] == "degrade"] == [("degrade", "script", [5])]


def test_degrade_skips_read_pages_and_calls_no_hook_with_nothing_to_degrade(log):
    _add(FakeRule("a", log, direct=frozenset({1})), 10, sends_direct=True, has_degrade=True)
    _add(FakeRule("b", log, direct=frozenset({2})), 20, sends_direct=True, has_degrade=True)

    plan = _run({1, 2})

    assert plan.degrade([2]) == [2]
    assert [entry for entry in log if entry[0] == "degrade"] == [("degrade", "b", [2])]


def test_the_hook_decides_which_pages_go_to_the_local_tier(log):
    hook = FakeRule("a", log, direct=frozenset({1, 2}), degrade_answer=[2])
    _add(hook, 10, sends_direct=True, has_degrade=True)

    assert _run({1, 2}).degrade([1, 2]) == [2]


def _check_a(text: str, facts: Any) -> str | None:
    return "reason_a"


def _check_b(text: str, facts: Any) -> str | None:
    return "reason_b"


def test_post_checks_come_back_in_rule_order_and_only_from_declared_rules(log):
    _add(FakeRule("late", log, check=_check_b), 30, has_post_check=True)
    _add(FakeRule("none", log, check=None), 20, has_post_check=True)
    _add(FakeRule("early", log, check=_check_a), 10, has_post_check=True)
    _add(FakeRule("undeclared", log, check=_check_a), 40)

    plan = _run({1})

    assert plan.post_checks() == (_check_a, _check_b)
    assert ("post_check", "undeclared", None) not in log


def test_stamps_run_in_rule_order(log):
    _add(FakeRule("b", log), 20)
    _add(FakeRule("a", log), 10)
    metadata: dict = {}

    _run({1}).stamp(metadata, [None, None])

    assert [entry for entry in log if entry[0] == "stamp"] == [
        ("stamp", "a", "a"),
        ("stamp", "b", "b"),
    ]
    assert list(metadata) == ["stamp_a", "stamp_b"]
    assert metadata == {"stamp_a": 2, "stamp_b": 2}


def test_a_built_in_rule_that_raises_reaches_the_caller(log):
    _add(FakeRule("broken", log, error=ValueError("boom")), 10)
    _add(FakeRule("later", log), 20)

    with pytest.raises(ValueError, match="boom"):
        _run({1})
    assert registry.RULES.off_reason("broken") is None


def test_an_external_rule_that_raises_is_skipped_warned_and_switched_off(log, caplog):
    _add(FakeRule("first", log, direct=frozenset({1})), 10, sends_direct=True)
    _add(FakeRule("acme", log, error=ValueError("boom"), drop=frozenset({2})), 15, source="acme")
    later = _add(FakeRule("later", log, direct=frozenset({3})), 20, sends_direct=True)

    with caplog.at_level(logging.WARNING, logger="omrs.integrations.pdf.page_rules.pipeline"):
        plan = _run({1, 2, 3}, _enabled("acme"))

    assert [name for kind, name, _ in log if kind == "run"] == ["first", "acme", "later"]
    assert later.seen[0].routed == {1, 2, 3}
    assert plan.direct == {1, 3}
    assert plan.local == (2,)
    assert [run.name for run in plan.runs] == ["first", "later"]
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "acme" in warnings[0].getMessage()
    assert registry.RULES.off_reason("acme") == "ValueError: boom"


def test_an_external_rule_that_cannot_be_imported_is_skipped_too(log, caplog):
    registry.register("missing", "omrs_no_such_module:RULE", order=10, source="acme")
    _add(FakeRule("later", log), 20)

    with caplog.at_level(logging.WARNING, logger="omrs.integrations.pdf.page_rules.pipeline"):
        plan = _run({1}, _enabled("missing"))

    assert [run.name for run in plan.runs] == ["later"]
    assert registry.RULES.off_reason("missing").startswith("ImportError")


def _hook_failure_plan(log, hook: str, source: str, **flags: bool):
    """Plan with a working built-in rule and a rule named ``acme`` whose *hook* raises."""
    _add(
        FakeRule("first", log, direct=frozenset({1}), check=_check_a),
        10,
        sends_direct=True,
        has_post_check=True,
        has_degrade=True,
    )
    acme = FakeRule(
        "acme",
        log,
        direct=frozenset({2}),
        check=_check_b,
        hook_errors={hook: ValueError("boom")},
    )
    _add(acme, 20, source=source, sends_direct=True, **flags)
    return _run({1, 2}, _enabled("acme"))


def _warnings(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.levelno == logging.WARNING]


def test_an_external_rule_whose_post_check_raises_adds_no_reason(log, caplog):
    plan = _hook_failure_plan(log, "post_check", "acme", has_post_check=True)

    with caplog.at_level(logging.WARNING, logger="omrs.integrations.pdf.page_rules.pipeline"):
        checks = plan.post_checks()

    assert checks == (_check_a,)
    assert len(_warnings(caplog)) == 1
    assert "acme" in _warnings(caplog)[0].getMessage()
    assert registry.RULES.off_reason("acme") == "ValueError: boom"


def test_an_external_rule_whose_degrade_raises_degrades_no_page(log, caplog):
    plan = _hook_failure_plan(log, "degrade", "acme", has_degrade=True)

    with caplog.at_level(logging.WARNING, logger="omrs.integrations.pdf.page_rules.pipeline"):
        pages = plan.degrade([1, 2])

    assert pages == [1]
    assert len(_warnings(caplog)) == 1
    assert "acme" in _warnings(caplog)[0].getMessage()
    assert registry.RULES.off_reason("acme") == "ValueError: boom"


def test_an_external_rule_whose_stamp_raises_writes_no_key(log, caplog):
    plan = _hook_failure_plan(log, "stamp", "acme")
    metadata: dict = {}

    with caplog.at_level(logging.WARNING, logger="omrs.integrations.pdf.page_rules.pipeline"):
        plan.stamp(metadata, [None])

    assert metadata == {"stamp_first": 1}
    assert len(_warnings(caplog)) == 1
    assert "acme" in _warnings(caplog)[0].getMessage()
    assert registry.RULES.off_reason("acme") == "ValueError: boom"


@pytest.mark.parametrize("hook", ["post_check", "degrade", "stamp"])
def test_a_built_in_rule_whose_hook_raises_reaches_the_caller(log, hook):
    _add(
        FakeRule("broken", log, direct=frozenset({1}), hook_errors={hook: ValueError("boom")}),
        10,
        sends_direct=True,
        has_post_check=True,
        has_degrade=True,
    )
    plan = _run({1})

    with pytest.raises(ValueError, match="boom"):
        if hook == "post_check":
            plan.post_checks()
        elif hook == "degrade":
            plan.degrade([1])
        else:
            plan.stamp({}, [None])
    assert registry.RULES.off_reason("broken") is None
