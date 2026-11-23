"""Experiment 35 blind labelling page: design, rendering and offline checks (task 8.4 follow-up).

The page follows the Experiment 34 review page: a sticky bar with a progress
pill, one collapsible card per item (one open at a time), context on the left
and the sentence to judge with choice chips on the right. Answers and passages
are rendered from Markdown in Python: fenced code becomes a code block, inline
Markdown renders in every text field, all text is escaped, and the target
sentence is marked in the full answer. The page loads nothing from the network
and shows only the fields of its set.
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
labelrender35 = load("labelrender35")

SETS = ("claim_kinds", "faithfulness", "correctness")
ANSWER = (
    "Intro sentence about **CO2** [1].\n\n"
    "**Hypercapnia** is the elevation of CO2 in the blood [2]. It costs $5 [1].\n\n"
    "```python\nx = a * b * c\nprint(x)\n```\n"
)
ITEM: dict[str, Any] = {
    "item_id": "i1",
    "question": "What is **shown**?",
    "claim": "**Hypercapnia** is the elevation of CO2 in the blood.",
    "answer": ANSWER,
    "passages": [{"ordinal": 2, "text": "Passage two with `code`."}],
    "reference": "A reference.",
}
FAITH_ITEM = {**ITEM, "passages": ["First passage.", "Second passage."]}


def _page(tmp_path: Path, set_name: str, item: dict[str, Any] | None = None) -> str:
    path = tmp_path / f"{set_name}.html"
    chosen = item or (FAITH_ITEM if set_name == "faithfulness" else ITEM)
    labelpage35.write_page(path, set_name, [chosen])
    return path.read_text(encoding="utf-8")


def _visible(text: str) -> str:
    """The page without its JSON data block (what the browser renders)."""
    return re.sub(r'<script type="application/json" id="items">.*?</script>', "", text, flags=re.S)


def _data(text: str) -> dict[str, Any]:
    return json.loads(re.search(r'id="items">(.*?)</script>', text, re.S).group(1))


@pytest.mark.parametrize("set_name", SETS)
def test_page_loads_nothing_from_the_network(tmp_path: Path, set_name: str) -> None:
    text = _page(tmp_path, set_name)
    for banned in ("http://", "https://", "<link", "src=", "@import", "url(", "//cdn", "fetch("):
        assert banned not in text, banned
    assert re.search(r"<script[^>]*\ssrc", text) is None


@pytest.mark.parametrize("set_name", SETS)
def test_page_shows_the_guidance_of_its_own_set_only(tmp_path: Path, set_name: str) -> None:
    text = _page(tmp_path, set_name)
    assert '<p class="intro">' in text
    for term, meaning in labelpage35.GUIDANCE[set_name]:
        assert html.escape(term, quote=False) in text
        assert html.escape(meaning, quote=False) in text
    own = [meaning for _, meaning in labelpage35.GUIDANCE[set_name]]
    for other in SETS:
        for _, meaning in labelpage35.GUIDANCE[other]:
            if not any(meaning in mine for mine in own):  # shared wording is allowed
                assert html.escape(meaning, quote=False) not in text


@pytest.mark.parametrize("set_name", SETS)
def test_bar_has_title_progress_pill_and_controls(tmp_path: Path, set_name: str) -> None:
    text = _page(tmp_path, set_name)
    assert f"<h1>{labelpage35.TITLES[set_name]}</h1>" in text
    assert re.search(r'id="progress"[^>]*aria-live="polite"', text)
    assert re.search(r"#progress\.ok\s*\{[^}]*background", text)  # green when complete
    for control in ('id="next"', 'id="collapse"', 'id="save"', '<select id="labeller">'):
        assert control in text
    assert "'Done ' + n + ' / ' + total" in text


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


def test_layout_covers_the_fields_and_names_them_in_plain_words() -> None:
    for set_name in SETS:
        assert {row[0] for row in labelpage35.LAYOUT[set_name]} == set(labelpage35.FIELDS[set_name])
    assert labelpage35.FIELDS["claim_kinds"] == ("question", "claim", "answer", "passages")
    assert ("claim", "Sentence to label", "focus") in labelpage35.LAYOUT["claim_kinds"]
    assert ("answer", "Full answer", "answer") in labelpage35.LAYOUT["claim_kinds"]
    assert ("claim", "Sentence to label", "focus") in labelpage35.LAYOUT["faithfulness"]
    assert ("answer", "Answer", "focus") in labelpage35.LAYOUT["correctness"]
    assert ("reference", "Reference answer", "context") in labelpage35.LAYOUT["correctness"]


@pytest.mark.parametrize("set_name", SETS)
def test_page_data_carries_only_the_fields_of_its_set(tmp_path: Path, set_name: str) -> None:
    data = _data(_page(tmp_path, set_name))
    assert set(data["items"][0]) == {"item_id", *labelpage35.FIELDS[set_name]}


def test_code_fences_render_as_code_blocks_not_prose() -> None:
    out = labelrender35.render_markdown("Use this:\n\n```python\nx = a * b * c\n```\nThen `y`.")
    block = re.search(r'<pre class="code" data-lang="python"><code>(.*?)</code></pre>', out, re.S)
    assert block is not None
    assert block.group(1) == "x = a * b * c"  # no <em> from the asterisks, no prose wrap
    assert "<p>x = a" not in out
    assert "<code>y</code>" in out
    unclosed = labelrender35.render_markdown("```\nraw <b>\n")
    assert '<pre class="code"><code>raw &lt;b&gt;</code></pre>' in unclosed


def test_markdown_keeps_headings_lists_tables_and_literal_dollars() -> None:
    out = labelrender35.render_markdown(
        "# Title\n- one\n- two\n\n3. three\n4. four\n\n| a | b |\n|---|---|\n| $1 | $2 |\n"
        "Costs $5 and $6 [1, 2]. See [docs](x)."
    )
    assert "<h3>Title</h3>" in out
    assert "<ul><li>one</li><li>two</li></ul>" in out
    assert '<ol start="3"><li>three</li><li>four</li></ol>' in out
    assert "<th>a</th>" in out and "<td>$1</td>" in out
    assert "Costs $5 and $6" in out and "katex" not in out.lower()
    assert '<span class="cite">[1, 2]</span>' in out
    assert "See docs." in out  # link text only


def test_all_text_is_escaped_and_no_html_from_the_data_runs(tmp_path: Path) -> None:
    bad = "<script>alert(1)</script><img onerror=x>"
    item = {
        **ITEM,
        "question": bad,
        "claim": bad,
        "answer": bad + " [1].",
        "passages": [{"ordinal": 1, "text": bad}],
    }
    visible = _visible(_page(tmp_path, "claim_kinds", item))
    assert "<script>alert" not in visible and "<img" not in visible
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in visible
    data = _page(tmp_path, "claim_kinds", item)
    assert "</script><img" not in data  # the JSON block cannot close its own tag


def test_inline_markdown_renders_in_every_text_field(tmp_path: Path) -> None:
    visible = _visible(_page(tmp_path, "claim_kinds"))
    focus = re.search(r'<p class="focus">(.*?)</p>', visible, re.S)
    assert focus is not None
    assert focus.group(1).startswith("<strong>Hypercapnia</strong> is")
    assert "**" not in visible  # never literal asterisks
    assert "What is <strong>shown</strong>?" in visible
    assert re.search(r"\.focus\s*\{[^}]*font-weight:\s*400", visible)


def test_target_sentence_is_marked_in_the_full_answer(tmp_path: Path) -> None:
    visible = _visible(_page(tmp_path, "claim_kinds"))
    mark = re.search(r'<mark class="target">(.*?)</mark>', visible, re.S)
    assert mark is not None
    assert mark.group(1).startswith("<strong>Hypercapnia</strong> is the elevation")
    assert "Intro sentence" not in mark.group(1) and "costs" not in mark.group(1)
    listed = labelrender35.render_markdown(
        labelrender35.mark_claim("- **A** b [1].\n- c [1].", "- **A** b.")
    )
    assert '<ul><li><mark class="target"><strong>A</strong> b <span class="cite">' in listed
    assert labelrender35.mark_claim("text [1].", "absent") == "text [1]."


def test_answer_and_passages_reach_the_claim_kind_page(tmp_path: Path) -> None:
    visible = _visible(_page(tmp_path, "claim_kinds"))
    assert "Full answer" in visible
    assert "Passage [2]" in visible
    assert "Passage two with <code>code</code>." in visible
    assert '<pre class="code" data-lang="python"><code>x = a * b * c' in visible
    faith = _visible(_page(tmp_path, "faithfulness"))
    assert "Passage 1" in faith and "Passage 2" in faith and "Full answer" not in faith


def test_one_card_is_open_at_a_time_and_scrolls_into_view(tmp_path: Path) -> None:
    text = _page(tmp_path, "claim_kinds")
    assert '<details class="page" data-i="0">' in text
    assert "if (o !== card && o.open) { o.open = false; }" in text
    assert "card.scrollIntoView({block: 'start'})" in text
    assert "pane.scrollTop" in text  # the marked sentence scrolls into view in its pane


def test_card_has_chips_keys_note_clear_and_view_toggle(tmp_path: Path) -> None:
    text = _page(tmp_path, "claim_kinds")
    assert text.count('<label class="chip"><input type="radio"') == 4
    assert "<kbd>1</kbd>" in text and "<kbd>4</kbd>" in text
    assert 'class="note"' in text and 'class="clear"' in text
    assert 'data-v="md">Rendered</button>' in text and 'data-v="raw">Raw</button>' in text
    assert "confirm(" in text and "unlabelled" in text
    assert "key === 'j'" in text and "key === 'k'" in text
    assert "1 to 4" in text and "prefers-color-scheme" in text
    assert "@media (max-width:900px)" in text  # one column on small screens


def test_page_keeps_the_saved_format_filename_and_draft_guard(tmp_path: Path) -> None:
    text = _page(tmp_path, "correctness")
    assert "{set: data.set, labeller: who, labels: mine, notes: kept}" in text
    assert "data.set + '-' + who + '.json'" in text
    uses = [m.start() for m in re.finditer("localStorage", text)]
    assert uses
    for at in uses:
        assert re.search(r"try \{[^}]*$", text[:at])
    assert "name=" not in text.lower().replace("input.name", "")  # no name field


def test_read_labels_ignores_the_optional_notes_map(tmp_path: Path) -> None:
    path = tmp_path / "labels.json"
    path.write_text(
        json.dumps(
            {
                "set": "claim_kinds",
                "labeller": "L1",
                "labels": {"i1": "factual"},
                "notes": {"i1": "long sentence"},
            }
        ),
        encoding="utf-8",
    )
    assert labelpage35.read_labels(path, "claim_kinds", ["i1"]) == ("L1", {"i1": "factual"})


def test_bold_around_inline_code_renders_without_literal_asterisks() -> None:
    out = labelrender35.render_inline("**`response_metadata`** and **a `b` c**")
    assert out == (
        "<strong><code>response_metadata</code></strong> and <strong>a <code>b</code> c</strong>"
    )
    assert labelrender35.render_inline("`**kwargs`") == "<code>**kwargs</code>"
    # A claim cut out of a bold span: the unpaired markers are dropped, never shown.
    split = labelrender35.render_inline("3.0% as reported**, while **intl fell 0.6%")
    assert split == "3.0% as reported, while intl fell 0.6%"


def test_passages_that_are_source_code_render_as_code_blocks() -> None:
    source = (
        "def f(x):\n    y = g(x)\n    # comment, not a heading\n"
        "    return {\n        'a': y,\n    }\n"
    )
    out = labelrender35.render_passage(source)
    assert out.startswith('<pre class="code"><code>def f(x):\n    y = g(x)')
    assert "<h3>" not in out
    prose = "Hypercapnia is raised CO2.\nIt harms immunity.\nSee table 2."
    assert labelrender35.render_passage(prose).startswith("<p>Hypercapnia")
    meta = '---\nfreshstack_id: "x.ts_0_9"\nsource_url: "repo/a/b.ts"\n---\n\nconst a = 1;\n'
    out = labelrender35.render_passage(meta)
    assert '<pre class="code meta"><code>freshstack_id: "x.ts_0_9"' in out
    assert '<pre class="code" data-lang="ts"><code>const a = 1;</code></pre>' in out
    doc = '---\nsource_url: "repo/docs/a.mdx"\n--- # Title\nSome **prose**.'
    out = labelrender35.render_passage(doc)
    assert "<h3>Title</h3>" in out and "<strong>prose</strong>" in out


def test_each_choice_has_its_own_selected_colour() -> None:
    # Owner request 2026-11-23: factual green, refusal red, mixed blue, can't tell orange.
    import labelpage_assets35

    css = labelpage_assets35.CSS
    for value, colour in (
        ("factual", "#1f9d55"),
        ("refusal", "#d64545"),
        ("mixed", "#2f6fdb"),
        ("cant_tell", "#e07b00"),
    ):
        assert colour in css.split(f"input[value={value}]", 1)[1].split("}", 1)[0]
    assert "input:checked+span{background:var(--pick)" in css


def test_a_labelled_card_turns_green_with_a_status_pill() -> None:
    # Owner request 2026-11-23: labelled accordion header green, status as a pill.
    import labelpage_assets35

    css = labelpage_assets35.CSS
    pill = css.split("details.page[data-done] .pstat{", 1)[1].split("}", 1)[0]
    assert "background:var(--ok)" in pill and "border-radius:999px" in pill
    assert "details.page[data-done]{border-color:var(--ok)}" in css
    assert "details.page[data-done]>summary{background:" in css
