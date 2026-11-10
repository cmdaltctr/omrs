"""Tests for ``_lib.release_check`` (Experiment 35 tasks 2.10 and 3.4).

uv run --no-sync pytest tests/test_experiment_release_check.py -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from experiments._lib.release_check import check_shareable, main

PASSAGE = (
    "The company reported that net revenue for the fiscal year rose by eleven percent "
    "driven by strong demand in the northern region and lower input costs"
)


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    """A corpus folder with one plain-text and one JSON-lines document."""
    folder = tmp_path / "corpus"
    folder.mkdir()
    (folder / "filing.txt").write_text(f"Header line.\n{PASSAGE}.\nFooter line.\n")
    (folder / "docs.jsonl").write_text(
        json.dumps(
            {
                "id": "d1",
                "text": "Mitochondria produce most of the cell's chemical energy "
                "through oxidative phosphorylation in the inner membrane of the organelle",
            }
        )
        + "\n"
    )
    return folder


@pytest.fixture
def shareable(tmp_path: Path) -> Path:
    """An empty shareable folder."""
    folder = tmp_path / "output" / "shareable"
    folder.mkdir(parents=True)
    return folder


def _rules(findings: list) -> set[str]:
    return {f.rule for f in findings}


# ------------------------------------------------------------- corpus text rule


def test_corpus_text_in_a_shareable_file_fails(shareable: Path, corpus: Path) -> None:
    (shareable / "answers.md").write_text(f"Answer given:\n{PASSAGE}\n")
    findings = check_shareable(shareable, corpus)
    assert _rules(findings) == {"corpus-text"}
    assert findings[0].path == shareable / "answers.md"


def test_corpus_text_matches_across_line_wraps_case_and_spacing(
    shareable: Path, corpus: Path
) -> None:
    words = PASSAGE.upper().split()
    wrapped = "\n".join("  ".join(words[i : i + 5]) for i in range(0, len(words), 5))
    (shareable / "wrapped.txt").write_text(wrapped)
    assert _rules(check_shareable(shareable, corpus)) == {"corpus-text"}


def test_corpus_text_inside_json_strings_fails(shareable: Path, corpus: Path) -> None:
    (shareable / "ctx.json").write_text(json.dumps({"context": "Quote: " + PASSAGE + "\nend"}))
    assert _rules(check_shareable(shareable, corpus)) == {"corpus-text"}


def test_json_escapes_do_not_hide_corpus_text(shareable: Path, corpus: Path) -> None:
    words = PASSAGE.split()
    wrapped = "\n".join(" ".join(words[i : i + 4]) for i in range(0, len(words), 4))
    (shareable / "ctx.json").write_text(json.dumps({"context": wrapped}))
    assert _rules(check_shareable(shareable, corpus)) == {"corpus-text"}


def test_corpus_held_in_jsonl_is_read(shareable: Path, corpus: Path) -> None:
    text = (
        "Mitochondria produce most of the cell's chemical energy through oxidative "
        "phosphorylation in the inner membrane"
    )
    (shareable / "leak.txt").write_text(text)
    assert _rules(check_shareable(shareable, corpus)) == {"corpus-text"}


def test_short_overlap_is_allowed(shareable: Path, corpus: Path) -> None:
    (shareable / "note.md").write_text("net revenue for the fiscal year rose by eleven percent")
    assert check_shareable(shareable, corpus) == []


def test_ngram_length_is_a_parameter(shareable: Path, corpus: Path) -> None:
    (shareable / "note.md").write_text("net revenue for the fiscal year rose by eleven percent")
    assert _rules(check_shareable(shareable, corpus, ngram_words=6)) == {"corpus-text"}


# -------------------------------------------------------------- home-path rule


@pytest.mark.parametrize(
    "text",
    [
        "see /Users/jane/Development/x.py",
        "log at /home/jane/.cache/run.log",
        r"copied from C:\Users\jane\Documents\run.csv",
        '{"path": "C:\\\\Users\\\\jane\\\\Documents\\\\run.csv"}',
    ],
)
def test_home_folder_path_fails(shareable: Path, corpus: Path, text: str) -> None:
    (shareable / "run.log").write_text(text)
    findings = check_shareable(shareable, corpus)
    assert _rules(findings) == {"home-path"}
    assert findings[0].line == 1


def test_home_path_reports_its_line(shareable: Path, corpus: Path) -> None:
    (shareable / "run.log").write_text("ok\nok\nsaved to /Users/jane/out.json\n")
    assert [f.line for f in check_shareable(shareable, corpus)] == [3]


# ------------------------------------------------------------------ clean cases


def test_clean_folder_passes(shareable: Path, corpus: Path) -> None:
    (shareable / "scores.csv").write_text("question_id,score\nq1,0.82\nq2,0.64\n")
    (shareable / "README.md").write_text(
        "Run from ~/work or /Users/<name>/work. Paths use a placeholder, e.g. /home/<user>/x.\n"
    )
    sub = shareable / "nested"
    sub.mkdir()
    (sub / "ids.json").write_text(json.dumps({"ids": ["a1", "b2"]}))
    assert check_shareable(shareable, corpus) == []


def test_empty_shareable_folder_passes(shareable: Path, corpus: Path) -> None:
    assert check_shareable(shareable, corpus) == []


# ------------------------------------------------------------------ stop cases


def test_empty_corpus_stops_instead_of_passing(shareable: Path, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="no readable"):
        check_shareable(shareable, empty)


def test_missing_shareable_folder_stops(tmp_path: Path, corpus: Path) -> None:
    with pytest.raises(FileNotFoundError):
        check_shareable(tmp_path / "absent", corpus)


# -------------------------------------------------------------------------- CLI


def test_main_exits_non_zero_on_a_finding(
    shareable: Path, corpus: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (shareable / "run.log").write_text("/home/jane/x")
    assert main([str(shareable), "--corpus", str(corpus)]) == 1
    assert "home-path" in capsys.readouterr().err


def test_main_exits_zero_on_a_clean_folder(shareable: Path, corpus: Path) -> None:
    (shareable / "scores.csv").write_text("q1,0.5\n")
    assert main([str(shareable), "--corpus", str(corpus)]) == 0
