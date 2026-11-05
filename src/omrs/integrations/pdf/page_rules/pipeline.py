"""Run the page rules of one PDF in order (change local-ocr-backends, design D5).

:func:`run_rules` applies four fixed semantics, which reproduce the hand-wired
routing the rules replace:

1. A page dropped by an earlier rule leaves the ``routed`` set of every later rule.
2. A rule's ``direct`` set loses the pages earlier rules dropped.
3. ``direct`` is the union of every rule's reduced ``direct`` set and added
   pages, minus every dropped page, and the local tier reads ``routed - direct``.
4. :meth:`RoutingPlan.degrade` gives a rule only the pages it was first to send
   direct.

A built-in rule that raises fails the file, as before. A rule from another
distribution that fails to load or raises in ``run``, ``post_check``,
``degrade`` or ``stamp`` is skipped for the file, logs one warning and is
switched off in the registry with the reason (design D11). A failing
``post_check`` adds no reason, a failing ``degrade`` degrades no page and a
failing ``stamp`` writes no key. The same holds for the check that
``post_check`` returns, for a panic (a ``BaseException`` that is not an
``Exception``), and for a ``run`` outcome that is not a ``RuleOutcome`` or that
drops or sends direct a page that is not routed. A rule from another
distribution runs only while it is on and its
``reading_part_options`` entry holds ``"enabled": true`` (design D12).
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable, Collection, Iterable, Sequence
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
        """Return the post-checks of the rules that declare one, in rule order.

        The check of an external rule comes back wrapped by :func:`_guarded_check`.
        """
        checks: list[PostCheck] = []
        for run in self.runs:
            if not run.facts["has_post_check"]:
                continue
            check = _guarded(
                run, "post_check", lambda run=run: run.rule.post_check(run.ctx, run.outcome)
            )
            if check is not None:
                checks.append(check if _built_in(run.facts) else _guarded_check(run, check))
        return tuple(checks)

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
                pages.update(
                    _guarded(
                        run,
                        "degrade",
                        lambda run=run, mine=mine: run.rule.degrade(run.ctx, run.outcome, mine),
                    )
                    or ()
                )
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
                _guarded(
                    run,
                    "stamp",
                    lambda run=run, stamp=stamp: stamp(metadata, run.ctx, run.outcome, results),
                )


def _built_in(facts: dict[str, Any]) -> bool:
    return facts["source"] == registry.SOURCE_BUILT_IN


def _skip(name: str, source: str, ctx: RuleContext, where: str, exc: BaseException) -> None:
    """Log one warning and switch an external rule off with the reason."""
    reason = f"{type(exc).__name__}: {exc}"
    logger.warning(
        "Page rule %r from %s failed %s on %s and was skipped (%s).",
        name,
        source,
        where,
        getattr(ctx.file, "name", ctx.file),
        reason,
    )
    registry.RULES.switch_off(name, reason)


def _guarded(run: RuleRun, hook: str, call: Callable[[], Any]) -> Any:
    """Call a rule hook; an external rule that raises is skipped and returns ``None``.

    A panic (a ``BaseException`` that is not an ``Exception``) counts as a raise.
    ``KeyboardInterrupt`` and ``SystemExit`` always reach the caller.
    """
    if _built_in(run.facts):
        return call()
    try:
        return call()
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:  # noqa: BLE001 - an external rule never fails the file
        _skip(run.name, run.facts["source"], run.ctx, hook, exc)
        return None


def _guarded_check(run: RuleRun, check: PostCheck) -> PostCheck:
    """Wrap the post-check of an external rule (review of PR #168, finding 2).

    A check that raises logs one warning, switches the rule off and adds no
    reason. Once the rule is off, the check adds no reason and is not called.
    """

    def guarded(text: str, facts: Any) -> str | None:
        if registry.RULES.off_reason(run.name) is not None:
            return None
        return _guarded(run, "post-check", lambda: check(text, facts))

    return guarded


def _check_add(outcome: Any, ctx: RuleContext, facts: dict[str, Any]) -> None:
    """Raise when *outcome* uses ``add`` in a way the hook does not allow (design D4).

    Only a rule that declares ``adds_pages`` may add. A valid added page is in
    the scan, has text, is not flagged and is not claimed by an earlier rule.

    Raises:
        ValueError: The rule does not declare ``adds_pages``, or a page is not valid.
    """
    add = getattr(outcome, "add", frozenset())
    if not add:
        return
    if not facts["adds_pages"]:
        raise ValueError("run returned add but the rule does not declare adds_pages")
    with_text = {entry.page for entry in ctx.evidence if (entry.markdown or "").strip()}
    claimed = sorted(page for page in add if page in ctx.claimed)
    if claimed:
        raise ValueError(f"add names pages that earlier rules claimed: {claimed}")
    stray = sorted(page for page in add if page not in with_text or page in ctx.flagged)
    if stray:
        raise ValueError(f"add names pages that are flagged, blank or not in the scan: {stray}")


def _checked(
    outcome: Any, ctx: RuleContext, facts: dict[str, Any], added: frozenset[int]
) -> RuleOutcome:
    """Return the outcome of an external rule with frozen sets, or raise.

    An external rule may drop a routed page or a page that an earlier rule added,
    send direct only routed pages, and add only valid pages (:func:`_check_add`).

    Raises:
        TypeError: The outcome is not a ``RuleOutcome``, or a page set is not a set.
        ValueError: A page set names a page the rule may not name.
    """
    if not isinstance(outcome, RuleOutcome):
        raise TypeError(f"run returned a {type(outcome).__name__}, not a RuleOutcome")
    allowed = {"drop": ctx.routed | added, "direct": ctx.routed}
    for field in ("drop", "direct", "add"):
        pages = getattr(outcome, field)
        if not isinstance(pages, (set, frozenset)):
            raise TypeError(f"{field} is a {type(pages).__name__}, not a frozenset")
        if field != "add" and not pages <= allowed[field]:
            stray = sorted(pages - allowed[field])
            raise ValueError(f"{field} names pages that are not routed: {stray}")
    _check_add(outcome, ctx, facts)
    return dataclasses.replace(
        outcome,
        drop=frozenset(outcome.drop),
        direct=frozenset(outcome.direct),
        add=frozenset(outcome.add),
    )


def _waits(name: str, facts: dict[str, Any], settings: Any) -> bool:
    """Return True for a rule from another distribution that is off or not enabled."""
    if facts["source"] == registry.SOURCE_BUILT_IN:
        return False
    if registry.RULES.off_reason(name) is not None:
        return True
    options = (getattr(settings, "reading_part_options", None) or {}).get(name, {})
    return options.get("enabled") is not True


def _run_one(
    name: str, facts: dict[str, Any], ctx: RuleContext, added: frozenset[int]
) -> tuple[Any, RuleOutcome] | None:
    """Load and run one rule; return ``None`` when an external rule failed."""
    if _built_in(facts):
        rule = registry.RULES.get(name)
        outcome = rule.run(ctx)
        _check_add(outcome, ctx, facts)
        return rule, outcome
    try:
        rule = registry.RULES.get(name)
        return rule, _checked(rule.run(ctx), ctx, facts, added)
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException as exc:  # noqa: BLE001 - an external rule never fails the file
        _skip(name, facts["source"], ctx, "run", exc)
        return None


def run_rules(
    file: Path,
    evidence: Sequence[Any],
    flagged: Collection[int],
    settings: Any,
    routes: Any,
    judge: Any = None,
) -> RoutingPlan:
    """Run every registered page rule on one PDF, in ascending order.

    Args:
        file: Path to the PDF file.
        evidence: The page scan, one ``PageEvidence`` per page.
        flagged: Pages the scan flagged as needing OCR.
        settings: The injected settings.
        routes: The injected ``OcrRoutes``.
        judge: The page judge of the selected router, or ``None``. Every rule sees it.

    Returns:
        The combined plan.

    Raises:
        Exception: Whatever a built-in rule raises.
    """
    flagged = frozenset(flagged)
    dropped: frozenset[int] = frozenset()
    direct: frozenset[int] = frozenset()
    added: frozenset[int] = frozenset()
    runs: list[RuleRun] = []
    for name, facts in registry.ordered():
        if _waits(name, facts, settings):
            continue
        ctx = RuleContext(
            file, evidence, flagged, flagged - dropped, settings, routes, dropped | direct, judge
        )
        ran = _run_one(name, facts, ctx, added)
        if ran is None:
            continue
        rule, outcome = ran
        # Added pages go to the engine once, like direct pages (design D4).
        reduced = (frozenset(outcome.direct) | frozenset(outcome.add)) - dropped
        runs.append(RuleRun(name, facts, rule, ctx, outcome, reduced))
        dropped |= outcome.drop
        direct |= reduced
        added |= outcome.add
    direct -= dropped  # a later drop still removes a page an earlier rule added
    local = tuple(sorted(flagged - dropped - direct))
    return RoutingPlan(tuple(runs), dropped, direct, local)
