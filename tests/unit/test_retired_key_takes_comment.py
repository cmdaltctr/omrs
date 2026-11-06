"""A removed retired key takes its own comment (change cuts-follow-ups, D3).

``remove_value(..., with_comment=True)`` also removes the ``//`` comment lines
directly above the member. It stops at a blank line, a line that holds code, or
a commented-out key line. The page write turns it on for retired keys only.

Every test points ``OMRS_CONFIG_DIR`` at a temporary folder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omrs.config.jsonc_edit import remove_value, set_value
from omrs.config.settings_file import file_revision
from omrs.config.settings_file_write import write_settings
from omrs.config.user_config import parse_jsonc
from omrs.transports.cli.config_template import build_template

# ── remove_value(with_comment=True) ──────────────────────────────────────


def test_one_comment_line_above_goes() -> None:
    text = '{\n  "a": 1,\n  // about b\n  "b": 2,\n  "c": 3\n}\n'
    out = remove_value(text, ("b",), with_comment=True)
    assert out == '{\n  "a": 1,\n  "c": 3\n}\n'


def test_two_description_lines_above_go() -> None:
    text = '{\n  "a": 1,\n  // about b\n  // more about b\n  "b": 2,\n  "c": 3\n}\n'
    assert remove_value(text, ("b",), with_comment=True) == '{\n  "a": 1,\n  "c": 3\n}\n'


def test_the_last_member_and_its_comment_go() -> None:
    text = '{\n  "a": 1,\n  // about b\n  "b": 2\n}\n'
    out = remove_value(text, ("b",), with_comment=True)
    assert out == '{\n  "a": 1\n}\n'
    assert parse_jsonc(out) == {"a": 1}


def test_a_commented_out_key_line_above_stays() -> None:
    text = '{\n  // "x": 9,\n  // about b\n  "b": 2\n}\n'
    assert remove_value(text, ("b",), with_comment=True) == '{\n  // "x": 9,\n}\n'


def test_a_blank_line_stops_the_removal() -> None:
    text = '{\n  "a": 1,\n  // about a group\n\n  // about b\n  "b": 2,\n  "c": 3\n}\n'
    out = remove_value(text, ("b",), with_comment=True)
    assert out == '{\n  "a": 1,\n  // about a group\n\n  "c": 3\n}\n'


def test_a_comment_on_the_line_of_another_member_stays() -> None:
    text = '{\n  "a": 1, // note on a\n  // about b\n  "b": 2,\n  "c": 3\n}\n'
    out = remove_value(text, ("b",), with_comment=True)
    assert out == '{\n  "a": 1, // note on a\n  "c": 3\n}\n'


def test_the_default_call_keeps_every_comment() -> None:
    text = '{\n  "a": 1,\n  // about b\n  "b": 2,\n  "c": 3\n}\n'
    out = remove_value(text, ("b",))
    assert out == '{\n  "a": 1,\n  // about b\n  "c": 3\n}\n'


def test_a_member_with_no_comment_above_is_cut_as_before() -> None:
    text = '{\n  "a": 1,\n  "b": 2,\n  "c": 3\n}\n'
    assert remove_value(text, ("b",), with_comment=True) == remove_value(text, ("b",))


def test_crlf_text_keeps_its_line_ends() -> None:
    text = '{\r\n  "a": 1,\r\n  // about b\r\n  "b": 2\r\n}\r\n'
    assert remove_value(text, ("b",), with_comment=True) == '{\r\n  "a": 1\r\n}\r\n'


def test_the_real_template_layout_keeps_a_neighbours_commented_out_key() -> None:
    """The template has no blank line between entries of a nested block."""
    template = build_template()
    start = template.index('  // "retrieval": {')
    end = template.index("  // },", start)
    block = template[start:end].splitlines()
    leaves = [n for n, line in enumerate(block) if line.lstrip().startswith('// "')][1:]
    first, second = leaves[0], leaves[1]
    # Make the second leaf real. Its description line stays directly above it,
    # and the first leaf stays a commented-out line directly above that.
    key = block[second].lstrip()[len("// ") :].rstrip(",")
    block[second] = "    " + key
    block[0] = '  "retrieval": {'
    text = template[:start] + "\n".join(block) + "\n  }\n" + template[end + len("  // },") :]
    assert parse_jsonc(text)["retrieval"]
    neighbour = block[first].strip()
    description = block[second - 1].strip()
    assert description.startswith("// Environment name:")

    name = key.split(":")[0].strip().strip('"')
    out = remove_value(text, ("retrieval", name), with_comment=True)

    assert neighbour in out
    assert description not in out
    assert name not in parse_jsonc(out)["retrieval"]
    assert out.count("// Environment name:") == text.count("// Environment name:") - 1


# ── through the page write ───────────────────────────────────────────────

RETIRED = (
    "{\n"
    '  "community_seed": 3,\n'
    "  // The old single cut. Replaced by ocr_local_cuts.\n"
    '  "ocr_local_min_confidence": 0.9,\n'
    '  "retrieval": {\n'
    "    // keep me\n"
    '    "top_k": 7\n'
    "  }\n"
    "}\n"
)


@pytest.fixture
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "cfg" / "omrs"
    root.mkdir(parents=True, mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return root


def test_saving_the_cuts_removes_the_retired_key_and_its_comment(folder: Path) -> None:
    (folder / "omrs.jsonc").write_text(RETIRED, encoding="utf-8")
    write_settings({"ocr_local_cuts": {"pp-ocrv6-small": 0.93}}, revision=file_revision(folder))
    out = (folder / "omrs.jsonc").read_text(encoding="utf-8")
    assert "ocr_local_min_confidence" not in out
    assert "The old single cut" not in out
    assert "// keep me" in out
    assert parse_jsonc(out)["ocr_local_cuts"] == {"pp-ocrv6-small": 0.93}


def test_a_plain_clear_keeps_the_comment_above_the_key(folder: Path) -> None:
    (folder / "omrs.jsonc").write_text(RETIRED, encoding="utf-8")
    write_settings({"retrieval.top_k": None}, revision=file_revision(folder))
    out = (folder / "omrs.jsonc").read_text(encoding="utf-8")
    assert "top_k" not in out
    assert "// keep me" in out
    assert "The old single cut" in out


def test_saving_a_reading_list_removes_the_old_key_and_its_comment(folder: Path) -> None:
    text = set_value('{\n  // the old reader\n  "pdf_reader": "pypdf"\n}\n', ("a",), 1)
    (folder / "omrs.jsonc").write_text(text, encoding="utf-8")
    write_settings({"pdf_readers": ["pypdf"]}, revision=file_revision(folder))
    out = (folder / "omrs.jsonc").read_text(encoding="utf-8")
    assert 'pdf_reader"' not in out
    assert "the old reader" not in out
