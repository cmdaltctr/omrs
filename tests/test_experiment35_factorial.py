"""Factorial analysis of Experiment 35 (readiness tasks 14.4, 15.6 and 15.7).

Pre-registration sections 7, 8, 9 and 14.3. Fixtures plant exact effects, so
null rows have d = 0 for every question and get p = 1.
"""

from __future__ import annotations

import random
from typing import Any

import numpy as np
import pytest
from tests._exp35_fixtures import load

select35 = load("select35")
factorial35 = load("factorial35")

SIZES = {"financebench": 30, "freshstack": 12, "bioasq": 10, "legal": 8}
STEP = {"0.6b": 0, "4b": 1, "8b": 2}
FAST = {"n_draws": 2000, "n_perm": 2000}


def _doc(dataset: str, i: int) -> str:
    return f"doc{i // 2}" if dataset == "financebench" else f"{dataset}-{i}"


def _answer_setups() -> list[str]:
    crossed = [
        select35.Setup("4b", c, r, h).name
        for c in (512, 1024, 2048)
        for r in ("off", "4b")
        for h in ("off", "on")
    ]
    return crossed + [select35.Setup("4b", c, "4b", "on", True).name for c in (512, 1024, 2048)]


def _search(effect: float = 0.1, legal_effect: float | None = None) -> list[dict[str, Any]]:
    rng = random.Random(1)  # noqa: S311
    noise = {(d, i, e): rng.gauss(0, 0.01) for d in SIZES for i in range(SIZES[d]) for e in STEP}
    rows = []
    for name in select35.SEARCH_SETUPS:
        e = select35.parse_setup(name).embedder
        for dataset, n in SIZES.items():
            step = legal_effect if dataset == "legal" and legal_effect is not None else effect
            for i in range(n):
                value = 0.4 + step * STEP[e] + noise[(dataset, i, e)]
                rows.append(
                    {
                        "dataset": dataset,
                        "setup": name,
                        "qid": f"q{i:02d}",
                        "doc_id": _doc(dataset, i),
                        "ndcg_at_10": value,
                        "evidence_recall_20k": value,
                    }
                )
    return rows


def _answers(cut: Any = 20_000) -> list[dict[str, Any]]:
    rows = []
    for name in _answer_setups():
        t20k = select35.parse_setup(name).t20k
        for dataset, n in SIZES.items():
            for i in range(n):
                for run in (1, 2, 3):
                    row = {
                        "dataset": dataset,
                        "setup": name,
                        "qid": f"q{i:02d}",
                        "doc_id": _doc(dataset, i),
                        "run": run,
                        "faithfulness_glm_factual": 0.5 + i / 100,
                        "ragas_answer_correctness": 0.3 + i / 200,
                    }
                    if t20k:
                        row["cut_tokens"] = cut(dataset, i) if callable(cut) else cut
                    rows.append(row)
    return rows


def _rows(result: dict[str, Any], dataset: str) -> dict[int, dict[str, Any]]:
    return {r["row"]: r for r in result["datasets"][dataset]}


@pytest.fixture(scope="module")
def planted() -> dict[str, Any]:
    return factorial35.analyse(_search(), _answers(), **FAST)


# --- contrast scores (task 15.6, PR 9 point 1) ---


def _cells(value: Any, setups: list[str], questions: int = 2) -> dict[str, dict[str, float]]:
    return {s: {f"q{i}": value(select35.parse_setup(s)) for i in range(questions)} for s in setups}


def test_row_3_equal_cell_weights() -> None:
    by_size = {"off": 0.2, "0.6b": 0.3, "4b": 0.6, "8b": 0.9}
    cells = _cells(lambda s: by_size[s.reranker], list(select35.SEARCH_SETUPS))
    d, excluded = factorial35.contrast(factorial35.ROWS[2], cells)
    assert d == pytest.approx({"q0": 0.4, "q1": 0.4})
    assert excluded == 0


def test_row_11_known_answer() -> None:
    corners = {("8b", 2048): 0.8, ("8b", 512): 0.2, ("0.6b", 2048): 0.3, ("0.6b", 512): 0.7}
    cells = _cells(lambda s: corners.get((s.embedder, s.chunk), 0.5), list(select35.SEARCH_SETUPS))
    d, _ = factorial35.contrast(factorial35.ROWS[10], cells)
    assert d["q0"] == pytest.approx(1.0)  # the mean-minus-mean recipe would give 0.5


def test_answer_runs_averaged_first_and_complete_cases() -> None:
    rows = []
    for name in _answer_setups():
        for run, value in ((1, 0.2), (2, 0.4), (3, None)):
            for qid in ("q0", "q1"):
                v = None if qid == "q1" and name.startswith("e4b-c512-roff-hoff") else value
                rows.append(
                    {
                        "dataset": "freshstack",
                        "setup": name,
                        "qid": qid,
                        "run": run,
                        "faithfulness_glm_factual": v,
                    }
                )
    cells = factorial35.cell_means(rows, "faithfulness_glm_factual")["freshstack"]
    assert cells["e4b-c512-roff-hoff"]["q0"] == pytest.approx(0.3)  # mean of 0.2 and 0.4
    assert "q1" not in cells["e4b-c512-roff-hoff"]  # no run has a value
    d, excluded = factorial35.contrast(factorial35.ROWS[11], cells)  # row 12 uses that cell
    assert set(d) == {"q0"} and excluded == 1


def test_complete_data_estimate_equals_cell_means_contrast() -> None:
    rng = np.random.default_rng(3)
    scores = rng.uniform(0, 1, size=(9, 72))
    setups = list(select35.SEARCH_SETUPS)
    cells = {s: {f"q{q}": float(scores[q, j]) for q in range(9)} for j, s in enumerate(setups)}
    cell_mean = scores.mean(axis=0)
    first = [j for j, s in enumerate(setups) if select35.parse_setup(s).hybrid == "on"]
    second = [j for j, s in enumerate(setups) if select35.parse_setup(s).hybrid == "off"]
    d, _ = factorial35.contrast(factorial35.ROWS[3], cells)
    assert np.mean(list(d.values())) == pytest.approx(
        cell_mean[first].mean() - cell_mean[second].mean(), abs=1e-12
    )


# --- contrast table and families (task 15.7, PR 8) ---


def test_contrast_table_rows_signs_and_endpoints() -> None:
    rows = {r.number: r for r in factorial35.ROWS}
    assert sorted(rows) == list(range(1, 20))
    directional = {n for n, r in rows.items() if r.directional}
    assert directional == {1, 2, 3, 4, 5, 6, 7, 8, 11}
    endpoint = factorial35.endpoint
    assert endpoint(rows[9], "financebench") == "evidence_recall_20k"
    assert endpoint(rows[11], "financebench") == "evidence_recall_20k"
    assert endpoint(rows[9], "freshstack") == "ndcg_at_10"
    assert endpoint(rows[8], "financebench") == "ndcg_at_10"
    assert endpoint(rows[13], "freshstack") == "faithfulness_glm_factual"
    assert endpoint(rows[19], "financebench") == "ragas_answer_correctness"
    assert [rows[n].hypothesis for n in (5, 6, 11, 12, 16)] == ["H4", "H4", "H7", "H8a", "H8b"]


def test_family_sizes_and_flags(planted: dict[str, Any]) -> None:
    for dataset, size in (("financebench", 19), ("freshstack", 19), ("bioasq", 8)):
        family = [r for r in planted["datasets"][dataset] if r["holm_p"] is not None]
        assert len(family) == size
    bq = _rows(planted, "bioasq")
    assert all(bq[n]["sanity_check"] and bq[n]["counts"] is None for n in range(9, 20))
    assert not any(bq[n]["sanity_check"] for n in range(1, 9))
    legal = _rows(planted, "legal")
    assert all(r["exploratory"] and r["holm_p"] is None for r in legal.values())
    assert all(r["ci_low"] is not None for r in bq.values())


def test_planted_embedder_effect_only_h1_rows_count(planted: dict[str, Any]) -> None:
    for dataset in ("financebench", "freshstack", "bioasq"):
        counted = {n for n, r in _rows(planted, dataset).items() if r["counts"]}
        assert counted == {1, 2}, dataset
    verdicts = planted["hypotheses"]
    assert verdicts["H1"]["holds"] == "full"
    assert verdicts["H2"]["holds"] is False and verdicts["H6"]["holds"] is False
    assert verdicts["H8a"]["faithfulness"]["holds"] is False


def test_holm_within_one_dataset_over_fixed_family(planted: dict[str, Any]) -> None:
    for dataset, m in (("freshstack", 19), ("bioasq", 8)):
        rows = _rows(planted, dataset)
        smallest = min(rows[1]["p_value"], rows[2]["p_value"])
        assert min(rows[1]["holm_p"], rows[2]["holm_p"]) == pytest.approx(min(1, m * smallest))
    alone = factorial35.analyse(
        [r for r in _search() if r["dataset"] == "financebench"],
        [r for r in _answers() if r["dataset"] == "financebench"],
        **FAST,
    )
    assert alone["datasets"]["financebench"] == planted["datasets"]["financebench"]


def test_gated_row_stays_in_family_with_p_one() -> None:
    result = factorial35.analyse(
        _search(), _answers(), not_testable={"freshstack": {1, 14}}, **FAST
    )
    rows = _rows(result, "freshstack")
    assert rows[1]["not_testable"] and rows[1]["holm_p"] == 1.0 and not rows[1]["counts"]
    assert rows[14]["not_testable"]
    assert rows[2]["holm_p"] == pytest.approx(min(1, 19 * rows[2]["p_value"]))  # 19, not 18


def test_wrong_sign_significant_row_does_not_count() -> None:
    result = factorial35.analyse(_search(effect=-0.1), _answers(), **FAST)
    rows = _rows(result, "freshstack")
    assert rows[1]["holm_p"] < 0.05 and rows[1]["estimate"] < 0
    assert rows[1]["counts"] is False
    assert result["hypotheses"]["H1"]["holds"] == "no"


def test_nan_p_value_raises_before_holm_and_names_row() -> None:
    search = [r for r in _search() if r["dataset"] != "freshstack" or r["qid"] == "q00"]
    answers = [r for r in _answers() if r["dataset"] != "freshstack" or r["qid"] == "q00"]
    with pytest.raises(ValueError, match="row 1 on freshstack"):
        factorial35.analyse(search, answers, **FAST)


def test_missing_setup_refused() -> None:
    search = [r for r in _search() if r["setup"] != "e8b-c512-r4b-hon"]
    with pytest.raises(ValueError, match="search setups.*e8b-c512-r4b-hon"):
        factorial35.analyse(search, _answers(), **FAST)


def test_legal_effects_change_no_decision(planted: dict[str, Any]) -> None:
    result = factorial35.analyse(_search(legal_effect=-0.3), _answers(), **FAST)
    assert result["hypotheses"] == planted["hypotheses"]
    assert _rows(result, "legal")[1]["estimate"] < 0


def test_sensitivity_checks_and_disagreement_table(planted: dict[str, Any]) -> None:
    fb = _rows(planted, "financebench")
    cells = factorial35.cell_means(_search(), "ndcg_at_10")["financebench"]
    d, _ = factorial35.contrast(factorial35.ROWS[0], cells)
    docs = [_doc("financebench", int(q[1:])) for q in sorted(d)]
    flip = factorial35.stats_cluster.sign_flip_test([d[q] for q in sorted(d)], docs, n_draws=2000)
    assert fb[1]["method"] == "document sign-flip"
    assert (fb[1]["p_value"], fb[1]["ci_low"]) == (flip.p_value, flip.ci_low)
    assert _rows(planted, "freshstack")[1]["method"].startswith("bias-reduced GEE")
    fs_cells = factorial35.cell_means(_search(), "ndcg_at_10")["freshstack"]
    fs_d, _ = factorial35.contrast(factorial35.ROWS[0], fs_cells)
    values = [fs_d[q] for q in sorted(fs_d)]
    expected = factorial35.paired_permutation(
        [0.0] * len(values), values, n_perm=2000, seed=20261101
    )
    assert _rows(planted, "freshstack")[1]["sensitivity_p"] == expected
    assert (factorial35.PERM_SEED, factorial35.PERM_SHUFFLES) == (20261101, 10_000)
    assert (
        factorial35.stats_cluster.SIGN_FLIP_SEED,
        factorial35.stats_cluster.SIGN_FLIP_DRAWS,
    ) == (
        20261101,
        100_000,
    )
    assert fb[1]["sensitivity_method"] == "GEE, document clusters, t on documents minus 1"
    assert _rows(planted, "freshstack")[1]["sensitivity_method"] == "paired permutation"
    assert planted["disagreements"] == []


# --- hypothesis rules (PR 7) ---


def _counted(signs: dict[str, dict[int, int]]) -> dict[str, dict[int, int]]:
    full = {d: dict.fromkeys(range(1, 20), 0) for d in ("financebench", "freshstack", "bioasq")}
    for dataset, rows in signs.items():
        full[dataset].update(rows)
    return full


def test_h1_in_part_and_h4_per_dataset() -> None:
    verdicts = factorial35.verdicts(
        _counted(
            {
                "financebench": {1: 1, 5: 1, 6: 1},
                "freshstack": {1: 1, 2: 1, 5: 1},
                "bioasq": {5: 1, 6: 1},
            }
        )
    )
    assert verdicts["H1"]["holds"] == "part"
    assert verdicts["H4"]["per_dataset"] == {
        "financebench": True,
        "freshstack": False,
        "bioasq": True,
    }
    assert verdicts["H4"]["holds"] is True


def test_two_sided_rule_needs_same_row_same_sign() -> None:
    opposite = factorial35.verdicts(_counted({"financebench": {9: 1}, "freshstack": {9: -1}}))
    assert opposite["H6"]["holds"] is False
    assert opposite["H6"]["dataset_dependent"] == [9]
    different_rows = factorial35.verdicts(_counted({"financebench": {9: 1}, "freshstack": {10: 1}}))
    assert different_rows["H6"]["holds"] is False
    same = factorial35.verdicts(_counted({"financebench": {13: -1}, "freshstack": {13: -1}}))
    assert same["H8a"]["faithfulness"] == {
        "holds": True,
        "rows": [13],
        "sign": -1,
        "dataset_dependent": [],
    }
    assert same["H8a"]["correctness"]["holds"] is False
    h7 = factorial35.verdicts(_counted({"financebench": {11: 1}, "bioasq": {11: 1}}))
    assert h7["H7"]["holds"] is False  # needs FinanceBench and FreshStack


# --- H6 and H8b sensitivity analyses ---


def test_h8b_sensitivity_uses_cut_total_not_realised_total() -> None:
    def cut(dataset: str, i: int) -> int:
        return 19_000 if i == 0 else 20_000

    answers = _answers(cut=cut)
    for row in answers:
        row["realised_tokens"] = 19_000  # never read
    kept = factorial35.h8b_questions(answers)
    assert "q00" not in kept["freshstack"] and "q01" in kept["freshstack"]
    assert len(kept["freshstack"]) == SIZES["freshstack"] - 1
    assert factorial35.h8b_questions(_answers(cut=19_456))["bioasq"] == {
        f"q{i:02d}" for i in range(SIZES["bioasq"])
    }
    result = factorial35.analyse(_search(), answers, **FAST)
    assert result["h8b_sensitivity"]["financebench"]["questions_kept"] == SIZES["financebench"] - 1


def test_h6_financebench_sensitivity_table(planted: dict[str, Any]) -> None:
    table = planted["h6_financebench_sensitivity"]
    assert [r["row"] for r in table] == [9, 10]
    assert all(r["metric"] == "ndcg_at_10" and "sign_agrees" in r for r in table)


# --- RQ1 headline and descriptive table (PR 14.3) ---


def test_headline_reads_half_b_only() -> None:
    search = _search()
    halves = {d: {f"q{i:02d}": "AB"[i % 2] for i in range(n)} for d, n in SIZES.items()}
    for row in search:
        if halves[row["dataset"]][row["qid"]] == "A":
            row["ndcg_at_10"] = 5.0
    head = factorial35.headline(search, "e4b-c512-roff-hoff", "ndcg_at_10", halves, n_draws=500)
    assert set(head) == {"financebench", "freshstack", "bioasq"}
    assert head["freshstack"]["estimate"] < 1.0
    assert head["freshstack"]["n"] == 6
    assert head["financebench"]["ci_low"] <= head["financebench"]["estimate"]


def test_setup_table_is_descriptive_on_all_questions() -> None:
    table = factorial35.setup_table(_search())
    assert table["descriptive"] is True
    assert len(table["scores"]) == 72
    assert table["scores"]["e4b-c512-roff-hoff"]["freshstack"] == pytest.approx(0.5, abs=0.01)


# --- step 8 guard: no confirmatory result before the gate files (task 16.18, A6 note) ---------


def test_confirmatory_result_refuses_before_the_gate_files(tmp_path) -> None:
    labels35 = load("labels35")
    out = tmp_path / "factorial.json"
    with pytest.raises(labels35.GateMissing, match="faithfulness-gate.json"):
        factorial35.write_confirmatory(out, _search(), _answers(), label_dir=tmp_path, **FAST)
    assert not out.exists()


def test_confirmatory_result_applies_the_gate_rows(tmp_path) -> None:
    import json

    (tmp_path / "faithfulness-gate.json").write_text(json.dumps({"not_testable_rows": [12, 13]}))
    (tmp_path / "correctness-gate.json").write_text(
        json.dumps({"result": {"not_testable_rows": {"freshstack": [14]}}})
    )
    out = tmp_path / "factorial.json"
    result = factorial35.write_confirmatory(out, _search(), _answers(), label_dir=tmp_path, **FAST)
    rows = _rows(result, "freshstack")
    assert rows[12]["not_testable"] and rows[14]["not_testable"]
    assert not _rows(result, "bioasq")[14]["not_testable"]
    saved = json.loads(out.read_text())
    assert saved["gates"] == {
        "bioasq": [12, 13],
        "financebench": [12, 13],
        "freshstack": [12, 13, 14],
    }
