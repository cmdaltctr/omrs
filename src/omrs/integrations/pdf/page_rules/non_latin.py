"""The ``non_latin`` page rule, order 30 (change local-ocr-backends, design D6).

Setting ``ocr_non_latin_routing`` (change non-latin-script-routing):

- direct: under ``always`` every routed page, under ``detect`` the routed pages
  with a mostly non-Latin text layer, skip the local tier;
- post-check: under ``detect`` with an engine available, a local result that is
  mostly non-Latin escalates with the reason ``non_latin_output``;
- degrade: a page this rule sent direct that no engine read goes to the local
  tier, with one warning;
- stamp: ``pages_non_latin`` when the mode is not ``off``.

The rule calls ``script_routing`` through the module at call time, so a test
that patches a ``script_routing`` attribute takes effect (design D17).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from .. import script_routing
from .base import PostCheck, RuleContext, RuleOutcome

logger = logging.getLogger(__name__)


class NonLatinRule:
    """Route non-Latin pages past the local tier and check local output."""

    def run(self, ctx: RuleContext) -> RuleOutcome:
        """Send the routed pages this setting picks direct."""
        direct = script_routing.non_latin_direct_pages(
            ctx.file, ctx.routed, ctx.settings, ctx.routes
        )
        return RuleOutcome(direct=direct)

    def post_check(self, ctx: RuleContext, outcome: RuleOutcome) -> PostCheck | None:
        """Return the non-Latin output check under ``detect`` with an engine, else ``None``."""
        if not script_routing.post_check_enabled(ctx.settings, ctx.routes):
            return None
        return script_routing.non_latin_output_reason

    def degrade(self, ctx: RuleContext, outcome: RuleOutcome, unread: list[int]) -> list[int]:
        """Send every unread non-Latin page to the local tier, with one warning."""
        logger.warning(
            "No OCR engine read %d non-Latin page(s) in %s; they went to the local tier.",
            len(unread),
            getattr(ctx.file, "name", ctx.file),
        )
        return list(unread)

    def stamp(
        self, metadata: dict[str, Any], ctx: RuleContext, outcome: RuleOutcome, escalated: Iterable
    ) -> None:
        """Stamp ``pages_non_latin``: direct pages plus local results it escalated."""
        script_routing.stamp_non_latin_count(metadata, ctx.settings, outcome.direct, escalated)


#: The rule object the registry loads.
RULE = NonLatinRule()
