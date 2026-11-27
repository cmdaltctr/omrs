"""Experiment 35 pooled H8 estimate (A18; pre-registration section 9 point 7).

Rows 12 to 19 get one inverse-variance-weighted mean of the FinanceBench and
FreshStack estimates (weight 1 / variance; FreshStack: the bias-reduced GEE
variance of point 3; FinanceBench: the document-cluster GEE of point 6), a 95%
normal interval and a "signs differ" mark. A row not testable on either
dataset is not pooled. The pooled row is secondary: it reads against no
SESOI and changes no verdict.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest
from tests._exp35_fixtures import load, open_half_b
from tests.test_experiment35_analyse import _build, _main
from tests.test_experiment35_factorial import _answer_setups, _answers, _doc, select35

pooled35 = load("pooled35")
cells35 = load("cells35")
analyse35 = load("analyse35")
stats_cluster = load("factorial35").stats_cluster

FB, FS = "financebench", "freshstack"
SIZE = {FB: 24, FS: 12}
ANSWER_ROWS = list(range(12, 20))
Z = 1.959963984540054


def _records(slope: dict[str, float]) -> list[dict[str, Any]]:
    """Answer records where chunk size shifts each metric by ``slope`` per doubling."""
    rows = []
    for setup in _answer_setups():
        chunk = select35.parse_setup(setup).chunk
        step = {512: 0, 1024: 1, 2048: 2}[chunk]
        for dataset, n in SIZE.items():
            for i in range(n):
                wobble = (i % 5 - 2) * 0.01 * step  # the contrast varies by question
                value = 0.5 + slope[dataset] * step + wobble
                rows.append(
                    {
                        "dataset": dataset,
                        "setup": setup,
                        "qid": f"q{i:02d}",
                        "doc_id": _doc(dataset, i),
                        "run": 1,
                        "faithfulness_glm_factual": value,
                        "ragas_answer_correctness": value / 2,
                        "cut_tokens": 20_000,
                    }
                )
    return rows


def _status(**gated: set[int]) -> dict[str, list[dict[str, Any]]]:
    return {
        d: [{"row": r, "not_testable": r in gated.get(d, set())} for r in ANSWER_ROWS] for d in SIZE
    }


def _per_dataset(records, row: int, dataset: str) -> tuple[float, float]:
    metric = "faithfulness_glm_factual" if row in (12, 13, 16, 17) else "ragas_answer_correctness"
    factorial = load("factorial35")
    cells = cells35.cell_means(records, metric)[dataset]
    d, _ = cells35.contrast(factorial.ROWS[row - 1], cells)
    qids = sorted(d)
    docs = cells35.documents(records)[dataset]
    clusters = [docs[q] for q in qids] if dataset == FB else None
    test = stats_cluster.cluster_test([d[q] for q in qids], clusters=clusters)
    return math.fsum(d.values()) / len(d), test.variance


def test_pooled_row_is_the_inverse_variance_weighted_mean_with_a_normal_interval() -> None:
    records = _records({FB: 0.04, FS: 0.10})
    out = pooled35.pooled_h8(records, _status())
    assert sorted(out) == ANSWER_ROWS
    for row in ANSWER_ROWS:
        (e1, v1), (e2, v2) = (_per_dataset(records, row, d) for d in (FB, FS))
        weight = 1 / v1 + 1 / v2
        estimate = (e1 / v1 + e2 / v2) / weight
        half = Z * math.sqrt(1 / weight)
        got = out[row]
        assert got["pooled"] is True
        assert got["estimate"] == pytest.approx(estimate)
        assert got["ci_low"] == pytest.approx(estimate - half)
        assert got["ci_high"] == pytest.approx(estimate + half)
        assert got["per_dataset"][FB]["estimate"] == pytest.approx(e1)
        assert got["per_dataset"][FS]["estimate"] == pytest.approx(e2)
        assert got["per_dataset"][FB]["variance"] == pytest.approx(v1)
        assert got["per_dataset"][FS]["variance"] == pytest.approx(v2)


def test_financebench_variance_uses_document_clusters_and_freshstack_does_not() -> None:
    records = _records({FB: 0.04, FS: 0.10})
    got = pooled35.pooled_h8(records, _status())[12]["per_dataset"]
    metric = "faithfulness_glm_factual"
    cells = cells35.cell_means(records, metric)
    d, _ = cells35.contrast(load("factorial35").ROWS[11], cells[FB])
    per_question = stats_cluster.cluster_test([d[q] for q in sorted(d)]).variance
    assert got[FB]["variance"] != pytest.approx(per_question)  # documents hold 2 questions each
    n = SIZE[FS]
    cells_fs, _ = cells35.contrast(load("factorial35").ROWS[11], cells[FS])
    r = [v - math.fsum(cells_fs.values()) / n for v in cells_fs.values()]
    closed = sum(x * x for x in r) * (n / (n - 1)) ** 2 / n**2  # section 9 point 3
    assert got[FS]["variance"] == pytest.approx(closed)


def test_signs_differ_is_marked_only_for_opposite_signs() -> None:
    opposite = pooled35.pooled_h8(_records({FB: 0.05, FS: -0.08}), _status())
    same = pooled35.pooled_h8(_records({FB: 0.05, FS: 0.08}), _status())
    assert all(opposite[r]["signs_differ"] is True for r in (12, 14, 16, 18))
    assert all(same[r]["signs_differ"] is False for r in ANSWER_ROWS)


def test_row_not_testable_on_either_dataset_is_not_pooled() -> None:
    records = _records({FB: 0.04, FS: 0.10})
    out = pooled35.pooled_h8(records, _status(**{FS: {12, 13}, FB: {14}}))
    for row in (12, 13, 14):
        assert out[row]["pooled"] is False
        assert out[row]["estimate"] is None and out[row]["ci_low"] is None
        assert "not testable" in out[row]["reason"]
    assert out[15]["pooled"] is True


def test_a_dropped_or_missing_dataset_is_not_pooled() -> None:
    records = [r for r in _records({FB: 0.04, FS: 0.10}) if r["dataset"] == FB]
    out = pooled35.pooled_h8(records, {FB: _status()[FB]})
    assert all(out[r]["pooled"] is False for r in ANSWER_ROWS)
    marked = {FB: _status()[FB], FS: [{"row": r, "dropped": True} for r in ANSWER_ROWS]}
    both = pooled35.pooled_h8(_records({FB: 0.04, FS: 0.10}), marked)
    assert all(both[r]["pooled"] is False for r in ANSWER_ROWS)


def test_pooled_row_decides_nothing() -> None:
    got = pooled35.pooled_h8(_records({FB: 0.04, FS: 0.10}), _status())[12]
    assert got["decides_nothing"] is True
    for key in ("p_value", "holm_p", "counts", "sesoi_reading"):
        assert key not in got


def test_zero_variance_in_one_dataset_is_not_pooled() -> None:
    records = _records({FB: 0.04, FS: 0.10})
    for r in records:  # no wobble: every FreshStack contrast is the same number
        if r["dataset"] == FS:
            step = {512: 0, 1024: 1, 2048: 2}[select35.parse_setup(r["setup"]).chunk]
            r["faithfulness_glm_factual"] = 0.5 + 0.10 * step
    got = pooled35.pooled_h8(records, _status())[12]
    assert got["pooled"] is False and "variance" in got["reason"]


# --- written by the analysis ------------------------------------------------------------------


def _with_chunk_effect(out: Path) -> None:
    """Rewrite answer-scores.jsonl so chunk size moves both metrics, differently per question."""
    rows = _answers()
    for r in rows:
        step = {512: 0, 1024: 1, 2048: 2}[select35.parse_setup(r["setup"]).chunk]
        r["faithfulness_glm_factual"] += step * (0.03 + 0.01 * (int(r["qid"][1:]) % 4))
        r["ragas_answer_correctness"] += step * (0.02 + 0.01 * (int(r["qid"][1:]) % 3))
    (out / "answer-scores.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


def test_analysis_writes_the_pooled_rows_beside_the_per_dataset_rows(tmp_path: Path) -> None:
    out, labels, gate, halves = _build(tmp_path)
    _with_chunk_effect(out)
    assert _main(out, labels, gate, halves) == 0
    saved = json.loads((out / analyse35.RESULT).read_text())
    pooled = saved["pooled_h8"]
    assert sorted(map(int, pooled)) == ANSWER_ROWS
    rows = {r["row"]: r for r in saved["datasets"][FS]}
    assert pooled["12"]["pooled"] is True
    assert pooled["12"]["per_dataset"][FS]["estimate"] == pytest.approx(rows[12]["estimate"])
    assert "p_value" not in pooled["12"]


def test_a_gated_row_stays_unpooled_in_the_written_file(tmp_path: Path) -> None:
    out, labels, gate, halves = _build(tmp_path)
    _with_chunk_effect(out)
    (labels / "faithfulness-gate.json").write_text(json.dumps({"not_testable_rows": [12, 13]}))
    assert _main(out, labels, gate, halves) == 0
    saved = json.loads((out / analyse35.RESULT).read_text())
    assert saved["pooled_h8"]["12"]["pooled"] is False
    assert saved["pooled_h8"]["14"]["pooled"] is True


def test_report_tables_print_the_pooled_rows_beside_the_per_dataset_rows(tmp_path: Path) -> None:
    reporttables35 = load("reporttables35")
    open_half_b(tmp_path)
    (tmp_path / "answer-scores.jsonl").write_text("")
    pooled = {"12": {"pooled": True, "estimate": 0.07, "per_dataset": {FB: {}, FS: {}}}}
    factorial = tmp_path / "confirmatory.json"
    factorial.write_text(json.dumps({"datasets": {}, "pooled_h8": pooled}))
    argv = ["--out-dir", str(tmp_path), "--factorial", str(factorial)]
    assert reporttables35.main(argv) == 0
    saved = json.loads((tmp_path / "report-tables.json").read_text())
    assert saved["pooled_h8"] == pooled
