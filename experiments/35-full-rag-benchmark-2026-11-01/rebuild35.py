"""G2 rebuild check of Experiment 35 (task 6.4; design D20; pre-registration section 15).

Usage (reads saved files only; runs without the environment record)::

    rebuild35.py --a CHECK/search.jsonl --b REBUILD/search.jsonl --out-dir OUT --dataset D

``--a`` is the build pod's search of the shared ``e4b-c1024`` index and
``--b`` the search of the index rebuilt in a fresh process, both with the
setup ``e4b-c1024-roff-hoff``. The tool compares the ranked stored chunk IDs
per question with ``compare_runs`` (``experiments/_lib/determinism.py``) and
writes only ``<out>/<dataset>/rebuild.json``. It exits with code 3 on any
mismatch or incomplete question.

A question whose search failed (no row with chunks: an empty list or a row
closed as missing) on either side is incomplete, never a match (H-21): it is
taken out before the comparison and listed. A question with a row on one side
only is a mismatch.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Hashable, Mapping, Sequence
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
for _folder in (EXP_DIR.parent.parent, EXP_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

from experiments._lib.determinism import compare_runs  # noqa: E402
from outputs35 import read_rows, write_json  # noqa: E402

EXIT_MISMATCH = 3


def ranked_ids(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[str] | None]:
    """Return per question the ranked chunk IDs of saved search rows; None for a failed search."""
    out: dict[str, list[str] | None] = {}
    for row in rows:
        ids = [str(c["chunk_id"]) for c in row.get("chunks") or []]
        out[str(row["qid"])] = ids or None
    return out


def compare(sides: Mapping[Hashable, Mapping[str, list[str] | None]]) -> dict[str, Any]:
    """Compare ranked lists across sides; failed searches are incomplete, never a match.

    Args:
        sides: Side label (in reference order) to :func:`ranked_ids` output.

    Returns:
        ``ok``, ``questions_compared``, ``questions_differing``, ``mismatches``
        (``compare_runs`` records) and ``incomplete`` (``question_id``, ``reason``).
    """
    questions = sorted({q for side in sides.values() for q in side})
    incomplete = []
    for q in questions:
        failed = [str(label) for label, side in sides.items() if q in side and side[q] is None]
        if failed:
            incomplete.append({"question_id": q, "reason": f"search failed in {', '.join(failed)}"})
    skip = {item["question_id"] for item in incomplete}
    report = compare_runs(
        {
            label: {q: ids for q, ids in side.items() if q not in skip and ids is not None}
            for label, side in sides.items()
        }
    ).to_dict()
    report["questions_compared"] = len(questions)
    report["incomplete"] = incomplete
    report["ok"] = report["ok"] and not incomplete
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Compare two saved search files; write ``rebuild.json``; return 0 or 3."""
    parser = argparse.ArgumentParser(prog="rebuild35.py", description=__doc__.split("\n")[0])
    parser.add_argument("--a", type=Path, required=True, help="search.jsonl of the shared index")
    parser.add_argument("--b", type=Path, required=True, help="search.jsonl of the rebuilt index")
    parser.add_argument(
        "--out-dir", type=Path, required=True, help="folder for <dataset>/rebuild.json"
    )
    parser.add_argument("--dataset", required=True)
    args = parser.parse_args(argv)
    report = compare({"a": ranked_ids(read_rows(args.a)), "b": ranked_ids(read_rows(args.b))})
    report.update({"dataset": args.dataset, "a": str(args.a), "b": str(args.b)})
    write_json(args.out_dir / args.dataset / "rebuild.json", report)
    if report["ok"]:
        print(
            f"[rebuild] {args.dataset}: {report['questions_compared']} questions match", flush=True
        )
        return 0
    bad = [m["question_id"] for m in report["mismatches"]] + [
        i["question_id"] for i in report["incomplete"]
    ]
    print(f"[rebuild] {args.dataset}: G2 fails on {', '.join(bad)}", flush=True)
    return EXIT_MISMATCH


if __name__ == "__main__":
    sys.exit(main())
