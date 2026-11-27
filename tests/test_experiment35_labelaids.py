"""Experiment 35 labelling page: reading aid, highlights, audit set, model-labeller copy.

The reading aid marks words and numbers shared by the item text and the text it
is judged against (code only, no model). Labeller highlights are a second mark.
The relevance audit set shows the question, the reference answer and the unit
text, never an arm. The model-labeller copy keeps its draft apart from humans.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load

labelpage35 = load("labelpage35")
labelaids35 = load("labelaids35")
labelpage_assets35 = load("labelpage_assets35")

AUDIT_ITEM: dict[str, Any] = {
    "item_id": "a1",
    "dataset": "financebench",
    "qid": "q-7",
    "question": "What was the 2019 revenue?",
    "reference": "Revenue was $1,234 in 2019.",
    "unit_text": "The 2019 revenue reached $1,234 million.",
    "arm": "hybrid-on-512",
}
FAITH = {
    "item_id": "f1",
    "question": "Q?",
    "claim": "The device weighs 2 kg.",
    "passages": ["Weight: 2 kg."],
}
CORRECT = {"item_id": "c1", "question": "Q?", "reference": "Paris.", "answer": "Paris."}
ITEMS = {"relevance_audit": AUDIT_ITEM, "faithfulness": FAITH, "correctness": CORRECT}


def _page(tmp_path: Path, set_name: str, **kw: Any) -> str:
    path = tmp_path / f"{set_name}.html"
    labelpage35.write_page(path, set_name, [ITEMS[set_name]], **kw)
    return path.read_text(encoding="utf-8")


def _data(text: str) -> dict[str, Any]:
    return json.loads(re.search(r'id="items">(.*?)</script>', text, re.S).group(1))


def _node(code: str) -> Any:
    """Run *code* in node, with the aid core functions loaded, and return its JSON output."""
    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    program = labelaids35.AID_CORE_JS + "\n" + code
    done = subprocess.run(
        ["node", "-e", program], capture_output=True, text=True, check=True, timeout=30
    )
    return json.loads(done.stdout)


# --- Reading aid: matching rules ------------------------------------------------------


def test_shared_words_match_exactly_after_lower_casing() -> None:
    out = _node(
        "console.log(JSON.stringify([...aidShared('The Device WEIGHS 2 kg', "
        "'device weighs 2 KG and more')].sort()));"
    )
    assert out == ["2", "device", "weighs"]


def test_numbers_stay_whole() -> None:
    out = _node(
        "console.log(JSON.stringify([...aidShared('Paid $1,234 in 2019 at 3.5 percent', "
        "'It was $1,234, in 2019, rate 3.5 percent; 1 and 234 and 3 and 5')].sort()));"
    )
    assert out == ["$1,234", "2019", "3.5", "percent"]


def test_stop_words_and_short_tokens_are_skipped_but_short_numbers_are_kept() -> None:
    out = _node(
        "console.log(JSON.stringify([...aidShared('the and of an is at 7 ox cat', "
        "'the and of an is at 7 ox cat')].sort()));"
    )
    assert out == ["7", "cat"]


def test_segments_cut_the_text_into_hits_and_gaps_without_losing_a_character() -> None:
    out = _node(
        "const s = new Set(['weighs','2']);"
        "const seg = aidSegments('It weighs 2 kg.', s);"
        "console.log(JSON.stringify({text: seg.map(x => x.t).join(''), "
        "hits: seg.filter(x => x.hit).map(x => x.t)}));"
    )
    assert out == {"text": "It weighs 2 kg.", "hits": ["weighs", "2"]}


# --- Reading aid: page parts ----------------------------------------------------------


@pytest.mark.parametrize("set_name", sorted(ITEMS))
def test_each_item_has_a_reading_aid_button_that_starts_on(tmp_path: Path, set_name: str) -> None:
    text = _page(tmp_path, set_name)
    button = re.search(r'<button[^>]*class="aidbtn"[^>]*>(.*?)</button>', text, re.S)
    assert button is not None
    assert "Reading aid: on" in button.group(0)
    assert 'aria-pressed="true"' in button.group(0)
    assert "aidOn" in labelpage_assets35.SCRIPT


@pytest.mark.parametrize(
    ("set_name", "item_role", "against_role"),
    [
        ("faithfulness", r'<div data-aid="item"><p class="focus">', 'data-aid="against"'),
        ("correctness", 'data-aid="item"', 'class="blk ctx"'),
        ("relevance_audit", 'data-aid="item"', 'data-aid="against"'),
    ],
)
def test_item_text_and_judged_against_text_carry_aid_roles(
    tmp_path: Path, set_name: str, item_role: str, against_role: str
) -> None:
    text = _page(tmp_path, set_name)
    assert re.search(item_role, text)
    assert against_role in text
    assert text.count('data-aid="item"') == 1
    assert text.count('data-aid="against"') >= 1


def test_faithfulness_passages_are_the_judged_against_text(tmp_path: Path) -> None:
    text = _page(tmp_path, "faithfulness")
    assert re.search(r'<div class="outwrap"[^>]*data-aid="against"', text)


def test_aid_marks_have_their_own_colour_apart_from_highlights() -> None:
    css = labelaids35.CSS_AIDS
    aid = re.search(r"mark\.aid\{[^}]*background:(#[0-9a-f]{6})", css).group(1)
    hl = re.search(r"mark\.hl\{[^}]*background:(#[0-9a-f]{6})", css).group(1)
    assert aid != hl
    assert aid != "#ffe08a"
    assert hl != "#ffe08a"


def test_aid_state_is_saved_with_the_labels_and_defaults_to_on() -> None:
    script = labelpage_assets35.SCRIPT
    assert "reading_aid" in script
    assert "aid[id] = aidOn[id] !== false;" in script
    assert "Object.assign(base, extraSave(mine));" in script


def test_the_aid_works_on_rendered_text_in_the_page_without_the_network() -> None:
    script = labelpage_assets35.SCRIPT
    assert "createTreeWalker" in script
    assert "aidSegments(" in script
    for banned in ("http://", "https://", "fetch(", "XMLHttpRequest", "src="):
        assert banned not in script
        assert banned not in labelaids35.CSS_AIDS


# --- Labeller highlights --------------------------------------------------------------


def test_each_item_has_a_highlight_button_and_the_h_key(tmp_path: Path) -> None:
    text = _page(tmp_path, "faithfulness")
    assert re.search(r'<button[^>]*class="hlbtn"[^>]*>Highlight', text)
    script = labelpage_assets35.SCRIPT
    assert "key === 'h'" in script or "e.key === 'h'" in script


def test_highlights_are_saved_as_area_text_and_start_and_restored_from_the_draft() -> None:
    script = labelpage_assets35.SCRIPT
    assert "marks[id] = highlights[id];" in script
    assert "out = {reading_aid: aid, highlights: marks}" in script
    assert "area:" in script and "text:" in script and "start:" in script
    assert "store + '-hl'" in script
    assert "JSON.parse(localStorage.getItem(store + '-hl')" in script


def test_a_click_on_a_highlight_removes_it() -> None:
    script = labelpage_assets35.SCRIPT
    assert "closest('mark.hl')" in script
    assert ".splice(" in script


def test_highlights_apply_to_rendered_markdown_blocks_by_text_offset() -> None:
    script = labelpage_assets35.SCRIPT
    assert "surroundContents" in script
    assert "'.outwrap .md'" in script


# --- Instructions panel ---------------------------------------------------------------


@pytest.mark.parametrize("set_name", sorted(ITEMS))
def test_instructions_explain_the_reading_aid_and_highlighting(
    tmp_path: Path, set_name: str
) -> None:
    text = _page(tmp_path, set_name)
    panel = re.search(r'<details class="panel" id="instructions".*?</details>', text, re.S)
    assert panel is not None
    body = panel.group(0)
    assert "Reading aid" in body
    assert "Highlight" in body
    assert "press H" in body
    assert "Click a highlight to remove it" in body


# --- Audit set ------------------------------------------------------------------------


def test_audit_set_choices_and_question(tmp_path: Path) -> None:
    text = _page(tmp_path, "relevance_audit")
    assert [c[0] for c in _data(text)["choices"]] == ["relevant", "not_relevant", "cant_tell"]
    assert "Does this passage contain information that the reference answer uses?" in text
    for shown in ("Relevant", "Not relevant", "Can&#x27;t tell", "Can't tell"):
        if shown in text:
            break
    else:  # pragma: no cover
        pytest.fail("no Can't tell chip")


def test_audit_page_shows_question_reference_and_unit_text(tmp_path: Path) -> None:
    text = _page(tmp_path, "relevance_audit")
    for part in ("What was the 2019 revenue?", "Revenue was $1,234", "reached $1,234 million"):
        assert part in text


def test_audit_page_never_shows_an_arm_or_dataset_keys(tmp_path: Path) -> None:
    text = _page(tmp_path, "relevance_audit")
    data = _data(text)
    assert set(data["items"][0]) == {"item_id", "question", "reference", "unit_text"}
    for banned in ("hybrid-on-512", "financebench", "q-7", "arm"):
        assert not re.search(rf"\b{re.escape(banned)}\b", text)


def test_audit_page_loads_nothing_from_the_network(tmp_path: Path) -> None:
    text = _page(tmp_path, "relevance_audit")
    for banned in ("http://", "https://", "<link", "src=", "@import", "url(", "//cdn", "fetch("):
        assert banned not in text


def test_audit_set_is_known_to_every_page_table() -> None:
    for table in ("CHOICES", "FIELDS", "TITLES", "LAYOUT", "GUIDANCE", "HARD_CASES"):
        assert "relevance_audit" in getattr(labelpage35, table)


# --- Model-labeller copy --------------------------------------------------------------


def test_model_copy_keeps_drafts_under_a_separate_key_and_says_so(tmp_path: Path) -> None:
    human = _page(tmp_path, "faithfulness")
    model = _page(tmp_path, "faithfulness", model_labeller=True)
    assert _data(human).get("draft_suffix", "") == ""
    assert _data(model)["draft_suffix"] == "-model"
    assert "Model labeller copy" in model
    assert "Model labeller copy" not in human
    assert "data.draft_suffix" in labelpage_assets35.SCRIPT


def test_command_line_flag_builds_the_model_copy(tmp_path: Path) -> None:
    items = tmp_path / "items.json"
    items.write_text(json.dumps([FAITH]), encoding="utf-8")
    out = tmp_path / "model.html"
    labelpage35.main(
        ["--set", "faithfulness", "--items", str(items), "--out", str(out), "--model-labeller"]
    )
    assert "Model labeller copy" in out.read_text(encoding="utf-8")
    plain = tmp_path / "human.html"
    labelpage35.main(["--set", "faithfulness", "--items", str(items), "--out", str(plain)])
    assert "Model labeller copy" not in plain.read_text(encoding="utf-8")


def test_new_and_changed_page_files_stay_within_500_lines() -> None:
    folder = Path(labelpage35.__file__).parent
    for name in ("labelpage35.py", "labelpage_assets35.py", "labelaids35.py", "labelrender35.py"):
        assert len((folder / name).read_text(encoding="utf-8").splitlines()) <= 500
