"""Tests for the dots-mocr engine that need no model or server.

The engine runs dots.mocr on a llama.cpp server (change
dots-mocr-llamacpp-backend, task 4.2). The layout converter, the prompt and
the parse loop are pure Python. They run here, in the main OMRS environment,
on the committed Experiment 34 fixtures and on stubs. No weights, no server,
no network. The PyTorch engine, its model-code patches and its code-hash
check were removed at cut-over (task 4.1), and their tests went with them.

The server, the request and the runtime address are tested in
``test_ocr_dots_llamacpp_engine.py`` against the shared fake server.
"""

from __future__ import annotations

import hashlib
import importlib
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.ocr_worker.isolation import isolated_worker_modules

REPO_ROOT = Path(__file__).resolve().parent.parent
DOTS_DIR = REPO_ROOT / "ocr-workers" / "engines" / "dots-mocr"
DOTS_SRC = DOTS_DIR / "src"
CORE_SRC = REPO_ROOT / "ocr-workers" / "core" / "src"
FIXTURES = REPO_ROOT / "experiments" / "34-worker-sample-review-2026-09-19" / "output" / "dots_mocr"


@pytest.fixture
def dots(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Import the dots-mocr package modules from source."""
    monkeypatch.syspath_prepend(str(CORE_SRC))
    monkeypatch.syspath_prepend(str(DOTS_SRC))
    with isolated_worker_modules():
        yield importlib.import_module("omrs_ocr_dots_mocr")


def _layout(dots: Any) -> Any:
    return importlib.import_module("omrs_ocr_dots_mocr.layout")


def _raw(doc: str, page: int) -> str:
    return (FIXTURES / doc / f"p{page:03d}.raw.txt").read_text(encoding="utf-8")


# ── layout.py on the committed fixtures (task 3.3) ─────────────────────────


def test_eq01_p11_has_four_display_blocks_and_no_doubling(dots: Any) -> None:
    """``eq01`` p11: exactly 4 display blocks, each with one ``$$`` pair."""
    layout = _layout(dots)
    markdown, reason = layout.page_markdown(_raw("eq01", 11), hit_token_cap=False)
    assert reason is None
    blocks = re.findall(r"^\$\$\n(.*?)\n\$\$$", markdown, flags=re.S | re.M)
    assert len(blocks) == 4
    assert markdown.count("$$") == 8, "one opening and one closing $$ per block"
    assert "$$$$" not in markdown
    for block in blocks:
        assert not block.strip().startswith("$$")
        assert not block.strip().endswith("$$")


def test_bd03_p2_drops_page_header_and_footer(dots: Any) -> None:
    """``bd03`` p2: no "PLOS One" header, no DOI footer line."""
    layout = _layout(dots)
    markdown, reason = layout.page_markdown(_raw("bd03", 2), hit_token_cap=False)
    assert reason is None
    assert markdown.strip()
    assert "PLOS One" not in markdown
    assert "doi.org" not in markdown.lower()


def test_every_fixture_converts_without_furniture(dots: Any) -> None:
    """Every committed raw page parses and loses its header and footer text."""
    layout = _layout(dots)
    raws = sorted(FIXTURES.glob("*/p*.raw.txt"))
    assert len(raws) >= 40
    for raw_path in raws:
        raw = raw_path.read_text(encoding="utf-8")
        cells = layout.parse_layout(raw)
        assert cells is not None, raw_path
        markdown, reason = layout.page_markdown(raw, hit_token_cap=False)
        assert reason is None, raw_path
        for cell in cells:
            text = str(cell.get("text") or "").strip()
            if cell.get("category") in ("Page-header", "Page-footer") and len(text) > 12:
                kept = [c for c in cells if c.get("category") not in layout.DROPPED_CATEGORIES]
                if any(text in str(c.get("text") or "") for c in kept):
                    continue  # the same words also sit in body text
                assert text not in markdown, (raw_path, text)


@pytest.mark.parametrize(
    "formula",
    ["x^2", "$$x^2$$", "$$\nx^2\n$$", "$$ $$x^2$$ $$", "\\[x^2\\]"],
)
def test_formula_gets_exactly_one_pair(dots: Any, formula: str) -> None:
    """Spec: a formula already wrapped in ``$$`` keeps exactly one pair."""
    layout = _layout(dots)
    markdown = layout.cells_to_markdown([{"category": "Formula", "text": formula}])
    assert markdown == "$$\nx^2\n$$\n"


def test_headings_tables_and_pictures(dots: Any) -> None:
    """Title and section headers become headings; tables keep HTML; pictures drop."""
    layout = _layout(dots)
    markdown = layout.cells_to_markdown(
        [
            {"category": "Title", "text": "# The Title"},
            {"category": "Section-header", "text": "## 1 Intro"},
            {"category": "Table", "text": "<table><tr><td>1</td></tr></table>"},
            {"category": "Picture", "text": "should vanish"},
            {"category": "Text", "text": ""},
            {"category": "Page-footer", "text": "page 3"},
        ]
    )
    assert markdown == "# The Title\n\n## 1 Intro\n\n<table><tr><td>1</td></tr></table>\n"


def test_token_cap_page_is_empty(dots: Any) -> None:
    """Spec: a page that reached the token limit returns empty Markdown."""
    layout = _layout(dots)
    assert layout.page_markdown(_raw("eq01", 11), hit_token_cap=True) == ("", "token_cap")


@pytest.mark.parametrize("raw", ['[{"category": "Text", "text": "cut', "not json", "42"])
def test_unparsable_page_is_empty(dots: Any, raw: str) -> None:
    """Truncated or non-list JSON returns empty Markdown, never raw output."""
    layout = _layout(dots)
    assert layout.page_markdown(raw, hit_token_cap=False) == ("", "unparsable_layout")


def test_wrapped_layout_object_and_fence_are_accepted(dots: Any) -> None:
    """A fenced JSON object that wraps its cells is unwrapped."""
    layout = _layout(dots)
    raw = '```json\n{"layout": [{"category": "Text", "text": "Hello"}]}\n```'
    assert layout.page_markdown(raw, hit_token_cap=False) == ("Hello\n", None)


# ── engine.py with stubbed seams ───────────────────────────────────────────


def test_engine_parse_converts_each_page_and_empties_bad_ones(
    dots: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``parse`` renders, generates and converts each page; bad pages give ""."""
    engine_mod = importlib.import_module("omrs_ocr_dots_mocr.engine")
    engine = engine_mod.DotsMocrLlamacppEngine()
    outputs = {
        1: (_raw("eq01", 11), 1937),
        2: ("not json", 12),
        3: (_raw("bd03", 2), engine_mod.MAX_NEW_TOKENS),
    }
    rendered: list[int] = []
    monkeypatch.setattr(engine, "render_page", lambda pdf, page: rendered.append(page) or page)
    monkeypatch.setattr(engine, "generate", lambda image: outputs[image])
    pages = engine.parse(tmp_path / "x.pdf", [1, 2, 3])
    assert rendered == [1, 2, 3]
    assert pages[0].count("$$") == 8
    assert pages[1] == ""
    assert pages[2] == "", "a page at the token cap is not usable text"


#: SHA-256 of the upstream ``prompt_layout_all_en`` prompt that Experiments 34
#: and 41 measured. It replaces the D6 copy test, which compared this prompt
#: with the PyTorch engine's copy until cut-over.
PROMPT_SHA256 = "16ff71ac5d218f35e5b3db41240b6e70741498bc099db3fa922ce1ff972e3b2f"


def test_engine_identity_and_render_settings(dots: Any) -> None:
    """The engine is ``dots-mocr`` on llama.cpp, with the measured prompt and render settings."""
    engine_mod = importlib.import_module("omrs_ocr_dots_mocr.engine")
    prompt = importlib.import_module("omrs_ocr_dots_mocr.prompt")
    engine = engine_mod.ENGINE
    assert engine.name == "dots-mocr"
    assert engine.backend_id == "dots_mocr_llamacpp"
    assert "llamacpp-b11941" in engine.pipeline[1]
    assert "torch" not in engine.declared_packages
    assert prompt.RENDER_DPI == 200 and prompt.MIN_LONG_SIDE_PX == 1600
    assert prompt.MAX_NEW_TOKENS == 8192
    assert hashlib.sha256(prompt.PROMPT.encode("utf-8")).hexdigest() == PROMPT_SHA256


def test_manifest_declares_gate_fetch_and_entry_point() -> None:
    """The dots-mocr manifest carries the licence gate, fetch script and entry point."""
    import tomllib

    manifest = tomllib.loads((DOTS_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    gate = {k: v for k, v in manifest["tool"]["omrs-ocr"].items() if k != "runtime"}
    assert gate == {"licence-file": "LICENCE-NOTES.md", "requires-acceptance": True}
    assert manifest["project"]["scripts"]["omrs-ocr-fetch"] == "omrs_ocr_dots_mocr.fetch:main"
    assert manifest["project"]["entry-points"]["omrs.ocr_engine"] == {
        "dots-mocr": "omrs_ocr_dots_mocr.engine:ENGINE"
    }
    assert not [d for d in manifest["project"]["dependencies"] if d.startswith("transformers")]
    notes = (DOTS_DIR / "LICENCE-NOTES.md").read_text(encoding="utf-8")
    for clause in ("3.3(c)", "5.2", "Clause 8", "Clause 9"):
        assert clause in notes
