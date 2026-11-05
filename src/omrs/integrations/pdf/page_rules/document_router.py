"""The ``document_router`` page rule, order 40 (change document-reading-routers, design D4).

A router asks a decision model, one page at a time, whether a page's native
text can be kept. The rule judges every page that has non-blank text, that the
scan did not flag and that no earlier rule claimed. A page whose P(yes) is
below the router threshold goes to the OCR engine list in ``RuleOutcome.add``.
A flagged page already goes to OCR, so it is never judged; OCR output is never
judged.

Cost: about 3.6 s per judged page with the local model, and about 2.7% of
healthy pages (15 of 565) sent to OCR in Experiment 43.

- run: an empty outcome, before any page is read, when no judge is wired (no
  router) or the judge carries a fixed reason (design D8). An image router with
  no page renderer gives ``renderer-missing``. A failed request keeps the page
  and counts it unjudged; when every request fails the reason is
  ``request-failed``. After ``MAX_FAILED_IN_A_ROW`` failed requests in a row
  the rule stops asking, so a hung server does not cost the request timeout
  on every page. The pages left count unjudged, and the reason is
  ``unreachable`` when no page was judged. A page whose image fails to
  render is not a failed request.
- degrade: an added page that no engine read goes to the local tier, with one
  warning.
- stamp: ``router_pages_judged`` (pages with an answer), ``_accepted``,
  ``_rejected``, ``_unjudged`` and ``router_status`` (``ok`` or the reason).
  With no router it stamps nothing.

The judge is built by the composition root and arrives on ``ctx.judge``; this
module imports no provider. Logs hold counts only, never page text or images.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .base import RuleContext, RuleOutcome

logger = logging.getLogger(__name__)

#: The page renderer package (design D5). It is imported on first use only.
_RENDERER = "omrs.integrations.pdf.page_images"

STATUS_OK = "ok"
RENDERER_MISSING = "renderer-missing"
REQUEST_FAILED = "request-failed"
UNREACHABLE = "unreachable"
#: Failed requests in a row after which the rule stops asking for this file.
MAX_FAILED_IN_A_ROW = 3


@dataclass(frozen=True)
class RouterCounts:
    """What the router did on one PDF; the stamp writes it."""

    judged: int = 0
    accepted: int = 0
    rejected: int = 0
    unjudged: int = 0
    status: str = STATUS_OK


def _renderer() -> Any | None:
    """Return the page renderer module when a renderer is available, else ``None``."""
    try:
        module = importlib.import_module(_RENDERER)
    except ImportError:
        return None
    return module if module.available() else None


def _candidates(ctx: RuleContext) -> list[Any]:
    """Return the unflagged, unclaimed pages with text, in page order."""
    skip = ctx.flagged | ctx.claimed
    pages = [e for e in ctx.evidence if (e.markdown or "").strip() and e.page not in skip]
    return sorted(pages, key=lambda entry: entry.page)


def _ask(
    ctx: RuleContext, judge: Any, entry: Any, renderer: Any | None
) -> tuple[float | None, bool]:
    """Return P(yes) for one page (``None`` when it cannot be judged) and whether it was asked."""
    try:
        image = renderer.render_page(ctx.file, entry.page) if renderer is not None else None
    except Exception:  # noqa: BLE001 - no file fails because of a router (design D8)
        return None, False
    try:
        return judge.judge(entry.markdown[: judge.max_chars], image), True
    except Exception:  # noqa: BLE001 - no file fails because of a router (design D8)
        return None, True


class DocumentRouterRule:
    """Send the unflagged pages the router rejects to the OCR engine list."""

    def run(self, ctx: RuleContext) -> RuleOutcome:
        """Judge the candidate pages one at a time and add the rejected ones."""
        judge = ctx.judge
        if judge is None:
            return RuleOutcome()
        try:
            status = judge.status
        except Exception:  # noqa: BLE001 - no file fails because of a router (design D8)
            logger.warning("The router checks failed in %s; no page was judged.", ctx.file.name)
            status = REQUEST_FAILED
        if status is not None:
            return RuleOutcome(state=RouterCounts(status=status))
        renderer = None
        if judge.images:
            renderer = _renderer()
            if renderer is None:
                return RuleOutcome(state=RouterCounts(status=RENDERER_MISSING))
        accepted, rejected, unjudged, failed_in_a_row = 0, set(), 0, 0
        candidates = _candidates(ctx)
        for index, entry in enumerate(candidates):
            if failed_in_a_row >= MAX_FAILED_IN_A_ROW:
                unjudged += len(candidates) - index
                break
            score, asked = _ask(ctx, judge, entry, renderer)
            if asked:  # a page that failed to render leaves the count alone
                failed_in_a_row = failed_in_a_row + 1 if score is None else 0
            if score is None:
                unjudged += 1
            elif score < judge.threshold:
                rejected.add(entry.page)
            else:
                accepted += 1
        judged = accepted + len(rejected)
        stopped = failed_in_a_row >= MAX_FAILED_IN_A_ROW
        status = STATUS_OK
        if unjudged and not judged:
            status = UNREACHABLE if stopped else REQUEST_FAILED
        counts = RouterCounts(judged, accepted, len(rejected), unjudged, status)
        return RuleOutcome(add=frozenset(rejected), state=counts)

    def degrade(self, ctx: RuleContext, outcome: RuleOutcome, unread: list[int]) -> list[int]:
        """Send every unread added page to the local tier, with one warning."""
        logger.warning(
            "No OCR engine read %d page(s) the router rejected in %s; they went to the local tier.",
            len(unread),
            getattr(ctx.file, "name", ctx.file),
        )
        return list(unread)

    def stamp(
        self, metadata: dict[str, Any], ctx: RuleContext, outcome: RuleOutcome, escalated: Iterable
    ) -> None:
        """Stamp the router counts and status; nothing when no router ran."""
        counts = outcome.state
        if not isinstance(counts, RouterCounts):
            return
        metadata.update(
            {
                "router_pages_judged": counts.judged,
                "router_pages_accepted": counts.accepted,
                "router_pages_rejected": counts.rejected,
                "router_pages_unjudged": counts.unjudged,
                "router_status": counts.status,
            }
        )


#: The rule object the registry loads.
RULE = DocumentRouterRule()
