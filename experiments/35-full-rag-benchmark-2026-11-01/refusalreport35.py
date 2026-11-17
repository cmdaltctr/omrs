"""Refusal report for Experiment 35 (task 8.9; design D13; pre-registration section 12).

Usage (reads saved files only, runs on the Mac)::

    refusalreport35.py --out-dir OUT --gate GATE_JSON

It refuses without a passing join (``OUT/join.json`` with ``ok: true``) and
without a frozen classifier version (``gate.json`` with ``pass: true``), and
refuses any saved kind from another version. Each run uses its own saved
kinds. It writes ``OUT/refusals.json``:

- ``faithfulness``: per checker (GLM-5.3 ``chat``, Clef-Flash), dataset and
  answer setup. ``primary`` uses factual and mixed claims; an unclassified
  claim counts as factual and is counted. Sensitivity tables: no-claim
  answers scored 1 and scored 0, an unjudged checker row scored 0,
  unclassified claims left out; ``all_claims`` is secondary robustness.
- ``bounds``: faithfulness on all claims when only one checker's refusal
  verdicts change to all supported (high) and all unsupported (low).
- ``refusal_rate`` (primary descriptive), each checker's unsupported rate on
  refusal claims, and the Clef-Flash against GLM-5.3 kappa on refusal and on
  factual and mixed claims, per dataset. The two rates take their 95% interval
  from ``bootstrap35.bootstrap_by_question`` (10,000 resamples by question,
  seed ``SEED``), because the claims of one question are not independent. An
  interval that is not testable (fail closed, section 11.2) is written as null.
- ``kind_disagreements``: claim texts with different kinds in different runs.

Missing outcomes (pre-registration section 12): every question stays in the
denominator. A run's faithfulness is undefined when the answer has no counted
claim; a missing answer counts as an answer with no factual claim. Per
question and setup, faithfulness is the mean over runs with a value. A cell
with an unjudged run leaves the complete cases and is counted.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import claimkinds35
from bootstrap35 import bootstrap_by_question
from experiments._lib.stats_d6 import cohen_kappa, paired_bootstrap
from outputs35 import Layout, read_rows, write_json

SEED = 20261136  # pre-registration section 16: refusal report bootstrap (owner confirms at P9)
CHECKERS = ("chat", "clef_flash")
FACTUAL = ("factual", "mixed")
NO_CLAIM = "no_claim"
UNJUDGED = "unjudged"
STATUS = {
    "primary": "primary",
    "no_claim_scored_1": "sensitivity",
    "no_claim_scored_0": "sensitivity",
    "unjudged_scored_0": "sensitivity",
    "unclassified_left_out": "sensitivity",
    "all_claims": "secondary robustness",
}


class ReportError(RuntimeError):
    """The inputs of the report are not ready."""


@dataclass
class Claim:
    """One claim of one answer run: its question, key, saved kind and each checker's verdict."""

    qid: str
    key: str
    kind: str | None
    verdicts: dict[str, str | None]


@dataclass
class RunAnswer:
    """One answer of one run and its claims (a claim without a verdict is unjudged)."""

    missing: bool
    claims: list[Claim] = field(default_factory=list)


def _verdict(v: dict[str, Any]) -> str | None:
    return v.get("verdict") if v.get("verdict") in ("supported", "unsupported") else None


def _load_run(folder: Path, version: str) -> dict[str, RunAnswer]:
    kinds_rows = read_rows(folder / "claim-kinds.jsonl")
    if any(r.get("version") != version for r in kinds_rows):
        raise ReportError(f"{folder}: a saved kind has another classifier version than {version}")
    kinds = {r["claim_key"]: r["kind"] for r in kinds_rows}
    judges = {c: {r["qid"]: r for r in read_rows(folder / f"judge-{c}.jsonl")} for c in CHECKERS}
    where = "/".join(folder.parts[-4:])
    out: dict[str, RunAnswer] = {}
    for row in read_rows(folder / "answer.jsonl"):
        qid = row["qid"]
        texts = claimkinds35.answer_claims(row)
        if row.get("missing") or not texts and not row.get("answer"):
            out[qid] = RunAnswer(missing=True)
            continue
        verdicts: dict[str, list[str | None]] = {}
        judged: dict[str, bool] = {}
        for c in CHECKERS:
            judge = judges[c].get(qid)
            judged[c] = judge is not None and not judge.get("missing")
            pairs = claimkinds35.align(row, judge, where=f"{where}/{qid}") if judged[c] else []
            verdicts[c] = [_verdict(v) for _, v in pairs] if judged[c] else [None] * len(texts)
        keys = [claimkinds35.claim_key(qid, t) for t in texts]
        claims = [
            Claim(qid, k, kinds.get(k), {c: verdicts[c][i] for c in CHECKERS})
            for i, k in enumerate(keys)
        ]
        out[qid] = RunAnswer(missing=False, claims=claims)
    return out


def load(out_dir: Path, version: str) -> dict[tuple[str, str], dict[int, dict[str, RunAnswer]]]:
    """Return ``(dataset, setup) -> run -> qid -> RunAnswer`` for every answer run folder.

    Raises:
        NoRunFiles: The output folder holds no answer run.
    """
    data: dict[tuple[str, str], dict[int, dict[str, RunAnswer]]] = defaultdict(dict)
    for dataset, setup, run, folder in Layout(out_dir).need_runs("answer", "answer.jsonl"):
        data[(dataset, setup)][run] = _load_run(folder, version)
    return dict(data)


def _unclassified(kind: str | None) -> bool:
    return kind is None or kind == claimkinds35.UNREADABLE


Keep = Callable[[Claim], bool]
Override = Callable[[Claim, str], str | None]


def _run_value(
    ans: RunAnswer | None,
    checker: str,
    keep: Keep,
    *,
    no_claim: float | None,
    unjudged: float | None,
    override: Override | None,
) -> float | str:
    claims = [] if ans is None or ans.missing else [c for c in ans.claims if keep(c)]
    if not claims:
        return NO_CLAIM if no_claim is None else no_claim
    verdicts = [override(c, checker) if override else c.verdicts[checker] for c in claims]
    if any(v is None for v in verdicts):
        return UNJUDGED if unjudged is None else unjudged
    return sum(v == "supported" for v in verdicts) / len(verdicts)


def _cell(values: list[float | str]) -> float | str:
    if UNJUDGED in values:
        return UNJUDGED
    numbers = [v for v in values if not isinstance(v, str)]
    return sum(numbers) / len(numbers) if numbers else NO_CLAIM


def faithfulness(
    runs: dict[int, dict[str, RunAnswer]],
    qids: Sequence[str],
    checker: str,
    keep: Keep,
    *,
    no_claim: float | None = None,
    unjudged: float | None = None,
    override: Override | None = None,
) -> dict[str, Any]:
    """Return the complete-case mean of one setup over *qids*, with exclusion counts."""
    cells = [
        _cell(
            [
                _run_value(
                    answers.get(q),
                    checker,
                    keep,
                    no_claim=no_claim,
                    unjudged=unjudged,
                    override=override,
                )
                for _, answers in sorted(runs.items())
            ]
        )
        for q in qids
    ]
    numbers = [c for c in cells if not isinstance(c, str)]
    return {
        "mean": sum(numbers) / len(numbers) if numbers else None,
        "n": len(numbers),
        "excluded_no_claim": cells.count(NO_CLAIM),
        "excluded_unjudged": cells.count(UNJUDGED),
        "values": numbers,
    }


def _keep(table: str) -> Keep:
    if table == "unclassified_left_out":
        return lambda c: c.kind in FACTUAL
    if table == "all_claims":
        return lambda c: True
    return lambda c: c.kind != "refusal"


_EXTRA: dict[str, dict[str, float]] = {
    "no_claim_scored_1": {"no_claim": 1.0},
    "no_claim_scored_0": {"no_claim": 0.0},
    "unjudged_scored_0": {"unjudged": 0.0},
}


def _ratio(sample: list[tuple[int, int]]) -> float:
    total = sum(t for _, t in sample)
    return sum(h for h, _ in sample) / total if total else math.nan


def _rate(flags: Iterable[tuple[str, bool]], qids: Sequence[str], n_boot: int) -> dict[str, Any]:
    """Return a claim rate with its bootstrap-by-question interval.

    Args:
        flags: ``(question, hit)`` for each claim of the rate's denominator.
        qids: Every question of the dataset; a question with no claim still
            counts as a resampling unit.
        n_boot: Number of resamples.

    Returns:
        ``rate``, ``low``, ``high`` (None when not testable), ``undefined``
        resamples and ``testable``. The rate is None when there is no claim.
    """
    counts = {q: (0, 0) for q in qids}
    for q, hit in flags:
        hits, total = counts[q]
        counts[q] = (hits + hit, total + 1)
    boot = bootstrap_by_question(sorted(counts.items()), _ratio, n=n_boot, seed=SEED, fill=None)
    out = boot.as_dict()
    return {
        "rate": out["estimate"],
        "low": out["lower"],
        "high": out["upper"],
        "undefined": out["undefined"],
        "testable": out["testable"],
    }


def _kappa(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    value = cohen_kappa([a for a, _ in pairs], [b for _, b in pairs])
    return None if math.isnan(value) else value


def _instances(data: dict, dataset: str):
    for (d, _setup), runs in sorted(data.items()):
        if d == dataset:
            for answers in runs.values():
                for ans in answers.values():
                    yield from ans.claims


def build(data: dict, *, n_boot: int) -> dict[str, Any]:
    """Return the ``refusals.json`` record from loaded runs."""
    datasets = sorted({d for d, _ in data})
    qids = {
        d: sorted(
            {q for (dd, _), runs in data.items() if dd == d for a in runs.values() for q in a}
        )
        for d in datasets
    }
    tables: dict[str, Any] = {t: {c: defaultdict(dict) for c in CHECKERS} for t in STATUS}
    bounds: dict[str, Any] = {c: defaultdict(dict) for c in CHECKERS}
    rates: dict[str, Any] = defaultdict(dict)
    unclassified: dict[str, Any] = defaultdict(dict)
    for (dataset, setup), runs in sorted(data.items()):
        for checker in CHECKERS:
            for table in STATUS:
                row = faithfulness(
                    runs, qids[dataset], checker, _keep(table), **_EXTRA.get(table, {})
                )
                values = row.pop("values")
                if table == "primary" and values:
                    _, row["low"], row["high"] = paired_bootstrap(
                        [0.0] * len(values), values, n_boot=n_boot, seed=SEED
                    )
                tables[table][checker][dataset][setup] = row
                if table == "primary":
                    print(
                        f"{dataset} {setup} {checker}: n {row['n']}, no factual claim "
                        f"{row['excluded_no_claim']}, unjudged {row['excluded_unjudged']}",
                        flush=True,
                    )
            bounds[checker][dataset][setup] = {
                side: faithfulness(
                    runs,
                    qids[dataset],
                    checker,
                    _keep("all_claims"),
                    override=lambda c, k, v=verdict: v if c.kind == "refusal" else c.verdicts[k],
                )["mean"]
                for side, verdict in (("high", "supported"), ("low", "unsupported"))
            }
        claims = [c for a in runs.values() for ans in a.values() for c in ans.claims]
        refusals = sum(c.kind == "refusal" for c in claims)
        rates[dataset][setup] = {
            "refusals": refusals,
            "claims": len(claims),
            **_rate([(c.qid, c.kind == "refusal") for c in claims], qids[dataset], n_boot),
            "status": "primary descriptive",
        }
        unclassified[dataset][setup] = sum(_unclassified(c.kind) for c in claims)
    checks: dict[str, Any] = {}
    disagreements: dict[str, int] = {}
    for dataset in datasets:
        claims = list(_instances(data, dataset))
        on_refusals = {}
        for c in CHECKERS:
            judged = [
                (x.qid, x.verdicts[c] == "unsupported")
                for x in claims
                if x.kind == "refusal" and x.verdicts[c] is not None
            ]
            on_refusals[c] = {
                "unsupported": sum(hit for _, hit in judged),
                "claims": len(judged),
                **_rate(judged, qids[dataset], n_boot),
            }
        both = [
            (x.verdicts["clef_flash"], x.verdicts["chat"])
            for x in claims
            if x.verdicts["clef_flash"] is not None and x.verdicts["chat"] is not None
        ]
        kinds = [
            x.kind
            for x in claims
            if x.verdicts["clef_flash"] is not None and x.verdicts["chat"] is not None
        ]
        checks[dataset] = {
            "unsupported_on_refusals": on_refusals,
            "kappa_clef_flash_vs_chat": {
                "refusal": _kappa([p for p, k in zip(both, kinds, strict=True) if k == "refusal"]),
                "factual_and_mixed": _kappa(
                    [p for p, k in zip(both, kinds, strict=True) if k != "refusal"]
                ),
            },
        }
        disagreements[dataset] = _kind_disagreements(data, dataset)
    return {
        "faithfulness": {t: {c: dict(v) for c, v in by.items()} for t, by in tables.items()},
        "faithfulness_status": STATUS,
        "bounds": {c: dict(v) for c, v in bounds.items()},
        "refusal_rate": dict(rates),
        "refusal_checks": checks,
        "unclassified_claims": dict(unclassified),
        "kind_disagreements": disagreements,
    }


def _kind_disagreements(data: dict, dataset: str) -> int:
    """Count claim keys with more than one saved kind across the dataset's runs."""
    seen: dict[str, set[str]] = defaultdict(set)
    for claim in _instances(data, dataset):
        if claim.kind is not None:
            seen[claim.key].add(claim.kind)
    return sum(1 for kinds in seen.values() if len(kinds) > 1)


def write_report(out_dir: Path, *, gate_path: Path, n_boot: int = 10_000) -> Path:
    """Check the inputs, build the report and write ``refusals.json``; return its path.

    Raises:
        ReportError: No passing join, no frozen classifier version, or a kind
            from another version.
    """
    join = out_dir / "join.json"
    if not join.exists() or json.loads(join.read_text(encoding="utf-8")).get("ok") is not True:
        raise ReportError(f"{join}: no passing join")
    gate = json.loads(gate_path.read_text(encoding="utf-8")) if gate_path.exists() else {}
    if gate.get("pass") is not True or not gate.get("version"):
        raise ReportError(f"{gate_path}: no frozen classifier version (gate not passed)")
    record = {
        "classifier_version": gate["version"],
        "seed": SEED,
        "n_boot": n_boot,
        **build(load(out_dir, gate["version"]), n_boot=n_boot),
    }
    path = out_dir / "refusals.json"
    write_json(path, record)
    return path


def main(argv: Sequence[str] | None = None) -> int:
    """Write the refusal report."""
    parser = argparse.ArgumentParser(prog="refusalreport35.py")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--gate", type=Path, required=True)
    args = parser.parse_args(argv)
    print(write_report(args.out_dir, gate_path=args.gate), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
