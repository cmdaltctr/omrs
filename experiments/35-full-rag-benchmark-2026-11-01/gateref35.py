"""Read the label files of the classifier gate (A18; pre-registration 11.1 and 11.3).

L1 labels every claim of the gate sample. L2 labels the staged subset that
``labels35.py l2`` wrote to ``l2-items.json``, so an L2 file is checked
against that subset and an L1 file against the whole sample.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import labelpage35

SET = "claim_kinds"


def read_gate_labels(
    label_files: Sequence[Path], ids: Sequence[str], l2_items: Path | None = None
) -> dict[str, dict[str, str]]:
    """Return the labels by labeller (``L1``, ``L2``) from the saved label files.

    Args:
        label_files: The saved label files of the claim-kind set.
        ids: Every item ID of the gate sample.
        l2_items: ``l2-items.json`` (a dict by set, or a plain list of item
            IDs). Without it, L2 must hold every item, as L1 does.

    Raises:
        labelpage35.LabelError: A file is not valid for its labeller's item list.
    """
    given = json.loads(l2_items.read_text(encoding="utf-8")) if l2_items else list(ids)
    l2_ids = given[SET] if isinstance(given, dict) else given
    found: dict[str, dict[str, str]] = {}
    for path in label_files:
        who = json.loads(path.read_text(encoding="utf-8")).get("labeller")
        labeller, labels = labelpage35.read_labels(path, SET, l2_ids if who == "L2" else ids)
        found[labeller] = labels
    return found
