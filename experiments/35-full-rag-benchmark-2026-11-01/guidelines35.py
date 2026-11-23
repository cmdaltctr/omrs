"""Written label guidelines for Experiment 35, one per label set (task 16.8, P8).

Pre-registration section 11.3 asks for one written guideline per set: claim
kinds, faithfulness, correctness and Part 2 correctness. This module builds
each guideline file from the label page constants in ``labelpage35``
(``CHOICES``, ``GUIDANCE``, ``HARD_CASES``, ``LAYOUT``), so the page and the
file show the same rules and examples. The only other text is ``QUOTES``:
sentences copied word for word from ``preregistration.md`` or ``protocol.md``.
A test regenerates every file and compares it byte for byte, and checks that
each quote is still in its source.

Part 2 correctness has no page of its own yet. Its guideline uses the
correctness choices, rules and examples, because pre-registration section 18
applies the section 11.2 correctness gate rule to C2.

Run ``uv run --no-sync python experiments/35-full-rag-benchmark-2026-11-01/guidelines35.py``
to write the files into ``guidelines/``.
"""

from __future__ import annotations

from pathlib import Path

from labelpage35 import CHOICES, GUIDANCE, HARD_CASES, LAYOUT

#: The folder that holds the committed guideline files.
GUIDELINE_DIR = Path(__file__).resolve().parent / "guidelines"

#: Guideline name and the page set whose constants it uses, in file order.
SETS: dict[str, str] = {
    "claim_kinds": "claim_kinds",
    "faithfulness": "faithfulness",
    "correctness": "correctness",
    "part2_correctness": "correctness",
}

#: Title per guideline.
TITLES: dict[str, str] = {
    "claim_kinds": "Claim kinds",
    "faithfulness": "Faithfulness",
    "correctness": "Correctness",
    "part2_correctness": "Part 2 correctness",
}

_PREREG = "preregistration.md"
_PROTOCOL = "protocol.md"

_BLIND = (_PREREG, "Labellers never see scores, verdicts, setup names or chunk sizes.")
_LENGTH = (_PREREG, "Cited passage length can still hint at chunk size; the report says so.")
_PRACTICE = (_PREREG, "A training round on practice items comes first and is not evidence.")
_DISAGREE = (
    _PREREG,
    'Disagreement rule: L1 and L2 discuss; if they cannot agree, the item is "can\'t tell" '
    "and counted.",
)
_CORRECT_GATE = (
    _PREREG,
    "The gate passes on a dataset when kappa is at least 0.60 with a lower 95% bound of at "
    'least 0.40, computed with "can\'t tell" items scored both as correct and as not correct '
    "(both must pass).",
)

#: Registered rules per guideline: (source file, sentence copied word for word).
QUOTES: dict[str, tuple[tuple[str, str], ...]] = {
    "claim_kinds": (
        (
            _PREREG,
            "The labeller sees the question, the full answer with the claim marked, and the "
            "passages the claim cites.",
        ),
        (
            _PREREG,
            "Claim-kind rule (owner decision 2026-11-23, pre-freeze, from a practice labelling "
            "round): a sentence that states a checkable fact about what a source contains and "
            "also says that the source lacks the answer is mixed, not a refusal. A refusal "
            "states no checkable fact, not even about what a source contains.",
        ),
        (
            _PROTOCOL,
            'A negative finding that answers the question (for example, "no debt securities are '
            'listed") is a factual claim.',
        ),
        (
            _PREREG,
            "Agreement is refusal against not refusal (fact and mixed both count as not refusal).",
        ),
        (_PREREG, '"Can\'t tell" labels are left out and counted.'),
        _BLIND,
        _LENGTH,
        _DISAGREE,
        _PRACTICE,
    ),
    "faithfulness": (
        (
            _PREREG,
            "Faithfulness follows the LLM-AggreFact task definition (MiniCheck): a claim is "
            "supported if and only if the cited passages support it, judged as the checker sees "
            "it, on meaning not grammar.",
        ),
        (
            _PROTOCOL,
            "Judge the claim exactly as the checkers see it. Do not fill in a missing subject or "
            "a pronoun from the answer or the question. If the claim cannot be checked as "
            'written, label it "Can\'t tell".',
        ),
        (
            _PROTOCOL,
            "Judge the meaning, not the grammar. If a garbled sentence still has one clear "
            'meaning and the passages support it, label it "Supported". Label "Can\'t tell" '
            "only when the meaning itself is unclear.",
        ),
        (
            _PREREG,
            '"Can\'t tell" counts as not supported (the binary benchmark scale); kappa is also '
            'reported with "can\'t tell" items left out.',
        ),
        _BLIND,
        _LENGTH,
        _DISAGREE,
        _PRACTICE,
    ),
    "correctness": (
        _CORRECT_GATE,
        (_PREREG, "The human label for this gate is the agreed L1 and L2 label (section 11.3)."),
        _BLIND,
        _DISAGREE,
        _PRACTICE,
    ),
    "part2_correctness": (
        (
            _PREREG,
            "C2 needs its own Part 2 correctness gate (the section 11.2 rule, labels from both "
            "systems); a failed gate leaves C2 in the family as not testable.",
        ),
        (
            _PREREG,
            "L2 is the primary Part 2 labeller and labels every Part 2 item (O4, section 11.3); "
            "system identity is hidden; both systems' answers are shuffled into one list "
            "(seed 20261132).",
        ),
        _CORRECT_GATE,
        _BLIND,
        _DISAGREE,
        _PRACTICE,
    ),
}

#: Where each page role shows its field.
_WHERE: dict[str, str] = {
    "context": "on the left",
    "answer": "on the left, with the sentence to label marked",
    "passages": "on the left, one panel per cited passage",
    "focus": "on the right, beside the choices",
}

_COMMAND = "uv run --no-sync python experiments/35-full-rag-benchmark-2026-11-01/guidelines35.py"


def _seen(page_set: str) -> list[str]:
    """Return the lines that list what the labeller sees, in page order."""
    lines = []
    for n, (_, label, role) in enumerate(LAYOUT[page_set], start=1):
        shown = f"{label}s cited" if role == "passages" else label
        lines.append(f"{n}. {shown}: {_WHERE[role]}.")
    return lines


def _choices(page_set: str) -> list[str]:
    """Return one section per choice: heading, rule and worked example."""
    names = dict(CHOICES[page_set])
    lines: list[str] = []
    for value, rule, example in GUIDANCE[page_set]:
        lines += [
            f"### {names[value]} (`{value}`)",
            "",
            f"Rule: {rule}",
            "",
            f"Worked example (label {names[value]}): {example}",
            "",
        ]
    return lines


def render(name: str) -> str:
    """Return the Markdown guideline for one set.

    Args:
        name: A key of :data:`SETS`.

    Returns:
        The full file text, ending in one newline.
    """
    page_set = SETS[name]
    lines = [
        f"# Label guideline: {TITLES[name]}",
        "",
        "Experiment 35, task 16.8 (pre-registration section 11.3, P8). Do not edit this file by "
        "hand. `guidelines35.py` builds it from the label page constants in `labelpage35.py`. "
        "To change it, change the constants and run:",
        "",
        f"    {_COMMAND}",
        "",
    ]
    if name != page_set:
        lines += [
            f"This guideline uses the choices, rules and worked examples of the {page_set} set, "
            "because pre-registration section 18 applies the section 11.2 correctness gate "
            "rule to C2.",
            "",
        ]
    lines += ["## What you see", "", *_seen(page_set), ""]
    lines += ["## Choices", "", "Pick one choice for each item.", "", *_choices(page_set)]
    lines += [
        "The worked examples are made up for this guideline. None comes from a dataset, so "
        "none is in a sample.",
        "",
    ]
    if HARD_CASES[page_set]:
        lines += ["## Hard cases", "", *(f"- {case}" for case in HARD_CASES[page_set]), ""]
    lines += [
        "## Registered rules",
        "",
        "Each rule below is copied word for word from the file named after it.",
        "",
        *(f"- {quote} (`{source}`)" for source, quote in QUOTES[name]),
    ]
    return "\n".join(lines) + "\n"


def write_all(folder: Path = GUIDELINE_DIR) -> list[Path]:
    """Write every guideline file into *folder* (atomically) and return the paths.

    Args:
        folder: The output folder, created when missing.

    Returns:
        The written paths, in :data:`SETS` order.
    """
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for name in SETS:
        path = folder / f"{name}.md"
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(render(name), encoding="utf-8")
        tmp.replace(path)
        written.append(path)
    return written


if __name__ == "__main__":
    for written_path in write_all():
        print(written_path)
