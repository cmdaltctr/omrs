"""Run the page rules of one PDF in order (change local-ocr-backends, design D5).

:func:`run_rules` applies four fixed semantics, which reproduce the hand-wired
routing the rules replace:

1. A page dropped by an earlier rule leaves the ``routed`` set of every later rule.
2. A rule's ``direct`` set loses the pages earlier rules dropped.
3. ``direct`` is the union of every rule's reduced ``direct`` set, and the local
   tier reads ``routed - direct``.
4. :meth:`RoutingPlan.degrade` gives a rule only the pages it was first to send
   direct.

A built-in rule that raises fails the file, as before. A rule from another
distribution that fails to load or raises is skipped for the file, logs one
warning and is switched off in the registry with the reason (design D11). A
rule from another distribution runs only while it is on and its
``reading_part_options`` entry holds ``"enabled": true`` (design D12).
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import registry
from .base import PostCheck, RuleContext, RuleOutcome

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuleRun:
    """One rule's run on one PDF.

    Attributes:
        name: Rule name.
        facts: The rule's registered facts (order and hook flags).
        rule: The loaded rule object.
        ctx: The context the rule ran with.
        outcome: What the rule returned.
        direct: ``outcome.direct`` without the pages earlier rules dropped.
    """

    name: str
    facts: dict[str, Any]
    rule: Any
    ctx: RuleContext
    outcome: RuleOutcome
    direct: frozenset[int]


@dataclass(frozen=True)
class RoutingPlan:
    """The combined decisions of every rule for one PDF.

    Attributes:
        runs: One entry per rule that ran, in rule order.
        dropped: Pages any rule dropped.
        direct: Pages sent to the OCR engine list without the local tier.
        local: Sorted pages the local tier reads.
    """

    runs: tuple[RuleRun, ...]
    dropped: frozenset[int]
    direct: frozenset[int]
    local: tuple[int, ...]

    def post_checks(self) -> tuple[PostCheck, ...]:
        """Return the post-checks of the rules that declare one, in rule order."""
        checks = (
            run.rule.post_check(run.ctx, run.outcome)
            for run in self.runs
            if run.facts["has_post_check"]
        )
        return tuple(check for check in checks if check is not None)

    def degrade(self, unread: Collection[int]) -> list[int]:
        """Return the direct pages no engine read that must go to the local tier.

        Each page goes to the degrade hook of the first rule that sent it direct,
        and to no other rule. A rule with no degrade hook still claims its pages.

        Args:
            unread: Direct pages the OCR engine list did not read.

        Returns:
            The sorted pages the hooks returned.
        """
        unread = set(unread)
        claimed: set[int] = set()
        pages: set[int] = set()
        for run in self.runs:
            mine = sorted((run.direct - claimed) & unread)
            claimed |= run.direct
            if mine and run.facts["has_degrade"]:
                pages.update(run.rule.degrade(run.ctx, run.outcome, mine))
        return sorted(pages)

    def stamp(self, metadata: dict[str, Any], escalated: Iterable[Any]) -> None:
        """Let each rule stamp its diagnostic count, in rule order.

        Args:
            metadata: Document metadata to stamp.
            escalated: The local results of the escalated pages (``None`` for a
                page that had none). It is read once per rule.
        """
        results = tuple(escalated)
        for run in self.runs:
            stamp = getattr(run.rule, "stamp", None)
            if stamp is not None:
                stamp(metadata, run.ctx, run.outcome, results)


def _waits(name: str, facts: dict[str, Any], settings: Any) -> bool:
    """Return True for a rule from another distribution that is off or not enabled."""
    if facts["source"] == registry.SOURCE_BUILT_IN:
        return False
    if registry.RULES.off_reason(name) is not None:
        return True
    options = (getattr(settings, "reading_part_options", None) or {}).get(name, {})
    return options.get("enabled") is not True


def _run_one(name: str, facts: dict[str, Any], ctx: RuleContext) -> tuple[Any, RuleOutcome] | None:
    """Load and run one rule; return ``None`` when an external rule failed."""
    if facts["source"] == registry.SOURCE_BUILT_IN:
        rule = registry.RULES.get(name)
        return rule, rule.run(ctx)
    try:
        rule = registry.RULES.get(name)
        return rule, rule.run(ctx)
    except Exception as exc:  # noqa: BLE001 - an external rule never fails the file
        reason = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "Page rule %r from %s failed on %s and was skipped (%s).",
            name,
            facts["source"],
            getattr(ctx.file, "name", ctx.file),
            reason,
        )
        registry.RULES.switch_off(name, reason)
        return None


def run_rules(
    file: Path, evidence: Sequence[Any], flagged: Collection[int], settings: Any, routes: Any
) -> RoutingPlan:
    """Run every registered page rule on one PDF, in ascending order.

    Args:
        file: Path to the PDF file.
        evidence: The page scan, one ``PageEvidence`` per page.
        flagged: Pages the scan flagged as needing OCR.
        settings: The injected settings.
        routes: The injected ``OcrRoutes``.

    Returns:
        The combined plan.

    Raises:
        Exception: Whatever a built-in rule raises.
    """
    flagged = frozenset(flagged)
    dropped: frozenset[int] = frozenset()
    direct: frozenset[int] = frozenset()
    runs: list[RuleRun] = []
    for name, facts in registry.ordered():
        if _waits(name, facts, settings):
            continue
        ctx = RuleContext(file, evidence, flagged, flagged - dropped, settings, routes)
        ran = _run_one(name, facts, ctx)
        if ran is None:
            continue
        rule, outcome = ran
        reduced = frozenset(outcome.direct) - dropped
        runs.append(RuleRun(name, facts, rule, ctx, outcome, reduced))
        dropped |= outcome.drop
        direct |= reduced
    local = tuple(sorted(flagged - dropped - direct))
    return RoutingPlan(tuple(runs), dropped, direct, local)
