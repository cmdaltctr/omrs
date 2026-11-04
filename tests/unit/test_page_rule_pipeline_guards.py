"""Guards around external page rules (change local-ocr-backends, design D11, review of PR #168).

An external rule never fails the file. These tests cover the paths the first
guard missed: the post-check that a rule returns, a panic (a ``BaseException``
that is not an ``Exception``), and an outcome of the wrong shape. In each case
the file reads, the other rules run, and the rule is switched off with a reason.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from omrs.integrations.part_registry import PartRegistry
from omrs.integrations.pdf.local_ocr import chain
from omrs.integrations.pdf.local_ocr import registry as backends
from omrs.integrations.pdf.local_ocr.base import BackendPage
from omrs.integrations.pdf.page_rules import registry
from omrs.integrations.pdf.page_rules.base import RuleOutcome
from omrs.integrations.pdf.page_rules.pipeline import run_rules

FILE = Path("doc.pdf")
LOGGER = "omrs.integrations.pdf.page_rules.pipeline"


class Panic(BaseException):
    """Stands in for ``pyo3_runtime.PanicException``, a ``BaseException``."""


@pytest.fixture(autouse=True)
def _empty_registries():
    """Run each test on an empty rule registry and a saved backend registry."""
    rules = registry.RULES.snapshot()
    saved_backends = backends.BACKENDS.snapshot()
    registry.RULES.restore(PartRegistry("page rule").snapshot())
    chain.reset_skip_warnings()
    yield
    registry.RULES.restore(rules)
    backends.BACKENDS.restore(saved_backends)
    chain.reset_skip_warnings()


class _Rule:
    """A rule whose ``run`` and ``post_check`` are plain functions."""

    def __init__(self, run: Any, check: Any = None) -> None:
        self._run, self._check, self.calls = run, check, 0

    def run(self, ctx):
        self.calls += 1
        return self._run(ctx)

    def post_check(self, ctx, outcome):
        return self._check


def _add(name: str, rule: Any, order: int, source: str = "acme-dist", **flags: bool) -> None:
    registry.register(name, f"fake.module:{name}", order=order, source=source, **flags)
    registry.RULES.cache[name] = rule


def _settings(**extra: Any) -> SimpleNamespace:
    return SimpleNamespace(reading_part_options={"acme": {"enabled": True}}, **extra)


def _warnings(caplog) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.levelno == logging.WARNING]


# ── Fix 2: the returned post-check ─────────────────────────────────────────


class _GoodBackend:
    def read_pages(self, file, pages, *, settings):
        return [BackendPage(p, "Plenty of good Latin text here", 0.99, "m@1") for p in pages]

    def identity(self, settings):
        return "m@1"


def _raising_check(text: str, facts: Any) -> str | None:
    raise ValueError("buggy external check")


def test_a_raising_external_post_check_keeps_the_local_text(caplog) -> None:
    _add("acme", _Rule(lambda ctx: RuleOutcome(), _raising_check), 40, has_post_check=True)
    backends.BACKENDS.cache["pp-ocrv6-small"] = _GoodBackend()
    settings = _settings(ocr_local_backends=("pp-ocrv6-small",), ocr_local_min_confidence=None)

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        plan = run_rules(FILE, [], {1, 2}, settings, None)
        pages = chain.read_local_pages(
            FILE, [1, 2], settings=settings, post_checks=plan.post_checks()
        )

    assert [(page.page, page.escalates, page.reasons) for page in pages] == [
        (1, False, ()),
        (2, False, ()),
    ]
    assert pages[0].text == "Plenty of good Latin text here"
    assert registry.RULES.off_reason("acme") == "ValueError: buggy external check"
    assert len(_warnings(caplog)) == 1
    assert "acme" in _warnings(caplog)[0].getMessage()


def test_a_built_in_post_check_that_raises_still_reaches_the_caller() -> None:
    rule = _Rule(lambda ctx: RuleOutcome(), _raising_check)
    _add("mine", rule, 40, "built-in", has_post_check=True)
    (check,) = run_rules(FILE, [], {1}, _settings(), None).post_checks()

    with pytest.raises(ValueError, match="buggy external check"):
        check("text", {})


# ── Fix 3: panics and outcomes of the wrong shape ──────────────────────────


def _panic(ctx):
    raise Panic("lock poisoned")


BAD_RUNS = {
    "panic": (_panic, "Panic: lock poisoned"),
    "none": (lambda ctx: None, "TypeError"),
    "list drop": (lambda ctx: RuleOutcome(drop=[1]), "TypeError"),  # type: ignore[arg-type]
    "unflagged drop": (lambda ctx: RuleOutcome(drop=frozenset({5})), "ValueError"),
    "unflagged direct": (lambda ctx: RuleOutcome(direct=frozenset({5})), "ValueError"),
}


@pytest.mark.parametrize("case", sorted(BAD_RUNS))
def test_a_bad_external_rule_is_skipped_and_switched_off(case: str, caplog) -> None:
    run, reason = BAD_RUNS[case]
    first = _Rule(lambda ctx: RuleOutcome(direct=frozenset({1})))
    later = _Rule(lambda ctx: RuleOutcome())
    _add("first", first, 10, "built-in", sends_direct=True)
    _add("acme", _Rule(run), 15)
    _add("later", later, 20, "built-in")

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        plan = run_rules(FILE, [], {1, 2}, _settings(), None)

    assert [run.name for run in plan.runs] == ["first", "later"]
    assert later.calls == 1
    assert plan.dropped == frozenset()
    assert 5 not in plan.dropped | plan.direct
    assert (plan.direct, plan.local) == ({1}, (2,))
    assert registry.RULES.off_reason("acme").startswith(reason)
    assert len(_warnings(caplog)) == 1


def test_a_good_external_outcome_is_kept_as_a_frozen_set() -> None:
    _add("acme", _Rule(lambda ctx: RuleOutcome(drop={2}, direct=frozenset({1}))), 15)  # type: ignore[arg-type]

    plan = run_rules(FILE, [], {1, 2, 3}, _settings(), None)

    assert plan.runs[0].outcome.drop == frozenset({2})
    assert isinstance(plan.runs[0].outcome.drop, frozenset)
    assert (plan.dropped, plan.direct, plan.local) == ({2}, {1}, (3,))
    assert registry.RULES.off_reason("acme") is None


@pytest.mark.parametrize("hook", ["post_check", "degrade", "stamp"])
def test_a_panicking_external_hook_is_skipped_and_switched_off(hook: str, caplog) -> None:
    class Hooks:
        def run(self, ctx):
            return RuleOutcome(direct=frozenset({1}))

        def post_check(self, *args):
            raise Panic("hook panic")

        degrade = stamp = post_check

    _add("acme", Hooks(), 15, sends_direct=True, has_post_check=True, has_degrade=True)
    plan = run_rules(FILE, [], {1}, _settings(), None)

    with caplog.at_level(logging.WARNING, logger=LOGGER):
        if hook == "post_check":
            assert plan.post_checks() == ()
        elif hook == "degrade":
            assert plan.degrade([1]) == []
        else:
            plan.stamp({}, [None])

    assert registry.RULES.off_reason("acme") == "Panic: hook panic"
    assert len(_warnings(caplog)) == 1


@pytest.mark.parametrize("stop", [KeyboardInterrupt, SystemExit])
def test_an_interrupt_from_an_external_rule_is_not_swallowed(stop: type) -> None:
    def run(ctx):
        raise stop()

    _add("acme", _Rule(run), 15)

    with pytest.raises(stop):
        run_rules(FILE, [], {1}, _settings(), None)
    assert registry.RULES.off_reason("acme") is None
