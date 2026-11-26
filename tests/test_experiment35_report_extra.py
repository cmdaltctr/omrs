"""Experiment 35 registered report outputs that had no code (review S4; prereg sections 6 and 21).

FinanceBench number match (a missing answer scores 0, a reference with no
number is not scored), the hybrid audit trigger (a), the uncited-segment
faithfulness sensitivity, the compute table and the fenced rows per file
extension. A value that is not defined reads "not defined".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load, open_half_b
from tests.test_experiment35_factorial import FAST, _answers

reportextra35 = load("reportextra35")
reporttables35 = load("reporttables35")
select35 = load("select35")

ND = reportextra35.NOT_DEFINED


def _rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


# --- FinanceBench number match --------------------------------------------------------------


def _fb_answers(out: Path, setup: str, run: int, answers: dict[str, Any]) -> None:
    rows = []
    for qid, text in answers.items():
        row = {"qid": qid, "answer": text} if text is not None else {"qid": qid, "missing": True}
        rows.append(row)
    _rows(out / "financebench" / "answer" / setup / f"run{run}" / "answer.jsonl", rows)


def test_number_match_scores_missing_answers_0_and_skips_references_with_no_number(
    tmp_path: Path,
) -> None:
    references = {"q1": "Revenue was $1,577 million.", "q2": "It rose.", "q3": "12.5%"}
    _fb_answers(tmp_path, "s", 1, {"q1": "About $1.58 billion.", "q2": "x", "q3": None})
    _fb_answers(tmp_path, "s", 2, {"q1": "No idea.", "q2": "x", "q3": "12.5 percent"})
    table = reportextra35.number_match_table(tmp_path, references)["s"]
    assert table["scored_questions"] == 2 and table["not_scored"] == 1  # q2 holds no number
    assert table["runs"] == 2
    # q1: runs 1 and 0 average 0.5; q3: missing 0 and match 1 average 0.5.
    assert table["number_match"] == pytest.approx(0.5)


def test_number_match_with_no_scored_question_is_not_defined(tmp_path: Path) -> None:
    _fb_answers(tmp_path, "s", 1, {"q2": "x"})
    table = reportextra35.number_match_table(tmp_path, {"q2": "It rose."})["s"]
    assert table["number_match"] == ND


# --- uncited-segment faithfulness sensitivity -------------------------------------------------


def test_uncited_sensitivity_runs_the_faithfulness_rows_on_the_uncited_value() -> None:
    answers = [
        {**r, "faithfulness_glm_factual_uncited": r["faithfulness_glm_factual"]} for r in _answers()
    ]
    share = {"freshstack": {"e4b-c512-r4b-hon": 0.25}}
    table = reportextra35.uncited_sensitivity(answers, share, n_draws=FAST["n_draws"])
    rows = {r["row"]: r for r in table["freshstack"]["rows"]}
    assert set(rows) == {12, 13, 16, 17}
    assert rows[12]["metric"] == "faithfulness_glm_factual_uncited" and rows[12]["n"] == 12
    assert table["freshstack"]["uncited_segment_share"] == share["freshstack"]
    assert table["bioasq"]["uncited_segment_share"] == ND


# --- compute table ----------------------------------------------------------------------------


def _record(minute: int, command: str, **flags: bool) -> dict[str, Any]:
    stamp = f"2026-12-01T{10 + minute // 60:02d}:{minute % 60:02d}:00Z"
    return {"started_at": stamp, "command": command, **flags}


def test_compute_table_gives_pod_hours_and_cost_per_stage(tmp_path: Path) -> None:
    pods = {
        "pod1": [
            _record(0, "run_arms.py --dataset bioasq --setup s --stage ingest"),
            _record(90, "run_arms.py --dataset bioasq --setup s --stage search"),
            _record(120, "run_arms.py --dataset bioasq --setup s --stage answer"),
        ],
        "pod2": [_record(0, "run_arms.py --stage ingest", prefreeze=True)],
    }
    table = reportextra35.compute_table(pods, usd_per_hour=0.5)
    rows = {(r["mode"], r["stage"]): r for r in table["stages"]}
    assert rows[("main", "ingest")]["pod_hours"] == pytest.approx(1.5)
    assert rows[("main", "ingest")]["usd"] == pytest.approx(0.75)
    assert rows[("main", "search")]["pod_hours"] == pytest.approx(0.5)
    # The last stage of a pod has no later start: its hours are not defined.
    assert rows[("main", "answer")]["pod_hours"] == ND and rows[("main", "answer")]["usd"] == ND
    assert rows[("prefreeze", "ingest")]["open_ended_runs"] == 1
    assert reportextra35.compute_table(pods, usd_per_hour=None)["stages"][0]["usd"] == ND


# --- fenced rows per extension ----------------------------------------------------------------


def test_fenced_rows_per_extension_from_the_prepare_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "freshstack" / "manifest.jsonl"
    _rows(
        manifest,
        [
            {"file": "a", "extension": ".py", "fenced": True, "rows": 2},
            {"file": "b", "extension": ".py", "fenced": False, "rows": 1},
            {"file": "c", "extension": ".md", "fenced": False, "rows": 3},
        ],
    )
    table = reportextra35.fenced_rows(tmp_path)
    assert table[".py"] == {"files": 2, "fenced_files": 1, "rows": 3, "fenced_rows": 2}
    assert table[".md"]["fenced_rows"] == 0
    assert reportextra35.fenced_rows(tmp_path / "none") == ND


# --- wired into reporttables35 ----------------------------------------------------------------


def test_report_tables_carry_the_new_outputs_or_not_defined(tmp_path: Path, monkeypatch) -> None:
    open_half_b(tmp_path)
    _rows(tmp_path / "answer-scores.jsonl", [])
    qrels = {"freshstack": {"q0": {"A": 1, "N": 0}}}
    monkeypatch.setattr(reporttables35, "load_qrels", lambda names: {d: qrels[d] for d in names})
    for setup in select35.SEARCH_SETUPS:
        units = ["X", "A"] if select35.parse_setup(setup).hybrid == "on" else ["A", "N"]
        record = {"dataset": "freshstack", "setup": setup, "qid": "q0", "units": units,
                  "ranked_units": units, "ndcg_at_10": 0.6}  # fmt: skip
        _rows(tmp_path / "scores" / "A" / "freshstack" / f"{setup}.jsonl", [record])
    assert reporttables35.main(["--out-dir", str(tmp_path)]) == 0
    saved = json.loads((tmp_path / "report-tables.json").read_text())
    trigger = saved["hybrid_trigger"]
    assert trigger["hybrid_on"] == pytest.approx(0.1) and trigger["hybrid_off"] == 0.0
    assert trigger["fires"] is True  # a 10-point gap
    assert saved["number_match"] == ND  # no FinanceBench answers
    assert saved["compute"] == ND and saved["fenced_rows"] == ND  # no inputs given
