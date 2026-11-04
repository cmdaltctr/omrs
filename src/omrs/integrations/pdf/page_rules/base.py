"""The page-rule interface (change local-ocr-backends, design D5).

A rule is an object with ``run(ctx) -> RuleOutcome``. It may also have these
hooks. The pipeline calls a hook only when the rule's registration declares it
(``has_post_check``, ``has_degrade``); ``stamp`` runs when the rule has one.

- ``post_check(ctx, outcome) -> PostCheck | None``: a check that the shared
  escalation rule runs on each local OCR result.
- ``degrade(ctx, outcome, unread) -> list[int]``: of the pages this rule was
  first to send direct and that no engine read, the pages the local tier must
  read instead.
- ``stamp(metadata, ctx, outcome, escalated) -> None``: writes the rule's
  diagnostic count after the pages are placed.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

#: A post-check gets the text of one local result and the facts of the backend
#: that read it, and returns an escalation reason or ``None``. The facts are
#: ``None`` until the ordered local backend list exists (task group 4).
PostCheck = Callable[[str, Any], "str | None"]


@dataclass(frozen=True)
class RuleContext:
    """What a rule sees for one PDF.

    Attributes:
        file: Path to the PDF file.
        evidence: The page scan, one ``PageEvidence`` per page.
        flagged: Pages the scan flagged as needing OCR.
        routed: Flagged pages that earlier rules did not drop.
        settings: The injected settings.
        routes: The injected ``OcrRoutes`` (OCR engine availability).
    """

    file: Path
    evidence: Sequence[Any]
    flagged: frozenset[int]
    routed: frozenset[int]
    settings: Any
    routes: Any


@dataclass(frozen=True)
class RuleOutcome:
    """What a rule decided for one PDF.

    Attributes:
        drop: Pages that leave the route. They keep native text and count blank.
        direct: Pages sent to the OCR engine list without the local tier.
        state: Anything the rule needs later, for its stamp or its degrade hook.
    """

    drop: frozenset[int] = frozenset()
    direct: frozenset[int] = frozenset()
    state: Any = None


class PageRule(Protocol):
    """The one method every page rule has. The hooks are optional (module docstring)."""

    def run(self, ctx: RuleContext) -> RuleOutcome:
        """Decide the drops and direct pages of one PDF."""
        ...
