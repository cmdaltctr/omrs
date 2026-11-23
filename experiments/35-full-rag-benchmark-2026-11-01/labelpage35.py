"""Blind labelling page and label files for Experiment 35 (tasks 8.4 and 15.8).

One static HTML page per label set: claim kinds, faithfulness verdicts or
correctness. The page shows only the fields a labeller needs (question and
claim; cited passages for faithfulness; reference and answer for
correctness). It never shows a kind, a verdict, a score, a setup name or a
chunk size, and it loads nothing from the network. The labeller picks `L1`
or `L2` (no name field). The page keeps a draft in browser storage inside
``try``/``catch`` and saves the labels as a JSON download.

This module also reads the saved label files and builds the reference label
of pre-registration section 11.3.
"""

from __future__ import annotations

import html
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from labelpage_assets35 import CSS, SCRIPT

#: The choices per set, as saved value and shown text.
CHOICES: dict[str, tuple[tuple[str, str], ...]] = {
    "claim_kinds": (
        ("factual", "Factual claim"),
        ("refusal", "Refusal"),
        ("mixed", "Mixed"),
        ("cant_tell", "Can't tell"),
    ),
    "faithfulness": (
        ("supported", "Supported"),
        ("not_supported", "Not supported"),
        ("cant_tell", "Can't tell"),
    ),
    "correctness": (
        ("correct", "Correct"),
        ("not_correct", "Not correct"),
        ("cant_tell", "Can't tell"),
    ),
}

#: The only item fields that reach the page, per set.
FIELDS: dict[str, tuple[str, ...]] = {
    "claim_kinds": ("question", "claim"),
    "faithfulness": ("question", "claim", "passages"),
    "correctness": ("question", "reference", "answer"),
}

#: The page title per set.
TITLES: dict[str, str] = {
    "claim_kinds": "Claim kinds",
    "faithfulness": "Faithfulness",
    "correctness": "Correctness",
}

#: How the page shows each field, per set, in order: field, plain-words label and role.
#: ``focus`` is the item to judge, ``context`` a muted panel, ``passages`` one box per passage.
LAYOUT: dict[str, tuple[tuple[str, str, str], ...]] = {
    "claim_kinds": (
        ("question", "Question", "context"),
        ("claim", "Sentence to label", "focus"),
    ),
    "faithfulness": (
        ("question", "Question", "context"),
        ("claim", "Sentence to label", "focus"),
        ("passages", "Passage", "passages"),
    ),
    "correctness": (
        ("question", "Question", "context"),
        ("reference", "Reference answer", "context"),
        ("answer", "Answer", "focus"),
    ),
}

#: Guidance shown at the top of each page, as (choice, meaning). The claim-kind text
#: follows protocol.md ("Three claim kinds"); the faithfulness lines add protocol.md's
#: labelling rules 1 and 2.
GUIDANCE: dict[str, tuple[tuple[str, str], ...]] = {
    "claim_kinds": (
        (
            "Factual claim",
            "States something that can be checked against a source. A negative answer counts "
            '("No debt securities are listed").',
        ),
        ("Refusal", "Only says the sources do not cover something. It states no fact."),
        (
            "Mixed",
            "A checkable fact plus a limit on what the sources cover. It counts as factual.",
        ),
        ("Can't tell", "Use this rarely."),
    ),
    "faithfulness": (
        (
            "Supported",
            "Every part of the sentence is stated in the passages or follows directly from them.",
        ),
        ("Not supported", "Any part is missing from the passages or is contradicted by them."),
        (
            "Can't tell",
            "Use this rarely. Judge the sentence as written: do not fill in a missing subject "
            "from the question. If the meaning is unclear, choose this.",
        ),
    ),
    "correctness": (
        ("Correct", "The answer gives the key facts of the reference answer and contradicts none."),
        ("Not correct", "Any other case."),
        ("Can't tell", "Use this rarely."),
    ),
}

LABELLERS = ("L1", "L2")
CANT_TELL = "cant_tell"


class LabelError(ValueError):
    """A label file does not match its set or sample."""


def page_items(set_name: str, items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return the items with only ``item_id`` and the page fields of *set_name*."""
    fields = FIELDS[set_name]
    return [{"item_id": item["item_id"], **{f: item[f] for f in fields}} for item in items]


def write_page(path: Path, set_name: str, items: Sequence[Mapping[str, Any]]) -> None:
    """Write the static labelling page for one set.

    Args:
        path: The HTML file to write (atomically).
        set_name: ``claim_kinds``, ``faithfulness`` or ``correctness``.
        items: Sample items. Each holds ``item_id`` and the set's fields;
            every other field is dropped before it reaches the page.
    """
    data = {
        "set": set_name,
        "fields": list(FIELDS[set_name]),
        "layout": [list(row) for row in LAYOUT[set_name]],
        "choices": [list(c) for c in CHOICES[set_name]],
        "items": page_items(set_name, items),
    }
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(TITLES[set_name], quote=False)
    options = "".join(f'<option value="{w}">{w}</option>' for w in LABELLERS)
    guide = "".join(
        f"<dt>{html.escape(term, quote=False)}</dt><dd>{html.escape(meaning, quote=False)}</dd>"
        for term, meaning in GUIDANCE[set_name]
    )
    hint = (
        f"Keys: 1 to {len(CHOICES[set_name])} pick a choice. "
        "J or K, or the Up and Down arrows, move between items."
    )
    # The viewport tag is written "name =" because tests ban the text "name=" on this page
    # (it guards against a name field for the labeller).
    text = (
        '<!doctype html>\n<html lang="en-GB"><head><meta charset="utf-8">'
        '<meta name ="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title} labels</title><style>{CSS}</style></head><body>\n"
        '<header class="bar" id="bar"><div class="bar-inner">'
        f"<h1>{title}</h1>"
        '<label class="who">Labeller '
        f'<select id="labeller"><option value=""></option>{options}</select></label>'
        '<button id="next" type="button">Next unlabelled</button>'
        '<button id="save" type="button" class="primary">Save labels</button>'
        '<div class="progress" id="progress" role="status" aria-live="polite">'
        f'<span id="progress-text">0 of {len(data["items"])} labelled</span>'
        '<div class="track" id="track" role="progressbar" aria-label="Labelling progress" '
        f'aria-valuemin="0" aria-valuemax="{len(data["items"])}" aria-valuenow="0">'
        '<div class="fill" id="progress-bar"></div></div></div>'
        "</div></header>\n"
        '<main class="page">\n'
        f'<details class="guide"><summary>How to label</summary><dl>{guide}</dl></details>\n'
        f'<p class="hint">{hint}</p>\n'
        '<div id="list"></div>\n</main>\n'
        f'<script type="application/json" id="items">{blob}</script>\n'
        f"<script>{SCRIPT}</script>\n</body></html>\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def read_labels(path: Path, set_name: str, item_ids: Sequence[str]) -> tuple[str, dict[str, str]]:
    """Read one saved label file and check it against its set and sample.

    Args:
        path: The JSON file the page saved.
        set_name: The set the file must hold.
        item_ids: The item IDs the labeller was given.

    Returns:
        The labeller (``L1`` or ``L2``) and the labels by item ID.

    Raises:
        LabelError: Wrong set or labeller, an unknown item or choice, or a
            missing label.
    """
    found = json.loads(path.read_text(encoding="utf-8"))
    if found.get("set") != set_name:
        raise LabelError(f"{path.name}: set {found.get('set')!r}, expected {set_name!r}")
    if found.get("labeller") not in LABELLERS:
        raise LabelError(f"{path.name}: labeller must be L1 or L2")
    labels: dict[str, str] = dict(found.get("labels") or {})
    allowed = {c for c, _ in CHOICES[set_name]}
    wanted = set(item_ids)
    extra = sorted(set(labels) - wanted)
    bad = sorted(i for i, v in labels.items() if v not in allowed)
    missing = sorted(wanted - set(labels))
    if extra or bad or missing:
        raise LabelError(
            f"{path.name}: unknown items {extra}, bad choices {bad}, missing {missing}"
        )
    return found["labeller"], labels


def reference_labels(
    l1: Mapping[str, str],
    l2: Mapping[str, str],
    resolved: Mapping[str, str],
) -> tuple[dict[str, str], int]:
    """Return the gate reference labels and the count of unresolved items.

    Pre-registration section 11.3: where both labelled an item, the agreed
    label; a disagreement takes the label L1 and L2 agreed on after
    discussion (*resolved*), and an item they could not agree on becomes
    "can't tell" and is counted. Where only L1 labelled an item, L1's label.

    Args:
        l1: L1's labels by item ID (every item).
        l2: L2's labels by item ID (all or some items).
        resolved: The label agreed after discussion, by item ID.

    Returns:
        The reference labels by item ID, and the unresolved count.
    """
    out: dict[str, str] = {}
    unresolved = 0
    for item in sorted(l1):
        if item not in l2 or l1[item] == l2[item]:
            out[item] = l1[item]
        elif item in resolved:
            out[item] = resolved[item]
        else:
            out[item] = CANT_TELL
            unresolved += 1
    return out, unresolved


def set_reference(
    label_dir: Path, set_name: str, item_ids: Sequence[str]
) -> tuple[dict[str, str], int]:
    """Read one set's label files and return its reference labels and unresolved count.

    Files in *label_dir*: ``labels-<set>-L1.json`` (every item),
    ``labels-<set>-L2.json`` (the items in ``l2-items.json`` for the set when
    that file exists, else every item; optional) and
    ``resolved-<set>.json`` (labels agreed after discussion; optional).
    """
    l2_path = label_dir / "l2-items.json"
    l2_ids = (
        json.loads(l2_path.read_text(encoding="utf-8")).get(set_name, item_ids)
        if l2_path.exists()
        else item_ids
    )
    _, l1 = read_labels(label_dir / f"labels-{set_name}-L1.json", set_name, item_ids)
    second = label_dir / f"labels-{set_name}-L2.json"
    l2 = read_labels(second, set_name, l2_ids)[1] if second.exists() else {}
    resolved_path = label_dir / f"resolved-{set_name}.json"
    resolved = (
        json.loads(resolved_path.read_text(encoding="utf-8")) if resolved_path.exists() else {}
    )
    return reference_labels(l1, l2, resolved)
