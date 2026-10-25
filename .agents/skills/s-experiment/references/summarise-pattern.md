# Summariser pattern: `summarise_eval.py`

The summariser turns `output/raw.json` into `output/summary.json` and the tables for `report.md`. It reads the stats level from `plan.json` and calls `_lib/stats.py`. It adds no new statistics code.

## What it does

1. Loads `plan.json` (level, metrics, gates) and `output/raw.json`.
2. Pairs baseline and candidate rows by `item_id`.
3. Calls `stats.compare` for each metric named in the plan.
4. Checks each gate from the plan, never from a threshold chosen after the run.
5. Writes `output/summary.json`, including the plain sentences.
6. Writes `output/report_tables.md` for you to paste into `report.md`.

It does not write the Answer box or the Discussion. You write those from the summary.

## `plan.json` keys it reads

```json
{
  "stats": "medium",
  "seed": 0,
  "baseline": "baseline",
  "candidate": "candidate",
  "metrics": [
    {"name": "hit_at_10", "binary": true, "primary": true},
    {"name": "rr_at_10", "binary": false, "primary": false}
  ],
  "gates": [
    {"id": "G1", "metric": "hit_at_10", "value": "difference", "op": ">=", "threshold": 0.05},
    {"id": "G2", "metric": "latency_ms", "value": "ratio", "op": "<=", "threshold": 1.5}
  ]
}
```

## Skeleton

```python
"""Experiment <N>: summarise raw.json at the stats level in plan.json."""

from __future__ import annotations

import json
import operator
import sys
from pathlib import Path
from statistics import fmean

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # for experiments/_lib

from _lib import stats  # noqa: E402

PLAN = json.loads((HERE / "plan.json").read_text(encoding="utf-8"))
RAW = json.loads((HERE / "output" / "raw.json").read_text(encoding="utf-8"))


def paired(metric: str) -> tuple[list[float], list[float], list[str] | None]:
    base = {r["item_id"]: r for r in RAW["cells"][PLAN["baseline"]]}
    cand = {r["item_id"]: r for r in RAW["cells"][PLAN["candidate"]]}
    ids = sorted(base.keys() & cand.keys())
    groups = [base[i]["group"] for i in ids] if all(base[i].get("group") for i in ids) else None
    return [base[i][metric] for i in ids], [cand[i][metric] for i in ids], groups


OPS = {">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt}


def check_gate(gate: dict, values: dict[str, float]) -> bool:
    """value is baseline, candidate, difference or ratio (candidate / baseline)."""
    return OPS[gate["op"]](values[gate["value"]], gate["threshold"])


def main() -> None:
    level = PLAN.get("stats", "medium")
    results = {}
    for m in PLAN["metrics"]:
        a, b, groups = paired(m["name"])
        results[m["name"]] = stats.compare(
            a,
            b,
            level=level,
            binary=m["binary"],
            metric=m["name"],
            groups=groups,
            seed=PLAN.get("seed", 0),
        )

    gates = []
    for g in PLAN["gates"]:
        if g["metric"] in results:
            r = results[g["metric"]]
            base, cand = r["baseline"], r["candidate"]
        else:  # a guardrail such as latency, compared on means only
            a, b, _ = paired(g["metric"])
            base, cand = fmean(a), fmean(b)
        values = {
            "baseline": base,
            "candidate": cand,
            "difference": cand - base,
            "ratio": cand / base if base else float("inf"),
        }
        gates.append({**g, **values, "pass": check_gate(g, values)})

    summary = {
        "level": level,
        "metrics": results,
        "gates": gates,
        "all_gates_pass": all(g["pass"] for g in gates),
    }
    out = HERE / "output"
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=list), encoding="utf-8")
    (out / "report_tables.md").write_text(tables(summary), encoding="utf-8")
    print("all gates pass" if summary["all_gates_pass"] else "a gate failed", file=sys.stderr)


def tables(summary: dict) -> str:
    lines = [
        "| Gate | Metric | Rule | Baseline | Candidate | Pass |",
        "| --- | --- | --- | ---: | ---: | :---: |",
    ]
    for g in summary["gates"]:
        rule = f"{g['value']} {g['op']} {g['threshold']}"
        mark = "yes" if g["pass"] else "no"
        lines.append(
            f"| {g['id']} | `{g['metric']}` | `{rule}` | {g['baseline']:.3f} | {g['candidate']:.3f} | {mark} |"
        )
    for name, r in summary["metrics"].items():
        lines += ["", f"**`{name}`** (n = {r['n']}, level {r['level']})", ""]
        lines += [f"- {s}" for s in r["sentences"]]
    lines += ["", "Source: `output/summary.json`", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
```

## Notes

- Each gate compares one value (`baseline`, `candidate`, `difference` or `ratio`) with a threshold from `plan.json`.
- Basic level gives numbers and win/loss counts only. Medium adds ranges and the paired test. Expert adds the smallest detectable gain. See `stats-levels.md`.
- With more than one primary metric at expert level, pass their p-values through `stats.holm` and report the adjusted values.
- Anything you compute that the plan did not name goes under "Exploratory findings" in the report.

## Checklist before you write the report

- Every gate in the plan appears in `summary.json`.
- Each number in `report_tables.md` has a plain sentence under it.
- The stats level in `summary.json` matches `plan.json`.
- No threshold was changed after the run.
