"""Factorial analysis of Experiment 35 (pre-registration sections 7 to 9 and 14.3).

Readiness tasks 14.4, 15.6 and 15.7. Reads plain per-question score records
and returns the contrast table of section 8 (rows 1 to 19), the Holm families,
the hypothesis verdicts of section 7 and the registered sensitivity analyses.

A score record is a mapping with ``dataset``, ``setup``, ``qid``,
``doc_id`` (FinanceBench), ``run`` (answer records) and metric keys:
``ndcg_at_10``, ``evidence_recall_20k``, ``faithfulness_glm_factual``,
``ragas_answer_correctness``; ``-t20k`` answer records also carry
``cut_tokens`` (the kept stored chunks before assembly), and an ``unjudged``
list of metric keys whose checker or Ragas row closed missing. A missing or
None metric means "no value" (section 12): the cell mean uses the runs that
have one, and a question enters a row only when every cell of the row has a
value. An unjudged run drops its whole cell (``cells35``). Each row counts
the questions it left out (``excluded``), split into ``excluded_unjudged``,
``excluded_not_defined`` (a Ragas NaN) and ``excluded_no_value``, against
every question of the dataset (the questions of its search records). After
drop step 1 (Legal answers removed) Legal answer rows 12 to 19 are marked
``dropped``.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import budget35
import determinism35
import labels35
import scoring35
import select35
from cells35 import (
    Cells,
    cell_means,
    contrast,
    documents,
    excluded_counts,
    h8b_questions,
    no_cut_total,
    unjudged_cells,
)
from experiments._lib import stats_cluster
from experiments._lib.stats_d6 import holm, paired_permutation
from outputs35 import write_json
from verdicts35 import verdicts

FB, FS, BQ = select35.CORE
LEGAL = "legal"
NDCG = "ndcg_at_10"
EVIDENCE = "evidence_recall_20k"
FAITH = "faithfulness_glm_factual"
CORRECT = "ragas_answer_correctness"
ALPHA = 0.05
PERM_SEED = 20261101
PERM_SHUFFLES = 10_000
FAMILIES = {FB: tuple(range(1, 20)), FS: tuple(range(1, 20)), BQ: tuple(range(1, 9))}
STAGE_SIZES = {"search": 72, "crossed": 12, "t20k": 3}
ON = ("0.6b", "4b", "8b")


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


def _marks(tables: Mapping[str, Any], metric: str, dataset: str) -> dict[str, Any]:
    return {k: v.get(dataset, {}) for k, v in tables["marks"][metric].items()}


def _dropped(row: Row, metric: str) -> dict[str, Any]:
    """Return an answer row of a dataset whose answers drop step 1 removed (section 17)."""
    return {"row": row.number, "hypothesis": row.hypothesis, "metric": metric, "dropped": True}


def _dataset_rows(
    dataset: str,
    tables: Mapping[str, Any],
    docs: Mapping[str, str],
    gated: set[int],
    n_draws: int,
    n_perm: int,
) -> list[dict[str, Any]]:
    family = FAMILIES.get(dataset, ())
    questions = tables["questions"][dataset]
    results = []
    for row in ROWS:
        metric = endpoint(row, dataset)
        if row.stage != "search" and dataset in tables["dropped"]:
            results.append(_dropped(row, metric))
            continue
        cells = tables[metric].get(dataset, {})
        d, excluded = contrast(row, cells, questions)
        result = {
            "row": row.number,
            "hypothesis": row.hypothesis,
            "metric": metric,
            "n": len(d),
            "excluded": excluded,
            **excluded_counts(row, cells, d, questions, _marks(tables, metric, dataset)),
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


def _h8b_sensitivity(
    answers: Sequence[Mapping[str, Any]], tables: Mapping[str, Any], hypotheses: Mapping[str, Any]
) -> dict[str, Any]:
    kept = h8b_questions(answers)
    out: dict[str, Any] = {}
    for dataset in sorted(kept):
        estimates, n = {}, {}
        for row in ROWS[15:]:
            cells = tables[endpoint(row, dataset)].get(dataset, {})
            subset = {
                s: {q: v for q, v in c.items() if q in kept[dataset]} for s, c in cells.items()
            }
            d, _ = contrast(row, subset, sorted(kept[dataset]))
            estimates[row.number] = math.fsum(d.values()) / len(d) if d else math.nan
            n[row.number] = len(d)
        out[dataset] = {
            "questions": len(tables["questions"][dataset]),
            "questions_kept": len(kept[dataset]),
            "no_cut_total": no_cut_total(answers, dataset),
            "n": n,
            "estimates": estimates,
        }
    fb, fs = out.get(FB, {}).get("estimates", {}), out.get(FS, {}).get("estimates", {})
    # Protocol 0.14 item 65: each row must have that row's H8b sign on both datasets.
    target = {}
    for r in range(16, 20):
        h8b = hypotheses["H8b"]["faithfulness" if r < 18 else "correctness"]
        target[r] = h8b["sign"] if r in h8b["rows"] else 0
    out["agrees"] = {
        r: target[r] != 0 and _sign(fb.get(r, 0.0)) == _sign(fs.get(r, 0.0)) == target[r]
        for r in range(16, 20)
    }
    out["sign"] = {r: target[r] if out["agrees"][r] else 0 for r in range(16, 20)}
    return out


def _claims(hypotheses: Mapping[str, Any], sensitivity: Mapping[str, Any]) -> dict[str, str | None]:
    claims: dict[str, str | None] = {}
    for outcome in ("faithfulness", "correctness"):
        h8a, h8b = hypotheses["H8a"][outcome], hypotheses["H8b"][outcome]
        itself = any(
            sensitivity["sign"][r] != 0 and sensitivity["sign"][r] == h8b["sign"]
            for r in h8b["rows"]
        )
        # Protocol 0.14 item 26: the registered claim names the fixed pre-assembly budget.
        claims[outcome] = (
            f"chunk size changes {outcome} at a fixed pre-assembly evidence budget"
            if h8b["holds"] and itself
            else f"chunk size together with context length changes {outcome}"
            if h8a["holds"] and not h8b["holds"]
            else None
        )
    return claims


def _questions(search_records: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Return per dataset every question: a missing search scores 0 and keeps its record."""
    found: dict[str, set[str]] = {}
    for row in search_records:
        found.setdefault(row["dataset"], set()).add(str(row["qid"]))
    return {d: sorted(q) for d, q in found.items()}


def analyse(
    search_records: Sequence[Mapping[str, Any]],
    answer_records: Sequence[Mapping[str, Any]],
    *,
    not_testable: Mapping[str, set[int]] | None = None,
    n_draws: int = stats_cluster.SIGN_FLIP_DRAWS,
    n_perm: int = PERM_SHUFFLES,
    dropped: Collection[str] = (),
) -> dict[str, Any]:
    """Run the factorial analysis on all questions.

    Args:
        search_records: Per-question search score records (72 setups).
        answer_records: Per-question answer score records, one per run (15 setups).
        not_testable: Per dataset, the rows a failed gate or the differential-error
            rule makes "not testable" (p = 1, kept in the family).
        n_draws: FinanceBench sign-flip draws (100,000 registered).
        n_perm: Paired permutation shuffles of the sensitivity check (10,000 registered).
        dropped: Datasets whose answers drop step 1 removed (``budget35``); their
            answer rows are marked ``dropped`` and their search rows still run.

    Returns:
        Per dataset rows, hypothesis verdicts, the decision and sensitivity
        disagreement table, the H6 FinanceBench sensitivity and the H8b sensitivity.

    Raises:
        ValueError: A setup grid is incomplete, or a family p-value is NaN.
    """
    gated = not_testable or {}
    search = {m: cell_means(search_records, m) for m in (NDCG, EVIDENCE)}
    answers = {m: cell_means(answer_records, m) for m in (FAITH, CORRECT)}
    # Search records come from the gold table, so they win over answer rows.
    docs = documents([*answer_records, *search_records])
    datasets = sorted(set(search[NDCG]) | set(answers[FAITH]))
    for dataset in datasets:
        _check_stage(dataset, "search", search[NDCG].get(dataset, {}))
        for stage in ("crossed", "t20k") if dataset not in dropped else ():
            _check_stage(dataset, stage, answers[FAITH].get(dataset, {}))
    tables: dict[str, Any] = {
        **search,
        **answers,
        "questions": _questions(search_records),
        "marks": {
            m: {k: unjudged_cells(answer_records, m, k) for k in ("unjudged", "not_defined")}
            for m in (FAITH, CORRECT, *search)
        },
        "dropped": frozenset(dropped),
    }
    by_dataset = {
        d: _dataset_rows(d, tables, docs.get(d, {}), set(gated.get(d, ())), n_draws, n_perm)
        for d in datasets
    }
    counted = {
        d: {r["row"]: _sign(r["estimate"]) if r.get("counts") else 0 for r in rows}
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
        if r.get("counts") is not None and r["counts"] != r["sensitivity_counts"]
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
    sensitivity = _h8b_sensitivity(answer_records, tables, hypotheses)
    return {
        "datasets": by_dataset,
        "hypotheses": hypotheses,
        "disagreements": disagreements,
        "h6_financebench_sensitivity": h6_fb,
        "h8b_sensitivity": sensitivity,
        "claims": _claims(hypotheses, sensitivity),
    }


def write_confirmatory(
    path: Path,
    search_records: Sequence[Mapping[str, Any]],
    answer_records: Sequence[Mapping[str, Any]],
    *,
    label_dir: Path,
    root: Path,
    n_draws: int = stats_cluster.SIGN_FLIP_DRAWS,
    n_perm: int = PERM_SHUFFLES,
) -> dict[str, Any]:
    """Write the confirmatory result to *path*, only after half B opens and both gate files exist.

    The result holds half-B scores, so the half-B guard (section 14.2) runs
    first on the run output folder *root*. The gate rows of
    ``labels35.require_gates`` become "not testable" (p = 1); *path* also
    records them under ``gates``. Drop step 1 in ``<root>/drops.json`` marks
    the Legal answer rows ``dropped``.

    Raises:
        scoring35.HalfBLocked: Half B is not open; nothing is computed or written.
        stages35.StageOrderError: ``<root>/join.json`` is missing, fails or is a smoke join.
        labels35.GateMissing: A gate file is missing; nothing is computed or written.
    """
    scoring35.require_half_b(root)
    determinism35.require_join(root)
    gated = labels35.require_gates(label_dir)
    kept = budget35.answer_datasets(budget35.read_drops(root))
    result = analyse(
        search_records,
        answer_records,
        not_testable=gated,
        n_draws=n_draws,
        n_perm=n_perm,
        dropped=[d for d in budget35.QUESTIONS if d not in kept],
    )
    write_json(path, {**result, "gates": {d: sorted(rows) for d, rows in gated.items()}})
    return result


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
    docs = documents(rows)
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
