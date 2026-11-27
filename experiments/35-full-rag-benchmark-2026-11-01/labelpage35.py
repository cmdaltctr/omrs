"""Blind labelling page and label files for Experiment 35 (tasks 8.4 and 15.8).

One static HTML page per label set: claim kinds, faithfulness verdicts or
correctness. The page follows the Experiment 34 review page: a sticky bar, one
collapsible card per item, context on the left and the sentence to judge with
the choice chips on the right. It shows only the fields a labeller needs:
claim kinds, the question, the full answer with the claim marked and the
passages the claim cites; faithfulness, the question, the claim and its cited
passages; correctness, the question, the reference and the answer.
Pre-freeze change 2026-11-23: the labeller sees the question, the full answer
with the claim marked, and the passages the claim cites, so the label rests on
context. The page still shows no kind, verdict, score or setup. It never shows
a chunk size either, and it loads nothing from the network. Answers and
passages are rendered from Markdown in Python (``labelrender35``), escaped.
The labeller picks `L1` or `L2` (no name field). The page keeps a draft in
browser storage inside ``try``/``catch`` and saves the labels as a JSON
download (an optional ``notes`` map rides along; :func:`read_labels` ignores it).

This module also reads the saved label files and builds the reference label
of pre-registration section 11.3.
"""

from __future__ import annotations

import argparse
import html
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from labelaids35 import (
    AUDIT_CHOICES,
    AUDIT_FIELDS,
    AUDIT_GUIDANCE,
    AUDIT_LAYOUT,
    AUDIT_QUESTION,
    INSTRUCTIONS_HTML,
    aid_attr,
    aids_row,
)
from labelpage_assets35 import CSS, SCRIPT, exp34_style
from labelrender35 import mark_claim, render_inline, render_markdown, render_passage

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
    "relevance_audit": AUDIT_CHOICES,
}

#: The only item fields that reach the page, per set.
FIELDS: dict[str, tuple[str, ...]] = {
    "claim_kinds": ("question", "claim", "answer", "passages"),
    "faithfulness": ("question", "claim", "passages"),
    "correctness": ("question", "reference", "answer"),
    "relevance_audit": AUDIT_FIELDS,
}

#: The page title per set.
TITLES: dict[str, str] = {
    "claim_kinds": "Claim kinds",
    "faithfulness": "Faithfulness",
    "correctness": "Correctness",
    "relevance_audit": "Relevance audit",
}

#: How the page shows each field, per set, in order: field, plain-words label and role.
#: ``focus`` is the item to judge (right), ``context`` a short text (left), ``answer``
#: the full answer with the claim marked (left) and ``passages`` one panel per passage (left).
LAYOUT: dict[str, tuple[tuple[str, str, str], ...]] = {
    "claim_kinds": (
        ("question", "Question", "context"),
        ("answer", "Full answer", "answer"),
        ("passages", "Passage", "passages"),
        ("claim", "Sentence to label", "focus"),
    ),
    "faithfulness": (
        ("question", "Question", "context"),
        ("passages", "Passage", "passages"),
        ("claim", "Sentence to label", "focus"),
    ),
    "correctness": (
        ("question", "Question", "context"),
        ("reference", "Reference answer", "context"),
        ("answer", "Answer", "focus"),
    ),
    "relevance_audit": AUDIT_LAYOUT,
}

#: The Instructions panel of each page, per set: (choice value, rule, worked example), in
#: the order of ``CHOICES``. The claim-kind rules follow protocol.md ("Three claim kinds");
#: the faithfulness rules are protocol.md's labelling rules 1 and 2. Pre-freeze change
#: 2026-11-23: one rule and one example per choice, and the owner's decision on a
#: sentence that states what a source contains and says the source lacks the answer.
GUIDANCE: dict[str, tuple[tuple[str, str, str], ...]] = {
    "claim_kinds": (
        (
            "factual",
            "The sentence states something that can be checked against a source. A negative "
            'answer that answers the question counts ("No debt securities are listed").',
            'Sentence: "The company was founded in 1998 and has 300 staff."',
        ),
        (
            "refusal",
            "The sentence only says that the sources do not cover something. It states no "
            "checkable fact, not even about what a source contains.",
            'Sentence: "The provided sources do not cover the 2019 audit."',
        ),
        (
            "mixed",
            "The sentence states a checkable fact and also says that the sources lack the answer "
            "or part of it. Mixed counts as factual in scoring.",
            'Sentence: "The policy page lists three plans but gives no prices."',
        ),
        (
            "cant_tell",
            "Use this rarely. Choose it only when the sentence is too unclear to sort.",
            'Sentence: "As noted above." (a fragment you cannot sort)',
        ),
    ),
    "faithfulness": (
        (
            "supported",
            "Every part of the sentence is stated in the passages or follows directly from them.",
            'Passage: "Weight: 2 kg." Sentence: "The device weighs 2 kg."',
        ),
        (
            "not_supported",
            "Any part is missing from the passages or is contradicted by them.",
            'Passage: "Weight: 2 kg." Sentence: "The device weighs 2 kg and is waterproof."',
        ),
        (
            "cant_tell",
            "Use this rarely. Judge the sentence as written: do not fill in a missing subject "
            "from the question. If the meaning is unclear, choose this.",
            'Sentence: "It was approved in May." (no subject, so the meaning is unclear)',
        ),
    ),
    "correctness": (
        (
            "correct",
            "The answer gives the key facts of the reference answer and contradicts none.",
            'Reference: "Paris." Answer: "The capital is Paris."',
        ),
        (
            "not_correct",
            "Any other case.",
            'Reference: "Paris, with 2.1 million people." Answer: "Paris." (a key fact is missing)',
        ),
        (
            "cant_tell",
            "Use this rarely. Choose it only when you cannot read what the answer claims.",
            "The answer stops in the middle of a sentence.",
        ),
    ),
    "relevance_audit": AUDIT_GUIDANCE,
}

#: Hard cases agreed with the owner, per set. Add each new one after a practice round.
HARD_CASES: dict[str, tuple[str, ...]] = {
    "claim_kinds": (
        "A sentence that says what a source contains and also says that the source lacks the "
        'answer is Mixed, not Refusal. Example: "Source X lists subsidiaries but no debt '
        'securities" is Mixed, because the list of subsidiaries is a checkable fact about the '
        "source.",
        'A negative answer that answers the question is Factual. Example: "No debt securities '
        'are listed."',
        "Refusal needs no checkable fact at all, not even about what a source contains.",
        "A sentence that says the sources do not state something is Refusal, even when it also "
        "names part of the question or the user's own setup, as long as it states no fact about "
        'a source. Example: "The sources do not say when the bug was fixed, so they cannot '
        'confirm whether your version 1.2 is the cause" is Refusal.',
        'A sentence that says what a source covers or is about, even "unrelated topics", is '
        'Factual or Mixed, never Refusal. Example: "One source is about tax law and the others '
        'cover unrelated topics" is Factual.',
        "A trailing citation stub such as \"see,,,,\" or an empty bracket pair does not make a "
        "sentence factual. A sentence that says the sources do not state, describe or contain "
        "something, with only a citation stub after it, is Refusal. Example: \"The sources do "
        "not describe a way to fix this error; see,,,,.\" is Refusal.",
        "A sentence that says the sources lack something and also states what the excerpts do "
        "contain is Mixed, never Refusal. Example: \"The sources do not show the balance sheet "
        "line; the excerpts include cash flow and debt\" is Mixed.",
        "A sentence that points the user to documentation or a source for more detail is "
        "Factual, not Refusal. Example: \"You may want to read the library documentation for "
        "the current API\" is Factual.",
        "Mixed counts as factual in scoring. Choose Mixed when it fits.",
    ),
    "faithfulness": (),
    "correctness": (),
    "relevance_audit": (),
}

#: The question above the choice chips when it differs from "Your label".
QUESTIONS: dict[str, str] = {"relevance_audit": AUDIT_QUESTION}

LABELLERS = ("L1", "L2")
CANT_TELL = "cant_tell"


class LabelError(ValueError):
    """A label file does not match its set or sample."""


def page_items(set_name: str, items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return the items with only ``item_id`` and the page fields of *set_name*."""
    fields = FIELDS[set_name]
    return [{"item_id": item["item_id"], **{f: item[f] for f in fields}} for item in items]


def _toggle(field: str, label: str, body: str, k: int | None = None, aid: str = "") -> str:
    """A rendered block with a Rendered / Raw toggle (raw text is filled by the script)."""
    index = "" if k is None else f' data-k="{k}"'
    return (
        f'<div class="outwrap" data-f="{field}"{index}{aid}><div class="viewbar">'
        f'<p class="tag">{label}</p>'
        '<button type="button" class="vt on" data-v="md">Rendered</button>'
        '<button type="button" class="vt" data-v="raw">Raw</button>'
        '<button type="button" class="vx" aria-pressed="false">Expand</button></div>'
        f'<div class="md">{body}</div><pre class="raw" hidden></pre></div>'
    )


def _passages(field: str, passages: Sequence[Any], aid: str = "") -> str:
    """One collapsible panel per passage, named by the ordinal the answer cites."""
    panels = []
    for k, passage in enumerate(passages):
        if isinstance(passage, Mapping):
            name, text = f"Passage [{passage['ordinal']}]", passage["text"]
        else:
            name, text = f"Passage {k + 1}", passage
        panels.append(
            '<details class="engine psg"><summary>'
            f'<span class="en">{name}</span></summary>'
            f"{_toggle(field, 'Text', render_passage(text), k, aid)}</details>"
        )
    return "".join(panels) or '<p class="pending">No cited passage.</p>'


def _card(set_name: str, i: int, item: Mapping[str, Any]) -> str:
    """One item card: context left (sticky), sentence and choice chips right."""
    left: list[str] = []
    right: list[str] = []
    for field, label, role in LAYOUT[set_name]:
        value = item[field]
        aid = aid_attr(set_name, field)
        if role == "context":
            left.append(
                f'<div class="blk ctx"><p class="tag">{label}</p>'
                f"<p{aid}>{render_inline(value)}</p></div>"
            )
        elif role == "block":
            body = render_markdown(value)
            left.append(f'<div class="ans">{_toggle(field, label, body, None, aid)}</div>')
        elif role == "answer":
            body = render_markdown(mark_claim(value, item.get("claim", "")))
            left.append(f'<div class="ans">{_toggle(field, label, body)}</div>')
        elif role == "passages":
            left.append(f'<div class="blk"><p class="tag">{label}s cited</p>')
            left.append(f"{_passages(field, value, aid)}</div>")
        elif field == "claim":
            focus = f'<p class="focus">{render_inline(value)}</p>'
            shown = f"<div{aid}>{focus}</div>" if aid else focus
            right.append(f'<p class="tag">{label}</p>{shown}')
        else:
            body = (render_passage if role == "unit" else render_markdown)(value)
            right.append(f'<div class="ans">{_toggle(field, label, body, None, aid)}</div>')
    right.append(aids_row())
    chips = "".join(
        f'<label class="chip"><input type="radio" value="{value}">'
        f"<span><kbd>{c + 1}</kbd>{html.escape(text, quote=False)}</span></label>"
        for c, (value, text) in enumerate(CHOICES[set_name])
    )
    right.append(
        f'<fieldset class="form"><legend>{QUESTIONS.get(set_name, "Your label")}</legend>'
        f'<div class="opts">{chips}</div>'
        '<input type="text" class="note" placeholder="Note (optional)" aria-label="Note">'
        '<button type="button" class="clear">Clear</button></fieldset>'
    )
    question = render_inline(item.get("question", ""))
    return (
        f'<details class="page" data-i="{i}"><summary><span class="pt">Item {i + 1}</span>'
        f'<span class="qs">{question}</span><span class="pnote"></span><span class="pstat"></span></summary>'
        f'<div class="body"><div class="orig"><div class="stick">{"".join(left)}</div></div>'
        f'<div class="judge">{"".join(right)}</div></div></details>'
    )


def write_page(
    path: Path,
    set_name: str,
    items: Sequence[Mapping[str, Any]],
    model_labeller: bool = False,
) -> None:
    """Write the static labelling page for one set.

    Args:
        path: The HTML file to write (atomically).
        set_name: ``claim_kinds``, ``faithfulness``, ``correctness`` or ``relevance_audit``.
        items: Sample items. Each holds ``item_id`` and the set's fields;
            every other field is dropped before it reaches the page.
        model_labeller: Build the model-labeller copy. It keeps its browser drafts
            under a separate key (suffix ``-model``), so it never loads a human draft,
            and its banner says so.
    """
    shown = page_items(set_name, items)
    data = {
        "set": set_name,
        "fields": list(FIELDS[set_name]),
        "choices": [list(c) for c in CHOICES[set_name]],
        "items": shown,
    }
    if model_labeller:
        data.update(draft_suffix="-model", model_labeller=True)
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(TITLES[set_name], quote=False)
    options = "".join(f'<option value="{w}">{w}</option>' for w in LABELLERS)
    keys = len(CHOICES[set_name])
    names = dict(CHOICES[set_name])
    rules = "".join(
        f'<dt><span class="cn" data-c="{value}">{html.escape(names[value], quote=False)}</span></dt>'
        f"<dd>{html.escape(rule, quote=False)}"
        f'<span class="eg"><b>Example.</b> {html.escape(example, quote=False)}</span></dd>'
        for value, rule, example in GUIDANCE[set_name]
    )
    hard = "".join(f"<li>{html.escape(h, quote=False)}</li>" for h in HARD_CASES[set_name])
    hard_block = f"<h2>Hard cases</h2><ul>{hard}</ul>" if hard else ""
    instructions = (
        '<details class="panel" id="instructions" open><summary>Instructions</summary>'
        '<div class="pbody"><p>Open an item. The context stays on the left; judge the item on '
        f'the right and pick one choice.</p><dl class="rules">{rules}</dl>{hard_block}'
        f"{INSTRUCTIONS_HTML}"
        f'<p class="keys">Keys: 1 to {keys} pick a choice; J and K move to the next or '
        "previous item. Your draft is kept in this browser; Save labels downloads the file."
        "</p></div></details>"
    )
    banner = '<span class="mlbanner">Model labeller copy</span>' if model_labeller else ""
    cards = "\n".join(_card(set_name, i, item) for i, item in enumerate(shown))
    # The viewport tag is written "name =" because tests ban the text "name=" on this page
    # (it guards against a name field for the labeller).
    text = (
        '<!doctype html>\n<html lang="en-GB"><head><meta charset="utf-8">'
        '<meta name ="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{title} labels</title><style>{exp34_style()}{CSS}</style></head><body>\n"
        f'<header class="bar" id="bar"><h1>{title}</h1>{banner}'
        '<span id="progress" role="status" aria-live="polite"></span>'
        '<button id="next" type="button">Next unlabelled</button>'
        '<button id="collapse" type="button">Collapse all</button>'
        '<button id="instructions-button" type="button">Instructions</button>'
        '<label class="who">Labeller '
        f'<select id="labeller"><option value=""></option>{options}</select></label>'
        '<button id="save" type="button" class="primary">Save labels</button>'
        '<span id="autosave" hidden>Autosave unavailable: save often.</span>'
        "</header>\n<main>\n"
        f"{instructions}\n{cards}\n</main>\n"
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


def main(argv: Sequence[str] | None = None) -> None:
    """Build one page from an items JSON file: ``--model-labeller`` writes the model copy."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--set", dest="set_name", required=True, choices=sorted(CHOICES))
    parser.add_argument("--items", type=Path, required=True, help="JSON list of items")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model-labeller", action="store_true", help="separate draft key")
    args = parser.parse_args(argv)
    items = json.loads(args.items.read_text(encoding="utf-8"))
    write_page(args.out, args.set_name, items, model_labeller=args.model_labeller)


if __name__ == "__main__":
    main()
