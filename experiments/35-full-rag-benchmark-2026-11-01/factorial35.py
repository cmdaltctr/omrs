"""Factorial analysis of Experiment 35 (pre-registration sections 7 to 9 and 14.3).

Readiness tasks 14.4, 15.6 and 15.7. Reads plain per-question score records
and returns the contrast table of section 8 (rows 1 to 19), the Holm families,
the hypothesis verdicts of section 7 and the registered sensitivity analyses.

A score record is a mapping with ``dataset``, ``setup``, ``qid``,
``doc_id`` (FinanceBench), ``run`` (answer records) and metric keys:
``ndcg_at_10``, ``evidence_recall_20k``, ``faithfulness_glm_factual``,
``ragas_answer_correctness``; ``-t20k`` answer records also carry
``cut_tokens`` (the kept stored chunks before assembly). A missing or None
metric means "no value" (section 12): the cell mean uses the runs that have
one, and a question enters a row only when every cell of the row has a value.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import select35
from experiments._lib import stats_cluster
from experiments._lib.stats_d6 import holm, paired_permutation

FB, FS, BQ = select35.CORE
LEGAL = "legal"
NDCG = "ndcg_at_10"
EVIDENCE = "evidence_recall_20k"
FAITH = "faithfulness_glm_factual"
CORRECT = "ragas_answer_correctness"
CUT_TOKENS = "cut_tokens"
CUT_MIN = 19_456  # 95% of 20,480 tokens
ALPHA = 0.05
PERM_SEED = 20261101
PERM_SHUFFLES = 10_000
FAMILIES = {FB: tuple(range(1, 20)), FS: tuple(range(1, 20)), BQ: tuple(range(1, 9))}
STAGE_SIZES = {"search": 72, "crossed": 12, "t20k": 3}
ON = ("0.6b", "4b", "8b")

Cells = Mapping[str, Mapping[str, float]]


@dataclass(frozen=True)
class Row:
    """One row of the contrast table: d = sum of coefficient x mean over matching cells."""

    number: int
    hypothesis: str
    stage: str
    outcome: str
    terms: tuple[tuple[float, Mapping[str, tuple[Any, ...]]], ...]
    directional: bool


def _pair(first: Mapping[str, tuple[Any, ...]], second: Mapping[str, tuple[Any, ...]]) -> Any:
    return ((1.0, first), (-1.0, second))


def _chunk_rows(start: int, hypothesis: str, stage: str) -> list[Row]:
    rows = []
    for k, outcome in enumerate(("faithfulness", "correctness")):
        for j, (a, b) in enumerate(((1024, 512), (2048, 1024))):
            terms = _pair({"chunk": (a,)}, {"chunk": (b,)})
            rows.append(Row(start + 2 * k + j, hypothesis, stage, outcome, terms, False))
    return rows


def _search_row(number: int, hypothesis: str, terms: Any, directional: bool = True) -> Row:
    return Row(number, hypothesis, "search", "retrieval", terms, directional)


_RR_ON = {"reranker": ON, "hybrid": ("on",)}
_H7 = ((1.0, "8b", 2048), (-1.0, "8b", 512), (-1.0, "0.6b", 2048), (1.0, "0.6b", 512))

ROWS: tuple[Row, ...] = (
    _search_row(1, "H1", _pair({"embedder": ("4b",)}, {"embedder": ("0.6b",)})),
    _search_row(2, "H1", _pair({"embedder": ("8b",)}, {"embedder": ("4b",)})),
    _search_row(3, "H2", _pair({"reranker": ON}, {"reranker": ("off",)})),
    _search_row(4, "H3", _pair({"hybrid": ("on",)}, {"hybrid": ("off",)})),
    _search_row(5, "H4", _pair(_RR_ON, {"reranker": ON, "hybrid": ("off",)})),
    _search_row(6, "H4", _pair(_RR_ON, {"reranker": ("off",), "hybrid": ("on",)})),
    _search_row(7, "H5", _pair({"reranker": ("4b",)}, {"reranker": ("0.6b",)})),
    _search_row(8, "H5", _pair({"reranker": ("8b",)}, {"reranker": ("4b",)})),
    _search_row(9, "H6", _pair({"chunk": (1024,)}, {"chunk": (512,)}), False),
    _search_row(10, "H6", _pair({"chunk": (2048,)}, {"chunk": (1024,)}), False),
    _search_row(11, "H7", tuple((c, {"embedder": (e,), "chunk": (k,)}) for c, e, k in _H7)),
    *_chunk_rows(12, "H8a", "crossed"),
    *_chunk_rows(16, "H8b", "t20k"),
)


def endpoint(row: Row, dataset: str) -> str:
    """Return the metric of ``row`` on ``dataset`` (section 8 table)."""
    if row.outcome == "faithfulness":
        return FAITH
    if row.outcome == "correctness":
        return CORRECT
    return EVIDENCE if dataset == FB and row.number in (9, 10, 11) else NDCG


def cell_means(
    records: Iterable[Mapping[str, Any]], metric: str
) -> dict[str, dict[str, dict[str, float]]]:
    """Return per dataset, setup and question the mean of ``metric`` over runs that have it."""
    values: dict[tuple[str, str, str], list[float]] = {}
    for row in records:
        key = (row["dataset"], row["setup"], str(row["qid"]))
        bucket = values.setdefault(key, [])
        if row.get(metric) is not None:
            bucket.append(float(row[metric]))
    cells: dict[str, dict[str, dict[str, float]]] = {}
    for (dataset, setup, qid), found in values.items():
        per_setup = cells.setdefault(dataset, {}).setdefault(setup, {})
        if found:
            per_setup[qid] = math.fsum(found) / len(found)
    return cells


def _stage_setups(row: Row, cells: Cells) -> list[str]:
    if row.stage == "search":
        return sorted(cells)
    want = row.stage == "t20k"
    return sorted(s for s in cells if select35.parse_setup(s).t20k == want)


def contrast(row: Row, cells: Cells) -> tuple[dict[str, float], int]:
    """Return the per-question contrast scores d of ``row`` and the excluded count.

    A question enters only when every cell the row uses has a value.
    """
    setups = _stage_setups(row, cells)
    grid = {s: select35.parse_setup(s) for s in setups}
    groups = []
    for coefficient, levels in row.terms:
        match = [s for s in setups if all(getattr(grid[s], k) in v for k, v in levels.items())]
        groups.append((coefficient, match))
    used = sorted({s for _, match in groups for s in match})
    every = set().union(*(cells[s] for s in setups)) if setups else set()
    entered = [q for q in sorted(every) if all(q in cells[s] for s in used)]
    d = {
        q: math.fsum(c * math.fsum(cells[s][q] for s in m) / len(m) for c, m in groups)
        for q in entered
    }
    return d, len(every) - len(entered)


def _documents(records: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, str]]:
    docs: dict[str, dict[str, str]] = {}
    for row in records:
        docs.setdefault(row["dataset"], {})[str(row["qid"])] = str(row.get("doc_id"))
    return docs


def _test(
    dataset: str, d: Mapping[str, float], docs: Mapping[str, str], n_draws: int
) -> dict[str, Any]:
    qids = sorted(d)
    values = [d[q] for q in qids]
    if dataset == FB:
        flip = stats_cluster.sign_flip_test(values, [docs[q] for q in qids], n_draws=n_draws)
        return {
            "estimate": flip.estimate,
            "p_value": flip.p_value,
            "ci_low": flip.ci_low,
            "ci_high": flip.ci_high,
            "method": "document sign-flip",
        }
    test = stats_cluster.cluster_test(values)
    return {
        "estimate": test.estimate,
        "p_value": test.p_value,
        "ci_low": test.ci_low,
        "ci_high": test.ci_high,
        "method": f"bias-reduced GEE ({test.source})",
    }


def _sensitivity(
    dataset: str, d: Mapping[str, float], docs: Mapping[str, str], n_perm: int
) -> tuple[float, str]:
    qids = sorted(d)
    values = [d[q] for q in qids]
    if dataset == FB:
        test = stats_cluster.cluster_test(values, clusters=[docs[q] for q in qids])
        return test.p_value, "GEE, document clusters, t on documents minus 1"
    p = paired_permutation([0.0] * len(values), values, n_perm=n_perm, seed=PERM_SEED)
    return p, "paired permutation"


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def _family(dataset: str, rows: list[dict[str, Any]], key: str) -> list[float]:
    """Holm over the fixed family; gated rows enter with p = 1; NaN raises first."""
    p_values = []
    for row in rows:
        p = 1.0 if row["not_testable"] else row[key]
        if math.isnan(p):
            raise ValueError(f"row {row['row']} on {dataset}: {key} is NaN; stop before Holm")
        p_values.append(p)
    return holm(p_values)


def _counts(row: Row, estimate: float, holm_p: float, gated: bool) -> bool:
    if gated or holm_p >= ALPHA:
        return False
    return estimate > 0 if row.directional else estimate != 0


def _check_stage(dataset: str, stage: str, cells: Cells) -> None:
    if stage == "search":
        found, want = set(cells), set(select35.SEARCH_SETUPS)
        if found != want:
            raise ValueError(
                f"{dataset}: search setups differ from the 72-setup grid: missing"
                f" {sorted(want - found)}, extra {sorted(found - want)}"
            )
        return
    count = len([s for s in cells if select35.parse_setup(s).t20k == (stage == "t20k")])
    if count != STAGE_SIZES[stage]:
        raise ValueError(f"{dataset}: {count} {stage} answer setups, expected {STAGE_SIZES[stage]}")


def _dataset_rows(
    dataset: str,
    search: Mapping[str, Cells],
    answers: Mapping[str, Cells],
    docs: Mapping[str, str],
    gated: set[int],
    n_draws: int,
    n_perm: int,
) -> list[dict[str, Any]]:
    family = FAMILIES.get(dataset, ())
    results = []
    for row in ROWS:
        metric = endpoint(row, dataset)
        cells = (search if row.stage == "search" else answers)[metric].get(dataset, {})
        d, excluded = contrast(row, cells)
        result = {
            "row": row.number,
            "hypothesis": row.hypothesis,
            "metric": metric,
            "n": len(d),
            "excluded": excluded,
            **_test(dataset, d, docs, n_draws),
            "not_testable": row.number in gated,
            "holm_p": None,
            "counts": None,
            "sanity_check": dataset == BQ and row.number not in family,
            "exploratory": dataset == LEGAL,
        }
        if row.number in family:
            result["sensitivity_p"], result["sensitivity_method"] = _sensitivity(
                dataset, d, docs, n_perm
            )
        results.append(result)
    in_family = [r for r in results if r["row"] in family]
    if in_family:
        for key, out, flag in (
            ("p_value", "holm_p", "counts"),
            ("sensitivity_p", "sensitivity_holm_p", "sensitivity_counts"),
        ):
            for r, adjusted in zip(in_family, _family(dataset, in_family, key), strict=True):
                r[out] = adjusted
                r[flag] = _counts(ROWS[r["row"] - 1], r["estimate"], adjusted, r["not_testable"])
    return results


def _two_of_three(counted: Mapping[str, Mapping[int, int]], row: int) -> bool:
    return sum(counted.get(d, {}).get(row, 0) > 0 for d in select35.CORE) >= 2


def _both(counted: Mapping[str, Mapping[int, int]], rows: Sequence[int]) -> dict[str, Any]:
    fb, fs = counted.get(FB, {}), counted.get(FS, {})
    holding = [r for r in rows if fb.get(r, 0) != 0 and fb.get(r) == fs.get(r)]
    signs = {fb[r] for r in holding}
    return {
        "holds": bool(holding),
        "rows": holding,
        "sign": signs.pop() if len(signs) == 1 else 0,
        "dataset_dependent": [r for r in rows if fb.get(r, 0) * fs.get(r, 0) < 0],
    }


def verdicts(counted: Mapping[str, Mapping[int, int]]) -> dict[str, Any]:
    """Apply the per-hypothesis rules of section 7.

    Args:
        counted: Per dataset and row, the sign of a counted row (+1 or -1), else 0.

    Returns:
        The verdict of each hypothesis.
    """

    def steps(rows: Sequence[int]) -> dict[str, Any]:
        held = {r: _two_of_three(counted, r) for r in rows}
        n = sum(held.values())
        return {"holds": "full" if n == len(rows) else "part" if n else "no", "steps": held}

    per_dataset = {
        d: counted.get(d, {}).get(5, 0) > 0 and counted.get(d, {}).get(6, 0) > 0
        for d in select35.CORE
    }
    return {
        "H1": steps((1, 2)),
        "H2": {"holds": _two_of_three(counted, 3)},
        "H3": {"holds": _two_of_three(counted, 4)},
        "H4": {"holds": sum(per_dataset.values()) >= 2, "per_dataset": per_dataset},
        "H5": steps((7, 8)),
        "H6": _both(counted, (9, 10)),
        "H7": {"holds": counted.get(FB, {}).get(11, 0) > 0 and counted.get(FS, {}).get(11, 0) > 0},
        "H8a": {"faithfulness": _both(counted, (12, 13)), "correctness": _both(counted, (14, 15))},
        "H8b": {"faithfulness": _both(counted, (16, 17)), "correctness": _both(counted, (18, 19))},
    }


def h8b_questions(answers: Iterable[Mapping[str, Any]]) -> dict[str, set[str]]:
    """Return per dataset the questions with a cut total of at least 19,456 in every t20k record."""
    seen: dict[str, dict[str, bool]] = {}
    for row in answers:
        if select35.parse_setup(row["setup"]).t20k:
            per = seen.setdefault(row["dataset"], {})
            qid = str(row["qid"])
            per[qid] = per.get(qid, True) and row[CUT_TOKENS] >= CUT_MIN
    return {d: {q for q, ok in per.items() if ok} for d, per in seen.items()}


def _h8b_sensitivity(
    answers: Sequence[Mapping[str, Any]], tables: Mapping[str, Mapping[str, Cells]]
) -> dict[str, Any]:
    kept = h8b_questions(answers)
    out: dict[str, Any] = {}
    for dataset in sorted(kept):
        estimates = {}
        for row in ROWS[15:]:
            cells = tables[endpoint(row, dataset)].get(dataset, {})
            subset = {
                s: {q: v for q, v in c.items() if q in kept[dataset]} for s, c in cells.items()
            }
            d, _ = contrast(row, subset)
            estimates[row.number] = math.fsum(d.values()) / len(d) if d else math.nan
        out[dataset] = {"questions_kept": len(kept[dataset]), "estimates": estimates}
    fb, fs = out.get(FB, {}).get("estimates", {}), out.get(FS, {}).get("estimates", {})
    out["agrees"] = {r: _sign(fb.get(r, 0.0)) * _sign(fs.get(r, 0.0)) > 0 for r in range(16, 20)}
    out["sign"] = {r: _sign(fb.get(r, 0.0)) if out["agrees"][r] else 0 for r in range(16, 20)}
    return out


def _claims(hypotheses: Mapping[str, Any], sensitivity: Mapping[str, Any]) -> dict[str, str | None]:
    claims: dict[str, str | None] = {}
    for outcome in ("faithfulness", "correctness"):
        h8a, h8b = hypotheses["H8a"][outcome], hypotheses["H8b"][outcome]
        itself = any(
            sensitivity["sign"][r] != 0 and sensitivity["sign"][r] == h8b["sign"]
            for r in h8b["rows"]
        )
        claims[outcome] = (
            "chunk size itself changes it"
            if h8b["holds"] and itself
            else "chunk size together with context length changes it"
            if h8a["holds"] and not h8b["holds"]
            else None
        )
    return claims


def analyse(
    search_records: Sequence[Mapping[str, Any]],
    answer_records: Sequence[Mapping[str, Any]],
    *,
    not_testable: Mapping[str, set[int]] | None = None,
    n_draws: int = stats_cluster.SIGN_FLIP_DRAWS,
    n_perm: int = PERM_SHUFFLES,
) -> dict[str, Any]:
    """Run the factorial analysis on all questions.

    Args:
        search_records: Per-question search score records (72 setups).
        answer_records: Per-question answer score records, one per run (15 setups).
        not_testable: Per dataset, the rows a failed gate or the differential-error
            rule makes "not testable" (p = 1, kept in the family).
        n_draws: FinanceBench sign-flip draws (100,000 registered).
        n_perm: Paired permutation shuffles of the sensitivity check (10,000 registered).

    Returns:
        Per dataset rows, hypothesis verdicts, the decision and sensitivity
        disagreement table, the H6 FinanceBench sensitivity and the H8b sensitivity.

    Raises:
        ValueError: A setup grid is incomplete, or a family p-value is NaN.
    """
    gated = not_testable or {}
    search = {m: cell_means(search_records, m) for m in (NDCG, EVIDENCE)}
    answers = {m: cell_means(answer_records, m) for m in (FAITH, CORRECT)}
    docs = _documents([*search_records, *answer_records])
    datasets = sorted(set(search[NDCG]) | set(answers[FAITH]))
    for dataset in datasets:
        _check_stage(dataset, "search", search[NDCG].get(dataset, {}))
        for stage in ("crossed", "t20k"):
            _check_stage(dataset, stage, answers[FAITH].get(dataset, {}))
    by_dataset = {
        d: _dataset_rows(
            d, search, answers, docs.get(d, {}), set(gated.get(d, ())), n_draws, n_perm
        )
        for d in datasets
    }
    counted = {
        d: {r["row"]: _sign(r["estimate"]) if r["counts"] else 0 for r in rows}
        for d, rows in by_dataset.items()
        if d in FAMILIES
    }
    hypotheses = verdicts(counted)
    disagreements = [
        {
            "dataset": d,
            "row": r["row"],
            "decision_counts": r["counts"],
            "sensitivity_counts": r["sensitivity_counts"],
            "sensitivity_method": r["sensitivity_method"],
        }
        for d, rows in by_dataset.items()
        for r in rows
        if r["counts"] is not None and r["counts"] != r["sensitivity_counts"]
    ]
    h6_fb = []
    if FB in by_dataset:
        main = {r["row"]: r for r in by_dataset[FB]}
        for row in ROWS[8:10]:
            d, _ = contrast(row, search[NDCG][FB])
            test = _test(FB, d, docs[FB], n_draws)
            h6_fb.append(
                {
                    "row": row.number,
                    "metric": NDCG,
                    **test,
                    "sign_agrees": _sign(test["estimate"]) == _sign(main[row.number]["estimate"]),
                }
            )
    tables = {**search, **answers}
    sensitivity = _h8b_sensitivity(answer_records, tables)
    return {
        "datasets": by_dataset,
        "hypotheses": hypotheses,
        "disagreements": disagreements,
        "h6_financebench_sensitivity": h6_fb,
        "h8b_sensitivity": sensitivity,
        "claims": _claims(hypotheses, sensitivity),
    }


def headline(
    records: Iterable[Mapping[str, Any]],
    setup: str,
    metric: str,
    halves: Mapping[str, Mapping[str, str]],
    *,
    n_draws: int = stats_cluster.SIGN_FLIP_DRAWS,
) -> dict[str, dict[str, Any]]:
    """Return the RQ1 headline: ``setup``'s mean ``metric`` on half B per core dataset.

    The interval uses the section 9 method: the document sign-flip inversion on
    FinanceBench, the bias-reduced test elsewhere. Answer scores average runs first.
    """
    rows = list(records)
    cells = cell_means(rows, metric)
    docs = _documents(rows)
    out = {}
    for dataset in select35.CORE:
        scores = {
            q: v
            for q, v in cells.get(dataset, {}).get(setup, {}).items()
            if halves[dataset].get(q) == "B"
        }
        result = _test(dataset, scores, docs.get(dataset, {}), n_draws)
        out[dataset] = {"setup": setup, "metric": metric, "half": "B", "n": len(scores), **result}
    return out


def setup_table(search_records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Return the descriptive 72-setup table: mean nDCG@10 per setup and dataset, all questions."""
    cells = cell_means(search_records, NDCG)
    scores: dict[str, dict[str, float]] = {}
    for dataset in sorted(cells):
        for setup, values in cells[dataset].items():
            scores.setdefault(setup, {})[dataset] = math.fsum(values.values()) / len(values)
    return {"descriptive": True, "metric": NDCG, "scores": scores}
