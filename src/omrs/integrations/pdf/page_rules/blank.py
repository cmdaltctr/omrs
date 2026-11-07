"""The ``blank`` page rule, order 10 (change local-ocr-backends, design D6).

A flagged page with no stroke ink leaves the route before every OCR tier
(change skip-blank-pages-before-worker): it keeps its native text and counts
blank. The rule calls the blank test through its module at call time, so a
test that patches ``blank_pages.find_blank_pages`` takes effect (design D17).

With ``ocr_skip_blank_pages`` off (change page-routing-panel, design D3) the
rule returns an empty outcome before the blank test runs, so no page renders
and every flagged page follows the flagged route. The rule keeps its place.
"""

from __future__ import annotations

from .. import blank_pages
from .base import RuleContext, RuleOutcome


class BlankRule:
    """Drop the routed pages the blank test finds blank."""

    def run(self, ctx: RuleContext) -> RuleOutcome:
        """Run the blank test on the routed pages, sorted, and drop the blank ones.

        With ``ocr_skip_blank_pages`` off, drop nothing and run no test.
        """
        if not ctx.routed or not ctx.settings.ocr_skip_blank_pages:
            return RuleOutcome()
        return RuleOutcome(drop=blank_pages.find_blank_pages(ctx.file, sorted(ctx.routed)))


#: The rule object the registry loads.
RULE = BlankRule()
