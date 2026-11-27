"""Experiment 35 report tables added by amendment A18 (prereg 11.1, 21; R3, R5).

- All-claims faithfulness (no kind filter) beside the primary measure for rows
  12, 13, 16 and 17, whether or not classifier gate 3 passed.
- The four H7 corner-cell means with 95% intervals beside row 11.
- FreshStack ``evidence_recall_20k`` for rows 9 to 11, descriptive.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest
from tests import _exp35_mainrun_fixtures as fx
from tests._exp35_fixtures import load, open_half_b
from tests._exp35_label_fixtures import judge_row, write_rows

reportextra35 = load("reportextra35")
reporttables35 = load("reporttables35")
factorial35 = load("factorial35")
select35 = load("select35")
stats_cluster = factorial35.stats_cluster

DRAWS = 2000
CORE = ("bioasq", "financebench", "freshstack")


def _docs() -> dict[str, str]:
    return {q: f"doc{int(q[1:]) // 2}" for q in fx.QIDS}


# --- all-claims faithfulness ------------------------------------------------------------------


def _build_runs(tmp_path: Path) -> Path:
    """Two claims per answer: the first supported, the second not, except as set below."""
    out = tmp_path / "out"
    fx.build(out)
    for folder in out.glob("*/answer/*-t20k"):  # a name select35.parse_setup reads
        folder.rename(folder.with_name(folder.name.replace("-t20k", "-r4b-hon-t20k")))
    fx.write_kinds(out, lambda qid, index: "refusal" if index == 1 else "factual")
    for path in out.glob("*/answer/*-c2048-*/run*/judge-chat.jsonl"):
        rows = [
            judge_row(q, ["unsupported" if int(q[1:]) % 4 == 0 else "supported", "unsupported"])
            for q in fx.QIDS
        ]
        write_rows(path, rows)
    return out


def _result(gated: bool = False) -> dict[str, Any]:
    rows = [
        {"row": r, "estimate": 0.5, "ci_low": 0.4, "ci_high": 0.6, "not_testable": gated}
        for r in (12, 13, 16, 17)
    ]
    return {"datasets": {d: rows for d in CORE}}


def test_all_claims_records_ignore_the_saved_claim_kinds(tmp_path: Path) -> None:
    out = _build_runs(tmp_path)
    records = reportextra35.all_claims_records(out, _docs())
    first = next(r for r in records if r["setup"] == "e4b-c512-roff-hoff" and r["qid"] == "q001")
    assert first["faithfulness_glm_factual"] == pytest.approx(0.5)  # 1 of 2 cited claims
    assert first["doc_id"] is None or isinstance(first["doc_id"], str)


def test_all_claims_table_sits_beside_the_primary_rows_with_no_p_value(tmp_path: Path) -> None:
    out = _build_runs(tmp_path)
    records = reportextra35.all_claims_records(out, _docs())
    table = reportextra35.all_claims_faithfulness(records, _result(), n_draws=DRAWS)
    assert set(table) >= set(CORE)  # Legal is exploratory and also listed
    for dataset in CORE:
        by_row = {r["row"]: r for r in table[dataset]}
        assert sorted(by_row) == [12, 13, 16, 17]
        assert by_row[12]["all_claims"]["estimate"] == pytest.approx(0.0)
        # 25 of 100 questions lose 0.5 when the chunk size goes from 1,024 to 2,048.
        assert by_row[13]["all_claims"]["estimate"] == pytest.approx(-0.125)
        assert by_row[13]["primary"] == {
            "estimate": 0.5,
            "ci_low": 0.4,
            "ci_high": 0.6,
            "status": "tested",
        }
        assert "p_value" not in by_row[13]["all_claims"]
        assert by_row[13]["all_claims"]["n"] == 100


def test_all_claims_table_is_reported_when_the_primary_rows_are_not_testable(
    tmp_path: Path,
) -> None:
    out = _build_runs(tmp_path)
    records = reportextra35.all_claims_records(out, _docs())
    table = reportextra35.all_claims_faithfulness(records, _result(gated=True), n_draws=DRAWS)
    row = {r["row"]: r for r in table["bioasq"]}[13]
    assert row["primary"]["status"] == "not testable"
    assert row["all_claims"]["estimate"] == pytest.approx(-0.125)


def test_all_claims_table_without_a_result_has_no_primary_column(tmp_path: Path) -> None:
    out = _build_runs(tmp_path)
    records = reportextra35.all_claims_records(out, _docs())
    table = reportextra35.all_claims_faithfulness(records, None, n_draws=DRAWS)
    assert table["bioasq"][0]["primary"] is None


# --- H7 corner cells and FreshStack evidence recall -------------------------------------------

SIZES = {"financebench": 12, "freshstack": 12, "bioasq": 10}


def _search(
    sizes: dict[str, int] | None = None, embedder_gain: float = 0.1, chunk_gain: float = 0.02
) -> list[dict[str, Any]]:
    rows = []
    for name in select35.SEARCH_SETUPS:
        setup = select35.parse_setup(name)
        for dataset, n in (sizes or SIZES).items():
            for i in range(n):
                wobble = (i % 4) * 0.01
                ndcg = 0.3 + embedder_gain * (setup.embedder == "8b") + wobble
                ndcg += chunk_gain * (setup.chunk == 2048)
                rows.append(
                    {
                        "dataset": dataset,
                        "setup": name,
                        "qid": f"q{i:03d}",
                        "doc_id": f"doc{i // 2}" if dataset == "financebench" else None,
                        "ndcg_at_10": ndcg,
                        "evidence_recall_20k": 0.2 + 0.05 * (setup.chunk == 1024) + wobble,
                    }
                )
    return rows


def _q(dataset: str) -> list[float]:
    return [(i % 4) * 0.01 for i in range(SIZES[dataset])]


def test_h7_corner_cells_report_the_four_means_with_intervals() -> None:
    table = reportextra35.h7_corner_cells(_search(), None, n_draws=DRAWS)
    assert set(table) == set(SIZES)
    corners = {c["corner"]: c for c in table["freshstack"]["corners"]}
    assert set(corners) == {"e8b-c2048", "e8b-c512", "e0.6b-c2048", "e0.6b-c512"}
    mean_wobble = sum(_q("freshstack")) / SIZES["freshstack"]
    assert corners["e8b-c2048"]["estimate"] == pytest.approx(0.3 + 0.1 + 0.02 + mean_wobble)
    assert corners["e8b-c512"]["estimate"] == pytest.approx(0.3 + 0.1 + mean_wobble)
    assert corners["e0.6b-c2048"]["estimate"] == pytest.approx(0.3 + 0.02 + mean_wobble)
    assert corners["e0.6b-c512"]["estimate"] == pytest.approx(0.3 + mean_wobble)
    values = [0.3 + w for w in _q("freshstack")]  # the same spread in every corner
    half = stats_cluster.cluster_test(values)
    assert corners["e0.6b-c512"]["ci_low"] == pytest.approx(half.ci_low)
    assert corners["e0.6b-c512"]["ci_high"] == pytest.approx(half.ci_high)
    assert "p_value" not in corners["e0.6b-c512"]


def test_h7_corner_cells_use_evidence_recall_on_financebench_as_row_11_does() -> None:
    table = reportextra35.h7_corner_cells(_search(), None, n_draws=DRAWS)
    corner = {c["corner"]: c for c in table["financebench"]["corners"]}["e8b-c2048"]
    assert corner["metric"] == "evidence_recall_20k"
    assert table["freshstack"]["corners"][0]["metric"] == "ndcg_at_10"


def test_h7_corner_cells_print_beside_row_11_of_the_result() -> None:
    result = {
        "datasets": {"freshstack": [{"row": 11, "estimate": 0.01, "ci_low": -0.1, "ci_high": 0.1}]}
    }
    table = reportextra35.h7_corner_cells(_search(), result, n_draws=DRAWS)
    assert table["freshstack"]["row_11"] == {"estimate": 0.01, "ci_low": -0.1, "ci_high": 0.1}
    assert table["bioasq"]["row_11"] is None


def test_freshstack_evidence_recall_rows_9_to_11_are_descriptive() -> None:
    table = reportextra35.freshstack_evidence_recall(_search(), n_draws=DRAWS)
    assert sorted(table) == [9, 10, 11]
    assert table[9]["estimate"] == pytest.approx(0.05)  # 1,024 minus 512
    assert table[10]["estimate"] == pytest.approx(-0.05)  # 2,048 minus 1,024
    assert table[11]["estimate"] == pytest.approx(0.0)  # H7 interaction: the same chunk gain
    assert table[9]["metric"] == "evidence_recall_20k" and table[9]["n"] == SIZES["freshstack"]
    for entry in table.values():
        assert "p_value" not in entry and "holm_p" not in entry
        assert not math.isnan(entry["ci_low"] + entry["ci_high"])


def test_freshstack_evidence_recall_without_freshstack_scores_is_not_defined() -> None:
    records = [r for r in _search() if r["dataset"] != "freshstack"]
    assert reportextra35.freshstack_evidence_recall(records, n_draws=DRAWS) == "not defined"


# --- wired into the report tables -------------------------------------------------------------


def test_report_tables_carry_the_three_a18_tables(tmp_path: Path) -> None:
    out = _build_runs(tmp_path)
    rows = _search({d: len(fx.QIDS) for d in CORE})
    for dataset in CORE:
        for setup in {r["setup"] for r in rows}:
            part = [r for r in rows if r["dataset"] == dataset and r["setup"] == setup]
            write_rows(out / "scores" / "A" / dataset / f"{setup}.jsonl", part)
    path = tmp_path / "confirmatory.json"
    path.write_text(json.dumps(_result()))
    saved = reporttables35.a18_tables(out, json.loads(path.read_text()), n_draws=DRAWS)
    assert set(saved["h7_corner_cells"]) == set(CORE)
    assert sorted(saved["freshstack_evidence_recall"]) == [9, 10, 11]
    assert set(saved["all_claims_faithfulness"]) >= set(CORE)
    assert saved["all_claims_faithfulness"]["bioasq"][1]["all_claims"]["estimate"] == pytest.approx(
        -0.125
    )


def test_report_tables_without_inputs_read_not_defined(tmp_path: Path) -> None:
    saved = reporttables35.a18_tables(tmp_path, None, n_draws=DRAWS)
    assert saved == {
        "h7_corner_cells": "not defined",
        "freshstack_evidence_recall": "not defined",
        "all_claims_faithfulness": "not defined",
    }


def test_the_report_command_writes_the_three_a18_tables(tmp_path: Path) -> None:
    open_half_b(tmp_path)
    (tmp_path / "answer-scores.jsonl").write_text("")
    assert reporttables35.main(["--out-dir", str(tmp_path)]) == 0
    saved = json.loads((tmp_path / "report-tables.json").read_text())
    for name in ("h7_corner_cells", "freshstack_evidence_recall", "all_claims_faithfulness"):
        assert saved[name] == "not defined"
