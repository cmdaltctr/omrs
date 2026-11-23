"""Experiment 35 blind labelling page: design and offline checks (task 8.4 follow-up).

The page is one static file. It loads nothing from the network, shows a title,
guidance and a progress counter per set, builds each cited passage as its own
box, and still shows only the fields of its set.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load

labelpage35 = load("labelpage35")

SETS = ("claim_kinds", "faithfulness", "correctness")
ITEM: dict[str, Any] = {
    "item_id": "i1",
    "question": "What is shown?",
    "claim": "A claim.",
    "passages": ["First passage.", "Second passage."],
    "reference": "A reference.",
    "answer": "An answer.",
}


def _page(tmp_path: Path, set_name: str) -> str:
    path = tmp_path / f"{set_name}.html"
    labelpage35.write_page(path, set_name, [ITEM])
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("set_name", SETS)
def test_page_loads_nothing_from_the_network(tmp_path: Path, set_name: str) -> None:
    text = _page(tmp_path, set_name)
    for banned in ("http://", "https://", "<link", "src=", "@import", "url(", "//cdn"):
        assert banned not in text, banned
    assert re.search(r"<script[^>]*\ssrc", text) is None


@pytest.mark.parametrize("set_name", SETS)
def test_page_shows_the_guidance_of_its_own_set_only(tmp_path: Path, set_name: str) -> None:
    text = _page(tmp_path, set_name)
    assert "<details" in text
    for term, meaning in labelpage35.GUIDANCE[set_name]:
        assert html.escape(term, quote=False) in text
        assert html.escape(meaning, quote=False) in text
    own = [meaning for _, meaning in labelpage35.GUIDANCE[set_name]]
    for other in SETS:
        for _, meaning in labelpage35.GUIDANCE[other]:
            if not any(meaning in mine for mine in own):  # shared wording is allowed
                assert html.escape(meaning, quote=False) not in text


@pytest.mark.parametrize("set_name", SETS)
def test_page_has_title_and_a_polite_progress_counter(tmp_path: Path, set_name: str) -> None:
    text = _page(tmp_path, set_name)
    assert f"<h1>{labelpage35.TITLES[set_name]}</h1>" in text
    assert re.search(r'id="progress"[^>]*aria-live="polite"', text)
    assert 'id="progress-text"' in text and 'id="progress-bar"' in text
    assert 'id="next"' in text and 'id="save"' in text
    assert '<select id="labeller">' in text


def test_guidance_words_follow_the_protocol_wording() -> None:
    claim = dict(labelpage35.GUIDANCE["claim_kinds"])
    assert "no debt securities are listed" in claim["Factual claim"].lower()
    assert "only says the sources do not cover" in claim["Refusal"].lower()
    assert "checkable fact" in claim["Mixed"]
    assert "rarely" in claim["Can't tell"].lower()
    assert set(dict(labelpage35.GUIDANCE["faithfulness"])) == {
        "Supported",
        "Not supported",
        "Can't tell",
    }
    assert set(dict(labelpage35.GUIDANCE["correctness"])) == {
        "Correct",
        "Not correct",
        "Can't tell",
    }


def test_layout_labels_match_the_fields_and_name_the_item_in_plain_words() -> None:
    for set_name in SETS:
        assert [row[0] for row in labelpage35.LAYOUT[set_name]] == list(
            labelpage35.FIELDS[set_name]
        )
    assert ("claim", "Sentence to label", "focus") in labelpage35.LAYOUT["claim_kinds"]
    assert ("claim", "Sentence to label", "focus") in labelpage35.LAYOUT["faithfulness"]
    assert ("answer", "Answer", "focus") in labelpage35.LAYOUT["correctness"]
    assert ("reference", "Reference answer", "context") in labelpage35.LAYOUT["correctness"]


def test_page_data_carries_the_layout_and_no_extra_item_field(tmp_path: Path) -> None:
    text = _page(tmp_path, "faithfulness")
    data = json.loads(re.search(r'id="items">(.*?)</script>', text, re.S).group(1))
    assert data["layout"] == [list(row) for row in labelpage35.LAYOUT["faithfulness"]]
    assert set(data["items"][0]) == {"item_id", "question", "claim", "passages"}


def test_script_builds_each_passage_as_its_own_scrollable_box(tmp_path: Path) -> None:
    text = _page(tmp_path, "faithfulness")
    assert "'passage'" in text  # one element per passage, class passage
    assert "(k + 1)" in text  # "Passage 1", "Passage 2", ...
    assert re.search(r"\.passage\s*\{[^}]*max-height:\s*16em", text)
    assert re.search(r"\.passage\s*\{[^}]*overflow:\s*auto", text)


def test_page_has_segmented_choices_keys_hint_and_a_save_confirmation(tmp_path: Path) -> None:
    text = _page(tmp_path, "claim_kinds")
    assert "type = 'radio'" in text
    assert ":focus-visible" in text and ":checked" in text
    assert re.search(r"\.card\.done\s*\{[^}]*border-color", text)
    assert "confirm(" in text and "unlabelled" in text
    assert "prefers-color-scheme: dark" in text
    assert "J or K" in text and "1 to 4" in text
    assert "max-width: 820px" in text


def test_page_keeps_the_saved_format_filename_and_draft_guard(tmp_path: Path) -> None:
    text = _page(tmp_path, "correctness")
    assert "{set: data.set, labeller: who, labels: mine}" in text
    assert "data.set + '-' + who + '.json'" in text
    for at in (m.start() for m in re.finditer("localStorage", text)):
        assert re.search(r"try \{[^}]*$", text[:at])
