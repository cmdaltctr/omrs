"""MDE table of Experiment 35 from saved pilot files (readiness task 15.11, PR section 10)."""

from __future__ import annotations

import json
import random
import statistics
from pathlib import Path
from typing import Any

import pytest
from scipy.stats import norm
from tests._exp35_fixtures import load

select35 = load("select35")
factorial35 = load("factorial35")
mde35 = load("mde35")

PILOT_SETUPS = [
    select35.Setup(e, c, r, h).name
    for e in ("0.6b", "8b")
    for c in (512, 2048)
    for r in ("off", "0.6b", "4b", "8b")
    for h in ("off", "on")
]


def _pilot() -> list[dict[str, Any]]:
    rng = random.Random(4)  # noqa: S311
    rows = []
    for dataset in ("financebench", "freshstack", "bioasq"):
        shifts = [rng.gauss(0, 0.1) for _ in range(10)]  # one per block of 4 questions
        for i in range(40):
            base = rng.random()
            doc_shift = shifts[i // 4]  # shared within a FinanceBench document
            for name in PILOT_SETUPS:
                s = select35.parse_setup(name)
                value = base + rng.gauss(0, 0.05) + (s.embedder == "8b") * (0.05 + doc_shift)
                rows.append(
                    {
                        "dataset": dataset,
                        "setup": name,
                        "qid": f"q{i:02d}",
                        "doc_id": f"doc{i // 4}" if dataset == "financebench" else f"q{i}",
                        "ndcg_at_10": value,
                        "evidence_recall_20k": value,
                    }
                )
    return rows


def _by(table: list[dict[str, Any]], dataset: str, row: int) -> dict[str, Any]:
    return next(r for r in table if r["dataset"] == dataset and r["row"] == row)


def test_mde_formula_and_alpha_per_family() -> None:
    entry = mde35.mde_row("freshstack", 4, 0.2, source="pilot")
    alpha = 0.05 / 19
    expected = (norm.ppf(1 - alpha / 2) + norm.ppf(0.8)) * 0.2 / 203**0.5
    assert entry["mde"] == pytest.approx(expected, rel=1e-12)
    assert entry["alpha"] == pytest.approx(alpha)
    bq = mde35.mde_row("bioasq", 4, 0.2, source="pilot")
    assert bq["alpha"] == pytest.approx(0.05 / 8)
    assert bq["n"] == 707


def test_design_effect_hand_case() -> None:
    # d = 1, 2, 3, 4 in documents a, a, b, c. Clustered variance (16 + 4/9 + 4) / 16,
    # question-level variance 5/9 (see test_experiment35_stats_cluster).
    de = mde35.design_effect([1.0, 2.0, 3.0, 4.0], ["a", "a", "b", "c"])
    assert de == pytest.approx(((16 + 4 / 9 + 4) / 16) / (5 / 9))


def test_financebench_n_divided_by_design_effect() -> None:
    entry = mde35.mde_row("financebench", 4, 0.2, source="pilot", design_effect=2.0)
    assert entry["n_effective"] == pytest.approx(75.0)
    alpha = 0.05 / 19
    assert entry["mde"] == pytest.approx((norm.ppf(1 - alpha / 2) + norm.ppf(0.8)) * 0.2 / 75**0.5)


def test_pilot_table_sd_stand_ins_and_sesoi() -> None:
    table = mde35.pilot_table(_pilot())
    assert {(r["dataset"], r["row"]) for r in table} == {
        *(("financebench", k) for k in range(1, 12)),
        *(("freshstack", k) for k in range(1, 12)),
        *(("bioasq", k) for k in range(1, 9)),
    }
    one, two = _by(table, "freshstack", 1), _by(table, "freshstack", 2)
    assert one["sd"] == two["sd"] and one["stand_in"] == "e8b minus e0.6b"
    assert _by(table, "freshstack", 7)["stand_in"] == "r8b minus r0.6b"
    assert _by(table, "freshstack", 9)["stand_in"] == "c2048 minus c512"
    assert _by(table, "freshstack", 11)["stand_in"] is None
    # Row 1's stand-in SD is the SD of the 8b minus 0.6b contrast, computed here apart.
    cells = factorial35.cell_means(_pilot(), "ndcg_at_10")["freshstack"]
    d = [
        statistics.fmean(cells[s][q] for s in cells if s.startswith("e8b"))
        - statistics.fmean(cells[s][q] for s in cells if s.startswith("e0.6b"))
        for q in sorted(cells[PILOT_SETUPS[0]])
    ]
    assert one["sd"] == pytest.approx(statistics.stdev(d), abs=1e-12)
    assert one["below_sesoi"] == (one["mde"] <= 0.02)
    assert _by(table, "financebench", 9)["metric"] == "evidence_recall_20k"
    assert _by(table, "financebench", 9)["below_sesoi"] is None  # no SESOI on that endpoint
    fb = _by(table, "financebench", 1)
    assert fb["design_effect"] > 1  # the planted document shift clusters the 8b effect
    assert fb["n_effective"] == pytest.approx(150 / fb["design_effect"])
    assert _by(table, "freshstack", 1)["design_effect"] is None


def test_pilot_missing_cells_named() -> None:
    rows = [r for r in _pilot() if "-r8b-" not in r["setup"]]  # row 7 needs r8b minus r0.6b
    with pytest.raises(ValueError, match="row 7"):
        mde35.pilot_table(rows)


def test_answer_rows_are_rough() -> None:
    answers = []
    for c in (512, 1024, 2048):
        for t20k in (False, True):
            name = select35.Setup("4b", c, "4b", "on", t20k).name
            for i in range(6):
                answers.append(
                    {
                        "dataset": "freshstack",
                        "setup": name,
                        "qid": f"q{i}",
                        "run": 1,
                        "faithfulness_glm_factual": (i * c % 7) / 10,
                        "ragas_answer_correctness": (i + c % 5) / 10,
                    }
                )
    table = mde35.answer_table(answers, source="smoke and test-pod answers")
    assert sorted(r["row"] for r in table) == list(range(12, 20))
    assert all(r["rough"] and r["below_sesoi"] is None for r in table)
    assert table[0]["sd_source"] == "smoke and test-pod answers"


def test_assumed_fallback_range() -> None:
    table = mde35.assumed_table()
    entry = _by(table, "freshstack", 1)
    assert entry["assumed"] is True
    assert (entry["sd_low"], entry["sd_high"]) == (0.15, 0.25)
    assert entry["mde_low"] == pytest.approx(
        mde35.mde_row("freshstack", 1, 0.15, source="x")["mde"]
    )
    assert entry["mde_high"] == pytest.approx(
        mde35.mde_row("freshstack", 1, 0.25, source="x")["mde"]
    )


def test_write_table(tmp_path: Path) -> None:
    path = tmp_path / "mde.json"
    mde35.write_table(path, mde35.assumed_table())
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["sesoi"] == 0.02 and len(saved["rows"]) == 30
