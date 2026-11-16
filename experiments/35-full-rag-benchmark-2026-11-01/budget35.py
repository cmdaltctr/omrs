"""Experiment 35 budget projection and drop record (pre-registration section 17).

``budget35.py project`` runs before the freeze, after the search stage and at
each stage end. It reads provider billing exports and measured rates only,
never scores and never the pre-freeze cost code. It appends one projection to
``<out>/budget-check.json``. When the projection reaches the $975 ceiling, it
records the next drop step of the registered order in ``<out>/drops.json``,
one step per call, never a step twice. After the last step, a projection at
the ceiling stops the run (exit code :data:`EXIT_STOP`).

Projection = billed so far + remaining answers x cost per answer + the
remaining other work, without the work a recorded drop step removes. The
answer count uses the 15 answer setups, 3 runs and the questions per dataset.

Inputs (JSON):

* ``--billing FILE`` (repeat): a list of ``{"provider": str, "usd": float}``
  rows, one per line of a provider billing export.
* ``--rates FILE``: ``pod_usd_per_hour``, ``pod_hours_per_answer``,
  ``hosted_per_answer`` (role to ``calls_per_answer`` and ``usd_per_call``),
  ``answers_done`` (dataset to answers saved) and ``other_work`` (a list of
  ``item``, ``pod_hours``, ``calls``, ``usd_per_call`` and ``drop_step``, 2 or
  3 for the work that step removes, else ``null``).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CEILING_USD = 975.0
ANSWER_SETUPS = 15
RUNS = 3
QUESTIONS = {"financebench": 150, "freshstack": 203, "bioasq": 707, "legal": 100}
DROP_STEPS = {
    1: "Legal RAG Bench answer generation",
    2: "length-controlled check",
    3: "closed-book run with the RAG prompt",
}
EXIT_STOP = 5


def read_drops(folder: Path) -> frozenset[int]:
    """Return the drop steps recorded in ``<folder>/drops.json``; none when the file is absent."""
    path = folder / "drops.json"
    if not path.is_file():
        return frozenset()
    return frozenset(int(d["step"]) for d in json.loads(path.read_text(encoding="utf-8"))["drops"])


def answer_datasets(steps: frozenset[int]) -> tuple[str, ...]:
    """Return the datasets whose answers the run still needs; drop step 1 removes Legal."""
    return tuple(name for name in QUESTIONS if not (name == "legal" and 1 in steps))


def project(
    rates: Mapping[str, Any], billing: Sequence[Mapping[str, Any]], steps: frozenset[int]
) -> dict[str, Any]:
    """Return the projection in dollars under the drop steps already recorded."""
    hour = float(rates["pod_usd_per_hour"])
    per_answer = float(rates["pod_hours_per_answer"]) * hour + sum(
        float(r["calls_per_answer"]) * float(r["usd_per_call"])
        for r in rates["hosted_per_answer"].values()
    )
    done = rates.get("answers_done") or {}
    remaining = {
        name: max(0, ANSWER_SETUPS * RUNS * QUESTIONS[name] - int(done.get(name, 0)))
        for name in answer_datasets(steps)
    }
    other = sum(
        float(w["pod_hours"]) * hour + float(w["calls"]) * float(w["usd_per_call"])
        for w in rates.get("other_work") or []
        if w.get("drop_step") not in steps
    )
    spent = sum(float(row["usd"]) for row in billing)
    remaining_usd = sum(remaining.values()) * per_answer + other
    return {
        "spent_usd": spent,
        "remaining_usd": remaining_usd,
        "projection_usd": spent + remaining_usd,
        "ceiling_usd": CEILING_USD,
        "answer_setups": ANSWER_SETUPS,
        "runs": RUNS,
        "remaining_answers": remaining,
        "drops_before": sorted(steps),
    }


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def run_project(
    rates_path: Path, billing_paths: Sequence[Path], out: Path, now: Callable[[], str]
) -> dict[str, Any]:
    """Project, record the check, and record the next drop step when the ceiling is reached."""
    steps = read_drops(out)
    billing = [row for path in billing_paths for row in _load(path)]
    check = project(_load(rates_path), billing, steps)
    over = check["projection_usd"] >= CEILING_USD
    step = min((s for s in DROP_STEPS if s not in steps), default=None) if over else None
    check |= {"time": now(), "over_ceiling": over, "drop_step": step, "stop": over and not step}
    if step:
        drops = _load(out / "drops.json")["drops"] if steps else []
        cost = check["projection_usd"]
        drops.append(
            {
                "step": step,
                "name": DROP_STEPS[step],
                "reason": f"projection {cost:.2f} USD reaches the ceiling {CEILING_USD:.0f}",
                "time": check["time"],
                "projection_usd": cost,
            }
        )
        _write(out / "drops.json", {"drops": drops})
    path = out / "budget-check.json"
    checks = _load(path)["checks"] if path.is_file() else []
    _write(path, {"checks": [*checks, check]})
    return check


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def main(argv: Sequence[str] | None = None, now: Callable[[], str] = _now) -> int:
    """Run the command line; return 0, or :data:`EXIT_STOP` when the run must stop."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("project", help="project the cost and record any drop step")
    cmd.add_argument("--rates", type=Path, required=True, help="measured rates JSON")
    cmd.add_argument("--billing", type=Path, action="append", default=[], help="billing rows")
    cmd.add_argument("--out", type=Path, required=True, help="folder of the two records")
    args = parser.parse_args(argv)
    check = run_project(args.rates, args.billing, args.out, now)
    print(f"[budget] projection {check['projection_usd']:.2f} USD, drop step {check['drop_step']}",
          file=sys.stderr, flush=True)  # fmt: skip
    return EXIT_STOP if check["stop"] else 0


if __name__ == "__main__":
    sys.exit(main())
