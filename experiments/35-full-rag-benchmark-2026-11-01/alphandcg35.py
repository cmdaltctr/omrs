"""FreshStack alpha-nDCG@10 with the benchmark's own scorer (RDY 16.3; pre-registration section 6).

Usage (reads saved score records; runs on the Mac)::

    alphandcg35.py --out-dir OUT --python SCORER_VENV/bin/python --repo FRESHSTACK_REPO

Secondary and descriptive, FreshStack only: no test, no Holm family, no
decision. The official ``alpha_ndcg`` (``freshstack/retrieval/metrics.py``,
repository and commit in ``plan.json`` ``pins.scorers.freshstack_alpha_ndcg``)
runs in a separate venv that holds only the pinned ``pyndeval``, never the
project venv, through ``alpha_runner35.py`` with ``python -I``. The nugget
qrels are built as the official loader builds them (relevant 1, then judged
non-relevant 0, per nugget) from the saved FreshStack export, and each ranked
list (``ranked_units`` of the score records, every half present) is sent with
strictly falling scores (1000 minus rank), so the scorer cannot re-sort ties.
The value per setup is the official mean over the setup's questions: a
question with no saved unit counts 0. Writes ``<out>/alpha-ndcg.json``. It
reads half-B scores, so it runs behind the half-B guard.
"""

from __future__ import annotations

import argparse
import json
import subprocess  # noqa: S404 - runs the pinned scorer venv, arguments are paths only
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
for _folder in (EXP_DIR.parent.parent, EXP_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import datasets35  # noqa: E402
import scoring35  # noqa: E402
from outputs35 import read_rows, write_json  # noqa: E402

DATASET = "freshstack"
RUNNER = EXP_DIR / "alpha_runner35.py"
METRICS = Path("freshstack") / "retrieval" / "metrics.py"
TOP = 1000


class ScorerRefused(RuntimeError):
    """The scorer differs from its pin, or it failed; the message names why."""


def read_plan() -> dict[str, Any]:
    """Return the parsed ``plan.json``."""
    return json.loads((EXP_DIR / "plan.json").read_text(encoding="utf-8"))


def nugget_qrels(root: Path) -> tuple[dict[str, dict[str, int]], dict[str, list[str]]]:
    """Return the nugget qrels and each question's nuggets, as the official loader builds them."""
    path = root / datasets35._FS_GT  # noqa: SLF001 - the pinned export path
    qrels: dict[str, dict[str, int]] = {}
    by_query: dict[str, list[str]] = {}
    for query in json.loads(path.read_text(encoding="utf-8"))["queries"]:
        if str(query["query_id"]).startswith("continuity"):
            continue
        for nugget in query.get("nuggets") or ():
            nid = str(nugget["nugget_id"])
            per = qrels.setdefault(nid, {})
            per.update(dict.fromkeys(map(str, nugget["relevant_corpus_ids"]), 1))
            per.update(dict.fromkeys(map(str, nugget["non_relevant_corpus_ids"]), 0))
            by_query.setdefault(str(query["query_id"]), []).append(nid)
    return qrels, by_query


def runs(records: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, dict[str, int]]]:
    """Return per setup and question the ranked units with strictly falling scores."""
    out: dict[str, dict[str, dict[str, int]]] = {}
    for row in records:
        if row["dataset"] == DATASET:
            ranked = row.get("ranked_units") or []
            scores = {unit: TOP - rank for rank, unit in enumerate(ranked)}
            out.setdefault(row["setup"], {})[str(row["qid"])] = scores
    return out


def score(
    records: Iterable[Mapping[str, Any]],
    *,
    root: Path,
    repo: Path,
    python: str,
    pin: Mapping[str, Any],
) -> dict[str, Any]:
    """Return per setup the official alpha-nDCG@10 and its question count.

    Raises:
        ScorerRefused: ``metrics.py`` or ``pyndeval`` differs from the pin, the
            alpha is not the official one, or the scorer failed.
    """
    qrels, by_query = nugget_qrels(root)
    per_setup = runs(records)
    task = {
        "metrics": str(repo / METRICS),
        "sha256": pin["metrics_py_sha256"],
        "alpha": pin["alpha"],
        "k": pin["k"],
        "qrels": qrels,
        "runs": {
            setup: {
                "nuggets": {q: by_query[q] for q in sorted(lists)},
                "results": {q: units for q, units in sorted(lists.items()) if units},
            }
            for setup, lists in sorted(per_setup.items())
        },
    }
    folder = Path(tempfile.mkdtemp(prefix="alpha-ndcg-"))
    source, target = folder / "input.json", folder / "output.json"
    source.write_text(json.dumps(task), encoding="utf-8")
    done = subprocess.run(  # noqa: S603 - fixed argument list, no shell
        [python, "-I", str(RUNNER), str(source), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if not target.is_file():
        raise ScorerRefused(f"the scorer failed (exit {done.returncode}): {done.stderr[-500:]}")
    found = json.loads(target.read_text(encoding="utf-8"))
    if "refused" in found:
        raise ScorerRefused(found["refused"])
    if found["pyndeval"] != pin["pyndeval_version"]:
        raise ScorerRefused(
            f"pyndeval {found['pyndeval']} is not the pinned {pin['pyndeval_version']}"
        )
    out: dict[str, Any] = {
        setup: {"alpha_ndcg_at_10": value, "n": len(per_setup[setup])}
        for setup, value in sorted(found["values"].items())
    }
    out["_input"] = str(target)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    """Write ``<out>/alpha-ndcg.json``; return 0."""
    parser = argparse.ArgumentParser(prog="alphandcg35.py", description=__doc__.split("\n")[0])
    parser.add_argument("--out-dir", type=Path, required=True, help="the joined output folder")
    parser.add_argument("--python", required=True, help="the scorer venv's python")
    parser.add_argument("--repo", type=Path, required=True, help="the official FreshStack clone")
    args = parser.parse_args(argv)
    scoring35.require_half_b(args.out_dir)
    pin = read_plan()["pins"]["scorers"]["freshstack_alpha_ndcg"]
    records = [
        row
        for path in sorted((args.out_dir / "scores").glob(f"[AB]/{DATASET}/*.jsonl"))
        for row in read_rows(path)
    ]
    values = score(
        records, root=datasets35.data_root(), repo=args.repo, python=args.python, pin=pin
    )
    values.pop("_input")
    table = {"metric": "alpha-nDCG@10", "descriptive": True, "pin": pin, "setups": values}
    write_json(args.out_dir / "alpha-ndcg.json", table)
    print(f"[alpha-ndcg] {args.out_dir / 'alpha-ndcg.json'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
