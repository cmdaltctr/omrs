"""The ``maths`` page rule, order 20 (change local-ocr-backends, design D6).

Pages with a maths font skip the local tier and join the one page-listed
request to the OCR engine list (setting ``ocr_maths_routing_enabled``). The
detector reads every page, flagged or not; the pipeline then removes the pages
an earlier rule dropped. The rule calls the detector through its module at call
time, so a test that patches ``maths_routing.detect_maths_pages`` takes effect
(design D17).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .. import maths_routing
from .base import RuleContext, RuleOutcome


class MathsRule:
    """Send maths-font pages direct and stamp ``pages_maths_font``."""

    def run(self, ctx: RuleContext) -> RuleOutcome:
        """Detect the maths pages; ``state`` keeps ``None`` when routing is off."""
        found = maths_routing.detect_maths_pages(ctx.file, ctx.settings)
        return RuleOutcome(direct=frozenset(found or ()), state=found)

    def stamp(
        self, metadata: dict[str, Any], ctx: RuleContext, outcome: RuleOutcome, escalated: Iterable
    ) -> None:
        """Stamp the detected count, dropped pages included, when routing ran."""
        maths_routing.stamp_maths_count(metadata, outcome.state)


#: The rule object the registry loads.
RULE = MathsRule()
