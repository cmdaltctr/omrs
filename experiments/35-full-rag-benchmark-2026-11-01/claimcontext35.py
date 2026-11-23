"""Context for the Experiment 35 claim-kind sample: the answer and the passages a claim cites.

The claim-kind labelling page shows each claim inside its full answer, with
the passages the claim cites, so the label rests on context (pre-freeze change
2026-11-23). This module also holds the reasoning check of the sample source,
moved here from ``refusals35.py`` to keep that file under 500 lines.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from outputs35 import read_rows

from omrs.core.answer.verify import split_claims


class SampleError(RuntimeError):
    """An answer folder is not a valid source of gate claims."""


def check_reasoning(run_dir: Path) -> None:
    """Refuse a run whose trace record does not show main-run answer reasoning ``none``."""
    path = run_dir / "traces.jsonl"
    rows = read_rows(path)
    if not rows:
        raise SampleError(f"{run_dir}: no {path.name}; cannot show answer reasoning 'none'")
    found = (rows[0].get("effective_settings") or {}).get("answer_reasoning")
    if found != "none":
        raise SampleError(
            f"{run_dir}: answer reasoning is {found!r}; the main run uses 'none' "
            "(pre-freeze amendment 2026-11-23)"
        )


def claim_contexts(answer: Mapping[str, Any]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Return each claim of one answer row with the passages it cites.

    The claims are the ones ``claimkinds35.answer_claims`` returns, in the same
    order. Each passage is ``{"ordinal", "text"}``: the cited ordinal and the
    evidence text the answer row saved for it. An ordinal with no saved
    evidence text is left out.

    Args:
        answer: One saved answer row (``answer`` and ``evidence``).

    Returns:
        ``(claim, passages)`` pairs in answer order.
    """
    text = answer.get("answer")
    if not text:
        return []
    evidence = answer.get("evidence") or []
    texts = {e["ordinal"]: e["text"] for e in evidence}
    return [
        (claim, [{"ordinal": o, "text": texts[o]} for o in ordinals if o in texts])
        for claim, ordinals in split_claims(text, len(evidence))
    ]
