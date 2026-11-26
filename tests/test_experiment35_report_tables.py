"""Report items of Experiment 35 (readiness task 16.20; pre-registration sections 10 and 21).

Chunk-length distribution per chunk-size level and dataset, unmapped-chunk
counts per setup, the drop record, the H8b token totals, SESOI and MDE lines
per row, the FinanceBench nDCG@10 table and the one sensitivity table set.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load, open_half_b

select35 = load("select35")
factorial35 = load("factorial35")
reporttables35 = load("reporttables35")

STEP = {512: 0, 1024: 1, 2048: 2}


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


# --- realised chunk-length distribution ------------------------------------------


def _lists() -> list[tuple[str, str, dict[str, Any]]]:
    """Chunk c1..c5 of 100..500 tokens at c512 (seen by two embedders), c9 at c2048."""
    first = {"qid": "q0", "chunks": [{"chunk_id": f"c{i}", "tokens": 100 * i} for i in (1, 2, 3)]}
    second = {"qid": "q1", "chunks": [{"chunk_id": f"c{i}", "tokens": 100 * i} for i in (3, 4, 5)]}
    wide = {"qid": "q0", "chunks": [{"chunk_id": "c9", "tokens": 1900}]}
    return [
        ("bioasq", "e4b-c512-roff-hoff", first),
        ("bioasq", "e8b-c512-r4b-hon", second),
        ("bioasq", "e4b-c2048-roff-hoff", wide),
        ("legal", "e4b-c512-roff-hoff", {"qid": "q0", "chunks": [{"chunk_id": "c1", "tokens": 7}]}),
    ]


def test_chunk_lengths_per_level_and_dataset_count_each_stored_chunk_once() -> None:
    table = reporttables35.chunk_lengths(_lists())
    small = table["bioasq"]["512"]
    assert small["chunks"] == 5
    assert (small["min"], small["median"], small["max"]) == (100, 300, 500)
    assert small["mean"] == pytest.approx(300)
    assert table["bioasq"]["2048"]["chunks"] == 1 and "1024" not in table["bioasq"]
    assert table["legal"]["512"]["max"] == 7  # same chunk ID, other dataset: its own entry
    assert "top-100" in table["source"]


def test_chunk_length_table_reads_the_saved_search_lists(tmp_path: Path) -> None:
    for dataset, setup, row in _lists():
        _write(tmp_path / dataset / "search" / setup / "run1" / "search.jsonl", [row])
    table = reporttables35.chunk_length_table(tmp_path)
    assert table["bioasq"]["512"]["chunks"] == 5


# --- unmapped chunks and drop record ------------------------------------------------


def test_unmapped_chunks_per_setup_sum_both_halves(tmp_path: Path) -> None:
    for half, count in (("A", 2), ("B", 3)):
        path = tmp_path / "scores" / half / "freshstack" / "summary.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"e4b-c512-roff-hoff": {"unmapped_chunks": count}}))
    assert reporttables35.unmapped_counts(tmp_path) == {"freshstack": {"e4b-c512-roff-hoff": 5}}


def test_drop_record_names_each_step(tmp_path: Path) -> None:
    assert reporttables35.drop_record(tmp_path) == []
    (tmp_path / "drops.json").write_text(json.dumps({"drops": [{"step": 3}, {"step": 1}]}))
    assert reporttables35.drop_record(tmp_path) == [
        {"step": 1, "name": "Legal RAG Bench answer generation"},
        {"step": 3, "name": "closed-book run with the RAG prompt"},
    ]


# --- H8b table: questions kept by cut total, both token totals --------------------


def _t20k() -> list[str]:
    return [select35.Setup("4b", c, "4b", "on", True).name for c in (512, 1024, 2048)]


def test_h8b_token_totals_keep_questions_by_cut_total_and_show_both_totals() -> None:
    rows = []
    for setup in _t20k():
        for qid, cut, realised in (("q0", 20_000, 18_000), ("q1", 19_000, 19_000)):
            for run in (1, 2):
                row = {"dataset": "freshstack", "setup": setup, "qid": qid, "run": run}
                row |= {"cut_tokens": cut, "evidence_tokens": realised}
                rows.append(row)
    rows.append({"dataset": "freshstack", "setup": _t20k()[0], "qid": "q2", "run": 1})
    table = reporttables35.h8b_token_totals(rows)["freshstack"][_t20k()[0]]
    assert table["questions"] == 3 and table["questions_kept"] == 1
    assert table["kept"] == {"mean_cut_tokens": 20_000, "mean_realised_tokens": 18_000}
    assert table["all"]["mean_cut_tokens"] == pytest.approx(19_500)
    assert table["realised_below_cut"] == 1 and table["share_realised_below_cut"] == 0.5
    assert table["no_cut_total"] == 1 and table["no_realised_total"] == 1


# --- SESOI and MDE lines ----------------------------------------------------------


def _row(number: int, metric: str, low: float, high: float, **extra: Any) -> dict[str, Any]:
    est = (low + high) / 2
    return {"row": number, "metric": metric, "estimate": est, "ci_low": low, "ci_high": high} | {
        "not_testable": False,
        **extra,
    }


def test_sesoi_and_mde_lines_per_row() -> None:
    rows = {
        "freshstack": [
            _row(1, "ndcg_at_10", 0.03, 0.08),
            _row(2, "ndcg_at_10", -0.01, 0.015),
            _row(3, "ndcg_at_10", 0.01, 0.05, not_testable=True),
            _row(12, "faithfulness_glm_factual", -0.1, 0.1),
            {"row": 13, "metric": "faithfulness_glm_factual", "dropped": True},
        ]
    }
    mde = [
        {"dataset": "freshstack", "row": 1, "mde": 0.03, "assumed": False, "rough": False},
        {"dataset": "freshstack", "row": 12, "mde": 0.07, "assumed": False, "rough": True},
        {
            "dataset": "freshstack",
            "row": 2,
            "mde": None,
            "mde_low": 0.02,
            "mde_high": 0.04,
            "assumed": True,
            "rough": False,
        },
    ]
    lines = {r["row"]: r for r in reporttables35.sesoi_lines(rows, mde)["freshstack"]}
    assert lines[1]["sesoi"] == 0.02 and lines[1]["sesoi_reading"] == "beyond 0.02"
    assert lines[1]["readings"] == {"0.01": "beyond", "0.02": "beyond", "0.05": "cannot exclude"}
    assert lines[1]["mde"] == 0.03
    assert lines[2]["sesoi_reading"] == "within 0.02"
    assert lines[2]["mde_range"] == [0.02, 0.04] and lines[2]["mde_label"] == "assumed"
    assert lines[3]["sesoi_reading"] == "cannot rule out a small effect"
    assert lines[3]["status"] == "not testable"
    assert lines[12]["sesoi"] is None and lines[12]["readings"] is None
    assert lines[12]["mde"] == 0.07 and lines[12]["mde_label"] == "rough"
    assert lines[13]["status"] == "dropped" and lines[13]["mde"] is None


# --- FinanceBench nDCG@10 table for rows 9 and 10 (sign agreement) -------------------


def _answer_setups() -> list[str]:
    crossed = [
        select35.Setup("4b", c, r, h).name
        for c in (512, 1024, 2048)
        for r in ("off", "4b")
        for h in ("off", "on")
    ]
    return crossed + _t20k()


def _fb_search(sign_flip: bool) -> list[dict[str, Any]]:
    rng = random.Random(7)  # noqa: S311
    noise = {(i, c): rng.gauss(0, 0.01) for i in range(20) for c in STEP}
    rows = []
    for name in select35.SEARCH_SETUPS:
        chunk = select35.parse_setup(name).chunk
        for i in range(20):
            base = 0.05 * STEP[chunk] + noise[(i, chunk)]
            rows.append(
                {
                    "dataset": "financebench",
                    "setup": name,
                    "qid": f"q{i:02d}",
                    "doc_id": f"doc{i // 2}",
                    "ndcg_at_10": 0.4 + base,
                    "evidence_recall_20k": 0.4 - base if sign_flip else 0.4 + base,
                }
            )
    return rows


@pytest.mark.parametrize("flip", [False, True])
def test_financebench_ndcg_table_gives_sign_agreement_per_row(flip: bool) -> None:
    answers = [
        {"dataset": "financebench", "setup": setup, "qid": f"q{i:02d}", "doc_id": f"doc{i // 2}"}
        | {"run": 1, "faithfulness_glm_factual": 0.5, "ragas_answer_correctness": 0.5}
        | ({"cut_tokens": 20_000} if select35.parse_setup(setup).t20k else {})
        for setup in _answer_setups()
        for i in range(20)
    ]
    result = factorial35.analyse(_fb_search(flip), answers, n_draws=500, n_perm=500)
    table = reporttables35.financebench_ndcg(result)
    assert [r["row"] for r in table] == [9, 10]
    assert all(r["metric"] == "ndcg_at_10" and r["estimate"] > 0.03 for r in table)
    assert all(r["endpoint"] == "evidence_recall_20k" for r in table)
    assert [r["sign_agrees"] for r in table] == [not flip, not flip]


# --- one sensitivity table set ------------------------------------------------------


def test_one_sensitivity_table_set_and_no_any_page_table() -> None:
    result = {
        "disagreements": [{"dataset": "bioasq", "row": 3}],
        "h6_financebench_sensitivity": [{"row": 9, "estimate": 0.1, "sign_agrees": True}],
        "h8b_sensitivity": {"freshstack": {"questions_kept": 4}},
    }
    tables = reporttables35.sensitivity_set(
        result,
        bounds={"freshstack": {}},
        contamination={"freshstack": {"label": "one closed-book run"}},
        length_check={"chat": {"rate": 0.1}},
        token_totals={"freshstack": {}},
    )
    assert list(tables) == list(reporttables35.SENSITIVITY_TABLES)
    assert not any("any_page" in name or "page_rule" in name for name in tables)
    assert tables["clustered_vs_sensitivity"] == result["disagreements"]
    assert tables["h8b_cut_total"]["token_totals"] == {"freshstack": {}}
    assert tables["closed_book_subset"]["freshstack"]["label"] == "one closed-book run"
    missing = reporttables35.sensitivity_set(result)
    assert missing["length_controlled_check"] == {"status": "not run"}


def test_main_writes_the_report_tables_behind_the_half_b_guard(tmp_path: Path) -> None:
    scoring35 = load("scoring35")
    with pytest.raises(scoring35.HalfBLocked):
        reporttables35.main(["--out-dir", str(tmp_path)])
    open_half_b(tmp_path)
    for dataset, setup, row in _lists():
        _write(tmp_path / dataset / "search" / setup / "run1" / "search.jsonl", [row])
    _write(tmp_path / "answer-scores.jsonl", [])
    assert reporttables35.main(["--out-dir", str(tmp_path)]) == 0
    saved = json.loads((tmp_path / "report-tables.json").read_text())
    assert saved["chunk_lengths"]["bioasq"]["512"]["chunks"] == 5
    assert saved["drops"] == [] and saved["sesoi_lines"] is None
    assert saved["sensitivity"] is None  # no factorial result given


def test_main_writes_the_unjudged_table_from_the_score_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR 21: unjudged share and condensed-list nDCG@10 where negatives are judged, else NEITHER.
    unjudged35 = load("unjudged35")
    qrels = {"freshstack": {"q0": {"A": 1, "N": 0}}, "bioasq": {"q0": {"P": 1}}}
    monkeypatch.setattr(reporttables35, "load_qrels", lambda names: {d: qrels[d] for d in names})
    open_half_b(tmp_path)
    _write(tmp_path / "answer-scores.jsonl", [])
    for dataset in ("freshstack", "bioasq"):
        for setup in select35.SEARCH_SETUPS:  # the full 72-setup grid, as score35 writes it
            units = ["X", "A"]
            record = {"dataset": dataset, "setup": setup, "qid": "q0",
                      "units": units, "ranked_units": units, "ndcg_at_10": 0.6}  # fmt: skip
            _write(tmp_path / "scores" / "A" / dataset / f"{setup}.jsonl", [record])
    assert reporttables35.main(["--out-dir", str(tmp_path)]) == 0
    saved = json.loads((tmp_path / "report-tables.json").read_text())["unjudged"]
    assert saved["bioasq"] == {"defined": False, "note": unjudged35.NEITHER}
    assert saved["freshstack"]["unjudged_share"]["e4b-c512-roff-hoff"] == pytest.approx(0.1)
    assert len(saved["freshstack"]["unjudged_share"]) == 72
    assert [r["row"] for r in saved["freshstack"]["condensed_ndcg_rows"]] == list(range(1, 9))


def test_main_writes_no_unjudged_table_before_any_score(tmp_path: Path) -> None:
    open_half_b(tmp_path)
    _write(tmp_path / "answer-scores.jsonl", [])
    assert reporttables35.main(["--out-dir", str(tmp_path)]) == 0
    saved = json.loads((tmp_path / "report-tables.json").read_text())
    assert saved["unjudged"] is None
    assert saved["alpha_ndcg_freshstack"] == {"status": "not run"}


def test_main_carries_the_alpha_ndcg_table_when_alphandcg35_wrote_it(tmp_path: Path) -> None:
    open_half_b(tmp_path)
    _write(tmp_path / "answer-scores.jsonl", [])
    table = {"metric": "alpha-nDCG@10", "descriptive": True, "setups": {"s": {"n": 1}}}
    (tmp_path / "alpha-ndcg.json").write_text(json.dumps(table))
    assert reporttables35.main(["--out-dir", str(tmp_path)]) == 0
    saved = json.loads((tmp_path / "report-tables.json").read_text())
    assert saved["alpha_ndcg_freshstack"] == table
