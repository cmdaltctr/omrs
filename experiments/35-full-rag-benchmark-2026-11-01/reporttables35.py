"""Report tables of Experiment 35 (task 16.20; pre-registration sections 10, 12, 13 and 21).

Usage (reads saved files only; runs on the Mac)::

    reporttables35.py --out-dir OUT [--factorial FACTORIAL_JSON] [--records POD.jsonl ...]
        [--rates RATES_JSON] [--passages-dir PASSAGES]

Writes ``<out>/report-tables.json`` with:

- ``chunk_lengths``: the realised chunk-length distribution (pinned Qwen3
  tokens) per chunk-size level and dataset, over the distinct stored chunks in
  the saved top-100 search lists (the search stage saves token counts, no text);
- ``unmapped_chunks``: per dataset and setup, the unmapped chunks of both halves;
- ``drops``: each drop step that ``drops.json`` holds, with its name;
- ``h8b_token_totals``: per dataset and ``-t20k`` setup, the cut total and the
  realised (assembled) evidence token total, over all questions and over the
  H8b sensitivity set (questions kept by cut total, never by realised total);
- ``sesoi_lines``: per row the SESOI reading (nDCG@10 rows only) and the "not
  testable" and "dropped" marks (needs ``--factorial``; no MDE line since A10);
- ``sensitivity``: the one sensitivity table set (needs ``--factorial``);
- ``unjudged``: per dataset, the unjudged share at 10 per setup and the
  condensed-list nDCG@10 rows 1 to 8 (H1 to H5) where the qrels list judged
  non-relevant units, else the statement that neither can be computed
  (``unjudged35.report``, over the score records of both halves);
- ``alpha_ndcg_freshstack``: ``<out>/alpha-ndcg.json`` as ``alphandcg35.py``
  wrote it (run it first), else "not run";
- ``hybrid_trigger``: audit trigger (a), hybrid on against off on FreshStack
  (``unjudged35.hybrid_trigger``), "not defined" without FreshStack scores;
- ``number_match``, ``compute`` (``--records`` pod run-record files and the
  ``--rates`` budget rates file) and ``fenced_rows`` (``--passages-dir``):
  ``reportextra35``; "not defined" without their inputs. The sensitivity set
  adds faithfulness with uncited factual segments as unsupported.

Other inputs it reads when present: ``answer-scores.jsonl``,
``contamination.json`` (``contamination35.py``) and
``lengthcheck/lengthcheck.json`` (``lengthcheck35.py``). The tables hold
half-B scores, so ``main`` runs behind the half-B guard.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

EXP_DIR = Path(__file__).resolve().parent
for _folder in (EXP_DIR.parent.parent, EXP_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import bounds35  # noqa: E402
import budget35  # noqa: E402
import cells35  # noqa: E402
import datasets35  # noqa: E402
import reportextra35  # noqa: E402
import scoring35  # noqa: E402
import select35  # noqa: E402
import unjudged35  # noqa: E402
from outputs35 import Layout, read_rows, write_json  # noqa: E402

SESOI = 0.02
READ_AGAINST = (0.01, 0.02, 0.05)
SMALL_EFFECT = "cannot rule out a small effect"
LENGTH_SOURCE = "distinct stored chunks in the saved top-100 search lists (pinned Qwen3 tokens)"
#: The one sensitivity table set of section 21 (A5: no any-page or page-rule table).
SENSITIVITY_TABLES = (
    "clustered_vs_sensitivity",
    "missing_outcome_bounds",
    "closed_book_subset",
    "length_controlled_check",
    "financebench_ndcg_rows_9_10",
    "h8b_cut_total",
    "faithfulness_uncited_as_unsupported",
)
NOT_RUN = {"status": "not run"}


def chunk_lengths(lists: Iterable[tuple[str, str, Mapping[str, Any]]]) -> dict[str, Any]:
    """Return per dataset and chunk-size level the token-length distribution of stored chunks.

    Args:
        lists: ``(dataset, search setup, saved search row)``; each row's ``chunks``
            hold ``chunk_id`` and ``tokens``. A chunk ID seen in several lists of
            one dataset and level counts once.
    """
    seen: dict[tuple[str, int], dict[str, int]] = {}
    for dataset, setup, row in lists:
        level = select35.parse_setup(setup).chunk
        per = seen.setdefault((dataset, level), {})
        for chunk in row.get("chunks") or ():
            per.setdefault(str(chunk["chunk_id"]), int(chunk["tokens"]))
    out: dict[str, Any] = {"source": LENGTH_SOURCE}
    for (dataset, level), per in sorted(seen.items()):
        values = np.array(sorted(per.values()), dtype=float)
        p = np.percentile(values, [5, 25, 50, 75, 95])
        out.setdefault(dataset, {})[str(level)] = {
            "chunks": len(values),
            "min": int(values.min()),
            "p05": float(p[0]),
            "p25": float(p[1]),
            "median": float(p[2]),
            "p75": float(p[3]),
            "p95": float(p[4]),
            "max": int(values.max()),
            "mean": float(values.mean()),
        }
    return out


def chunk_length_table(out: Path) -> dict[str, Any]:
    """Return :func:`chunk_lengths` over every saved search list under *out*."""
    return chunk_lengths(
        (dataset, setup, row)
        for dataset, setup, run, folder in Layout(out).runs("search", "search.jsonl")
        if run == 1
        for row in read_rows(folder / "search.jsonl")
    )


def unmapped_counts(out: Path) -> dict[str, dict[str, int]]:
    """Return per dataset and setup the unmapped chunks over both halves' ``summary.json``."""
    counts: dict[str, dict[str, int]] = {}
    for path in sorted((out / "scores").glob("[AB]/*/summary.json")):
        dataset = path.parent.name
        for setup, summary in json.loads(path.read_text(encoding="utf-8")).items():
            per = counts.setdefault(dataset, {})
            per[setup] = per.get(setup, 0) + int(summary["unmapped_chunks"])
    return counts


def drop_record(out: Path) -> list[dict[str, Any]]:
    """Return each drop step of ``<out>/drops.json`` with its name, in step order."""
    return [{"step": s, "name": budget35.DROP_STEPS[s]} for s in sorted(budget35.read_drops(out))]


def _mean(values: Sequence[float]) -> float | None:
    return math.fsum(values) / len(values) if values else None


def h8b_token_totals(answer_records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Return per dataset and ``-t20k`` setup the cut and realised evidence token totals.

    A question's totals come from the first run that saved them (G1: every run
    of a setup holds the same list). ``evidence_tokens`` is the realised total.
    """
    rows = list(answer_records)
    kept = cells35.h8b_questions(rows)
    found: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for row in rows:
        if not select35.parse_setup(row["setup"]).t20k:
            continue
        per = found.setdefault((row["dataset"], row["setup"]), {}).setdefault(str(row["qid"]), {})
        for key in (cells35.CUT_TOKENS, "evidence_tokens"):
            if per.get(key) is None and row.get(key) is not None:
                per[key] = int(row[key])
    out: dict[str, Any] = {}
    for (dataset, setup), questions in sorted(found.items()):
        both = [q for q in questions.values() if len(q) == 2]
        inside = [questions[q] for q in sorted(kept.get(dataset, set())) if q in questions]
        below = sum(1 for q in both if q["evidence_tokens"] < q[cells35.CUT_TOKENS])
        out.setdefault(dataset, {})[setup] = {
            "questions": len(questions),
            "questions_kept": len(inside),
            "all": {
                "mean_cut_tokens": _mean([q[cells35.CUT_TOKENS] for q in both]),
                "mean_realised_tokens": _mean([q["evidence_tokens"] for q in both]),
            },
            "kept": {
                "mean_cut_tokens": _mean([q[cells35.CUT_TOKENS] for q in inside if len(q) == 2]),
                "mean_realised_tokens": _mean(
                    [q["evidence_tokens"] for q in inside if len(q) == 2]
                ),
            },
            "realised_below_cut": below,
            "share_realised_below_cut": below / len(both) if both else None,
            "no_cut_total": sum(1 for q in questions.values() if cells35.CUT_TOKENS not in q),
            "no_realised_total": sum(1 for q in questions.values() if "evidence_tokens" not in q),
        }
    return out


def _reading(low: float, high: float, t: float) -> str:
    if low <= t <= high or low <= -t <= high:
        return "cannot exclude"
    return "within" if -t < low and high < t else "beyond"


def sesoi_lines(
    rows_by_dataset: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Return per row the SESOI reading and its marks (sections 10 and 21).

    Only nDCG@10 rows have a SESOI (0.02); their interval is read against plus
    and minus 0.01, 0.02 and 0.05. An interval that cannot exclude 0.02 reads
    "cannot rule out a small effect". Other rows get the marks only.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for dataset, rows in rows_by_dataset.items():
        for row in rows:
            status = (
                "dropped"
                if row.get("dropped")
                else "not testable"
                if row.get("not_testable")
                else "tested"
            )
            line: dict[str, Any] = {
                "row": row["row"],
                "metric": row["metric"],
                "status": status,
                "sesoi": None,
                "sesoi_reading": None,
                "readings": None,
            }
            low, high = row.get("ci_low"), row.get("ci_high")
            usable = low is not None and high is not None and not math.isnan(low + high)
            if row["metric"] == select35.NDCG and not row.get("dropped") and usable:
                readings = {str(t): _reading(low, high, t) for t in READ_AGAINST}
                main = readings[str(SESOI)]
                line |= {
                    "sesoi": SESOI,
                    "readings": readings,
                    "sesoi_reading": SMALL_EFFECT
                    if main == "cannot exclude"
                    else f"{main} {SESOI}",
                }
            out.setdefault(dataset, []).append(line)
    return out


def financebench_ndcg(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the FinanceBench nDCG@10 table for rows 9 and 10 with sign agreement.

    The endpoint of these rows is ``evidence_recall_20k`` (a chunk covers its
    page); ``sign_agrees`` compares each row's nDCG@10 sign with it.
    """
    return [
        {**row, "endpoint": "evidence_recall_20k"}
        for row in result.get("h6_financebench_sensitivity", ())
    ]


def sensitivity_set(
    result: Mapping[str, Any],
    *,
    bounds: Mapping[str, Any] | None = None,
    contamination: Mapping[str, Any] | None = None,
    length_check: Mapping[str, Any] | None = None,
    token_totals: Mapping[str, Any] | None = None,
    uncited: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the one sensitivity table set; a table with no input reads "not run"."""
    tables = {
        "clustered_vs_sensitivity": result.get("disagreements", []),
        "missing_outcome_bounds": bounds,
        "closed_book_subset": contamination,
        "length_controlled_check": length_check,
        "financebench_ndcg_rows_9_10": financebench_ndcg(result),
        "h8b_cut_total": {**result.get("h8b_sensitivity", {}), "token_totals": token_totals},
        "faithfulness_uncited_as_unsupported": uncited,
    }
    return {name: NOT_RUN if tables[name] is None else tables[name] for name in SENSITIVITY_TABLES}


def load_qrels(names: Iterable[str]) -> dict[str, dict[str, dict[str, int]]]:
    """Return the qrels of each dataset in *names* from the data folder (``datasets35.qrels``)."""
    root = datasets35.data_root()
    return {name: datasets35.qrels(name, root) for name in sorted(names)}


def _score_records(out: Path) -> list[dict[str, Any]]:
    return [
        row for path in sorted((out / "scores").glob("[AB]/*/*.jsonl")) for row in read_rows(path)
    ]


def unjudged_table(out: Path) -> dict[str, Any] | None:
    """Return :func:`unjudged35.report` over the search score records of both halves."""
    records = _score_records(out)
    if not records:
        return None
    return unjudged35.report(records, load_qrels({r["dataset"] for r in records}))


def hybrid_trigger_table(out: Path) -> dict[str, Any] | str:
    """Return audit trigger (a) on all FreshStack questions, else "not defined"."""
    records = [r for r in _score_records(out) if r["dataset"] == unjudged35.FRESHSTACK]
    if not records:
        return reportextra35.NOT_DEFINED
    return unjudged35.hybrid_trigger(
        records, load_qrels({unjudged35.FRESHSTACK}).get("freshstack", {})
    )


def number_match(out: Path) -> dict[str, Any] | str:
    """Return the FinanceBench number match per answer setup, else "not defined"."""
    if not Layout(out).runs("answer", "answer.jsonl", dataset=reportextra35.FB):
        return reportextra35.NOT_DEFINED
    return reportextra35.number_match_table(out, reportextra35.load_references())


def compute(records: Sequence[Path], rates: Path | None) -> dict[str, Any] | str:
    """Return the compute table from the pod run records, else "not defined"."""
    if not records:
        return reportextra35.NOT_DEFINED
    price = (_json(rates) or {}).get("pod_usd_per_hour") if rates else None
    pods = reportextra35.pod_records(records)
    return reportextra35.compute_table(pods, None if price is None else float(price))


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def main(argv: Sequence[str] | None = None) -> int:
    """Write ``<out>/report-tables.json``; return 0."""
    parser = argparse.ArgumentParser(prog="reporttables35.py", description=__doc__.split("\n")[0])
    parser.add_argument("--out-dir", type=Path, required=True, help="the joined output folder")
    parser.add_argument("--factorial", type=Path, help="confirmatory.json (analyse35.py)")
    parser.add_argument("--records", type=Path, nargs="*", default=[], help="pod run records")
    parser.add_argument("--rates", type=Path, help="budget rates file (pod_usd_per_hour)")
    parser.add_argument("--passages-dir", type=Path, help="the prepared passages folder")
    args = parser.parse_args(argv)
    out = args.out_dir
    scoring35.require_half_b(out)  # the tables hold half-B scores (section 14.2)
    answers = read_rows(out / "answer-scores.jsonl")
    totals = h8b_token_totals(answers)
    result = _json(args.factorial) if args.factorial else None
    tables = {
        "chunk_lengths": chunk_length_table(out),
        "unmapped_chunks": unmapped_counts(out),
        "drops": drop_record(out),
        "h8b_token_totals": totals,
        "sesoi_lines": None if result is None else sesoi_lines(result["datasets"]),
        "sensitivity": None
        if result is None
        else sensitivity_set(
            result,
            bounds=bounds35.missing_outcome_bounds(answers) if answers else None,
            contamination=_json(out / "contamination.json"),
            length_check=_json(out / "lengthcheck" / "lengthcheck.json"),
            token_totals=totals,
            uncited=reportextra35.uncited_sensitivity(
                answers, (_json(out / "join.json") or {}).get("uncited_segment_share", {})
            )
            if answers
            else None,
        ),
        "unjudged": unjudged_table(out),
        # alphandcg35.py writes it with the pinned FreshStack scorer (secondary, descriptive).
        "alpha_ndcg_freshstack": _json(out / "alpha-ndcg.json") or NOT_RUN,
        "hybrid_trigger": hybrid_trigger_table(out),
        "number_match": number_match(out),
        "compute": compute(args.records, args.rates),
        "fenced_rows": reportextra35.fenced_rows(args.passages_dir)
        if args.passages_dir
        else reportextra35.NOT_DEFINED,
    }
    write_json(out / "report-tables.json", tables)
    print(f"[report-tables] {out / 'report-tables.json'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
