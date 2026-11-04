"""The ``blank`` page rule, order 10 (change local-ocr-backends, design D6).

A flagged page with no stroke ink leaves the route before every OCR tier
(change skip-blank-pages-before-worker): it keeps its native text and counts
blank. The rule calls the blank test through its module at call time, so a
test that patches ``blank_pages.find_blank_pages`` takes effect (design D17).
"""

from __future__ import annotations

from .. import blank_pages
from .base import RuleContext, RuleOutcome


class BlankRule:
    """Drop the routed pages the blank test finds blank."""

    def run(self, ctx: RuleContext) -> RuleOutcome:
        """Run the blank test on the routed pages, sorted, and drop the blank ones."""
        if not ctx.routed:
            return RuleOutcome()
        return RuleOutcome(drop=blank_pages.find_blank_pages(ctx.file, sorted(ctx.routed)))


#: The rule object the registry loads.
RULE = BlankRule()
