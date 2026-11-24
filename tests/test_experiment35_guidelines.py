"""Experiment 35 label guidelines: one file per set, generated from the page constants (task 16.8).

The guideline files under ``guidelines/`` are built by ``guidelines35.py`` from
``labelpage35.GUIDANCE``, ``HARD_CASES``, ``CHOICES`` and ``LAYOUT``, so the
page and the written guideline cannot drift apart. A stale or hand-edited file
fails the byte-for-byte check. Each rule quoted from the pre-registration or
the protocol must still appear there word for word.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from tests._exp35_fixtures import FOLDER, load

labelpage35 = load("labelpage35")
claimkinds35 = load("claimkinds35")
guidelines35 = load("guidelines35")

NAMES = ("claim_kinds", "faithfulness", "correctness", "part2_correctness")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _file(name: str) -> str:
    return (FOLDER / "guidelines" / f"{name}.md").read_text(encoding="utf-8")


def test_there_is_one_guideline_per_registered_set() -> None:
    assert tuple(guidelines35.SETS) == NAMES
    assert sorted(p.name for p in (FOLDER / "guidelines").glob("*.md")) == sorted(
        f"{n}.md" for n in NAMES
    )


@pytest.mark.parametrize("name", NAMES)
def test_committed_guideline_matches_the_generator_byte_for_byte(name: str) -> None:
    assert _file(name) == guidelines35.render(name)


def test_write_all_regenerates_the_committed_files(tmp_path: Path) -> None:
    written = guidelines35.write_all(tmp_path)
    assert [p.name for p in written] == [f"{n}.md" for n in NAMES]
    for path in written:
        assert path.read_bytes() == (FOLDER / "guidelines" / path.name).read_bytes()
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("name", NAMES)
def test_guideline_holds_every_rule_example_and_hard_case_of_its_page_set(name: str) -> None:
    text = _file(name)
    page_set = guidelines35.SETS[name]
    shown = dict(labelpage35.CHOICES[page_set])
    for value, rule, example in labelpage35.GUIDANCE[page_set]:
        assert f"### {shown[value]} (`{value}`)" in text
        assert rule in text and example in text
    for case in labelpage35.HARD_CASES[page_set]:
        assert f"- {case}\n" in text
    for _, label, _ in labelpage35.LAYOUT[page_set]:
        assert label in text


@pytest.mark.parametrize("name", NAMES)
def test_every_quoted_rule_is_still_word_for_word_in_its_source(name: str) -> None:
    quotes = guidelines35.QUOTES[name]
    assert quotes
    text = _file(name)
    for source, quote in quotes:
        assert source in ("preregistration.md", "protocol.md")
        assert _norm(quote) in _norm((FOLDER / source).read_text(encoding="utf-8")), quote
        assert quote in text


def test_claim_kind_guideline_states_the_mixed_rule_as_registered() -> None:
    prereg = _norm((FOLDER / "preregistration.md").read_text(encoding="utf-8"))
    section = prereg.split("### 11.1 Models", 1)[1].split("### 11.2", 1)[0]
    rule = re.search(
        r"Claim-kind rule \(owner decision [^)]*\): .*?not even about what a source contains\.",
        section,
    )
    assert rule is not None
    text = _file("claim_kinds")
    assert rule.group(0) in _norm(text)
    shared = "states no checkable fact, not even about what a source contains"
    assert shared in _norm(claimkinds35.PROMPT) and shared in text


#: The two rules the owner added after the classifier gate failed (2026-11-24, pre-freeze).
CLARIFICATIONS = (
    "a sentence that says the sources do not state something is refusal, even when it also "
    "names part of the question or the user's own setup, as long as it states no fact about "
    "a source",
    'a sentence that says what a source covers or is about, even "unrelated topics", is '
    "factual or mixed, never refusal",
)


def test_the_classifier_and_the_labeller_follow_the_two_gate_fail_rules() -> None:
    prompt = _norm(claimkinds35.PROMPT).lower()
    hard = [_norm(h).lower() for h in labelpage35.HARD_CASES["claim_kinds"]]
    text = _norm(_file("claim_kinds")).lower()
    for rule in CLARIFICATIONS:
        assert rule in prompt, rule
        assert any(rule in case for case in hard), rule
        assert rule in text, rule


def test_faithfulness_guideline_follows_the_aggrefact_task_definition() -> None:
    text = _file("faithfulness")
    assert "LLM-AggreFact task definition (MiniCheck)" in text
    assert "Full answer" not in text  # the checker sees no full answer, nor does the labeller


def test_part2_guideline_reuses_the_correctness_rules_and_hides_the_system() -> None:
    text = _file("part2_correctness")
    assert guidelines35.SETS["part2_correctness"] == "correctness"
    assert text.startswith("# Label guideline: Part 2 correctness\n")
    assert "system identity is hidden" in text
    assert "Reference answer" in text


@pytest.mark.parametrize("name", NAMES)
def test_guideline_names_its_generator_and_has_no_em_dash(name: str) -> None:
    text = _file(name)
    assert "guidelines35.py" in text and "Do not edit this file by hand" in text
    assert "\u2014" not in text
