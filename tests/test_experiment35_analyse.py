"""Experiment 35 confirmatory analysis command, ``analyse35.py`` (review B1 and S3).

Rules under test (pre-registration sections 7 to 9, 14.2, 14.3 and 15): the
command opens behind the half-B guard before any read; it refuses unless G1
passed for every run of every answer setup; it reads the search scores of both
halves and refuses a question that is missing or appears twice in a setup; it
reads ``answer-scores.jsonl``; it writes the confirmatory result, the RQ1
headline and the 72-setup table into one file that ``reporttables35.py
--factorial`` reads.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load, open_half_b
from tests.test_experiment35_factorial import FAST, SIZES, _answer_setups, _answers, _search

analyse35 = load("analyse35")
reporttables35 = load("reporttables35")

CELL = "e4b-c1024-r4b-hon"


def _rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def _half(qid: str) -> str:
    return "B" if int(qid[1:]) % 2 else "A"


def _build(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    out, labels = tmp_path / "out", tmp_path / "labels"
    open_half_b(out, embedder="4b", reranker="4b", cell=CELL)
    for half in "AB":
        for dataset in SIZES:
            for setup in {r["setup"] for r in _search()}:
                rows = [
                    r
                    for r in _search()
                    if r["dataset"] == dataset and r["setup"] == setup and _half(r["qid"]) == half
                ]
                _rows(out / "scores" / half / dataset / f"{setup}.jsonl", rows)
    _rows(out / "answer-scores.jsonl", _answers())
    kinds = {"pass": True, "version": "v"}
    (out / "join.json").write_text(json.dumps({"ok": True, "claim_kinds": kinds}))
    for dataset in SIZES:
        for setup in _answer_setups():
            for run in (1, 2, 3):
                path = out / dataset / "answer" / setup / f"run{run}" / "determinism.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"ok": True}))
    labels.mkdir()
    (labels / "faithfulness-gate.json").write_text(json.dumps({"not_testable_rows": []}))
    corr = {"result": {"not_testable_rows": {}}}
    (labels / "correctness-gate.json").write_text(json.dumps(corr))
    gate = tmp_path / "gate.json"
    gate.write_text(json.dumps({"pass": True, "version": "v"}))
    halves = tmp_path / "halves.json"
    split = {d: {f"q{i:02d}": _half(f"q{i:02d}") for i in range(n)} for d, n in SIZES.items()}
    halves.write_text(json.dumps({"seed": 1, "halves": split}))
    return out, labels, gate, halves


def _main(out: Path, labels: Path, gate: Path, halves: Path) -> int:
    argv = ["--out-dir", str(out), "--halves", str(halves), "--label-dir", str(labels)]
    return analyse35.main([*argv, "--gate", str(gate)], **FAST)


def test_writes_one_file_that_the_report_tables_read(tmp_path: Path, monkeypatch) -> None:
    out, labels, gate, halves = _build(tmp_path)
    monkeypatch.setattr(reporttables35, "load_qrels", lambda names: {})  # no data folder here
    assert _main(out, labels, gate, halves) == 0
    saved = json.loads((out / analyse35.RESULT).read_text())
    assert set(saved["datasets"]) == set(SIZES) and saved["hypotheses"]
    assert saved["classifier_gate"]["pass"] is True
    retrieval = saved["headline"]["retrieval"]
    assert set(retrieval) == {"bioasq", "financebench", "freshstack"}
    assert retrieval["freshstack"]["setup"] == CELL and retrieval["freshstack"]["n"] == 6
    assert set(saved["headline"]["answer"]) == {
        "faithfulness_glm_factual",
        "ragas_answer_correctness",
    }
    assert saved["setup_table"]["descriptive"] is True
    assert len(saved["setup_table"]["scores"]) == 72
    factorial = ["--factorial", str(out / analyse35.RESULT)]
    assert reporttables35.main(["--out-dir", str(out), *factorial]) == 0
    tables = json.loads((out / "report-tables.json").read_text())
    assert tables["sesoi_lines"]["freshstack"][0]["row"] == 1
    assert "faithfulness_uncited_as_unsupported" in tables["sensitivity"]


def test_refuses_while_half_b_is_locked_before_any_read(tmp_path: Path, capsys) -> None:
    out, labels, gate, halves = _build(tmp_path)
    (out / "osf-timestamp.json").unlink()
    # Other inputs are broken too: the guard must refuse first, before it reads them.
    (out / "bioasq" / "answer" / CELL / "run1" / "determinism.json").unlink()
    (out / "answer-scores.jsonl").unlink()
    assert _main(out, labels, gate, halves) == 2
    err = capsys.readouterr().err
    assert "osf-timestamp.json" in err and "determinism" not in err
    assert not (out / analyse35.RESULT).exists()


def test_refuses_until_every_run_passed_g1(tmp_path: Path, capsys) -> None:
    out, labels, gate, halves = _build(tmp_path)
    path = out / "bioasq" / "answer" / CELL / "run3" / "determinism.json"
    path.write_text(json.dumps({"ok": False}))
    assert _main(out, labels, gate, halves) == 2
    assert "run3" in capsys.readouterr().err
    assert not (out / analyse35.RESULT).exists()


@pytest.mark.parametrize("change", ["twice", "missing"])
def test_refuses_a_question_not_once_in_a_setup(tmp_path: Path, change: str, capsys) -> None:
    out, labels, gate, halves = _build(tmp_path)
    a = out / "scores" / "A" / "freshstack" / f"{CELL}.jsonl"
    b = out / "scores" / "B" / "freshstack" / f"{CELL}.jsonl"
    first = json.loads(a.read_text().splitlines()[0])
    if change == "twice":
        b.write_text(b.read_text() + json.dumps(first) + "\n")
    else:
        a.write_text("".join(line + "\n" for line in a.read_text().splitlines()[1:]))
    assert _main(out, labels, gate, halves) == 2
    err = capsys.readouterr().err
    assert CELL in err and first["qid"] in err
    assert not (out / analyse35.RESULT).exists()


def test_refuses_a_question_of_halves_json_missing_from_every_setup(tmp_path: Path, capsys) -> None:
    # PR 227 review: the setups agree with each other, but the frozen list holds one more.
    out, labels, gate, halves = _build(tmp_path)
    gone = "q00"
    for path in (out / "scores").glob("[AB]/freshstack/*.jsonl"):
        kept = [line for line in path.read_text().splitlines() if json.loads(line)["qid"] != gone]
        path.write_text("".join(line + "\n" for line in kept))
    assert _main(out, labels, gate, halves) == 2
    err = capsys.readouterr().err
    assert "freshstack" in err and gone in err
    assert not (out / analyse35.RESULT).exists()


def test_a_failed_classifier_gate_gives_a_descriptive_faithfulness_headline(
    tmp_path: Path, monkeypatch
) -> None:
    # Amendment A14: under the fallback, faithfulness is descriptive only (no interval, no p).
    out, labels, gate, halves = _build(tmp_path)
    gate.write_text(json.dumps({"pass": False, "version": "v"}))
    kinds = {"pass": False, "version": None}
    (out / "join.json").write_text(json.dumps({"ok": True, "claim_kinds": kinds}))
    assert _main(out, labels, gate, halves) == 0
    answer = json.loads((out / analyse35.RESULT).read_text())["headline"]["answer"]
    assert set(answer) == {"faithfulness_glm_factual_descriptive", "ragas_answer_correctness"}
    faith = answer["faithfulness_glm_factual_descriptive"]["freshstack"]
    assert faith["descriptive"] is True and faith["setup"] == CELL and faith["n"] == 6
    assert isinstance(faith["mean"], float) and faith["metric"] == "faithfulness_glm_factual"
    assert not {"p_value", "ci_low", "ci_high", "estimate"} & set(faith)
    assert "p_value" in answer["ragas_answer_correctness"]["freshstack"]


def test_refuses_without_the_answer_scores(tmp_path: Path, capsys) -> None:
    out, labels, gate, halves = _build(tmp_path)
    (out / "answer-scores.jsonl").unlink()
    assert _main(out, labels, gate, halves) == 2
    assert "answer-scores.jsonl" in capsys.readouterr().err
