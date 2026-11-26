"""G2 rebuild check of Experiment 35 (task 6.4; design D20; pre-registration section 15).

Usage (reads saved files only; runs without the environment record)::

    rebuild35.py --a CHECK/search.jsonl --b REBUILD/search.jsonl --out-dir OUT --dataset D
        [--prefreeze]

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

It removes an earlier ``<out>/<dataset>/rebuild.json`` first, then refuses
(exit 2, no ``rebuild.json``) a missing or empty file, a path that
is not under ``search/e4b-c1024-roff-hoff/``, and a question count other than
the dataset's frozen count (``budget35.QUESTIONS``). ``--prefreeze`` (a test
pod subset) skips only the count check and marks the record.
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

import budget35  # noqa: E402
from experiments._lib.determinism import compare_runs  # noqa: E402
from outputs35 import read_rows, write_json  # noqa: E402

EXIT_MISMATCH = 3
SETUP = "e4b-c1024-roff-hoff"  # pre-registration section 15, G2
FROZEN = budget35.QUESTIONS


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
    parser.add_argument(
        "--prefreeze", action="store_true", help="a pre-freeze subset: no frozen-count check"
    )
    args = parser.parse_args(argv)
    # A refused rerun must not leave an earlier passing report for the join to read.
    (args.out_dir / args.dataset / "rebuild.json").unlink(missing_ok=True)
    sides = {}
    for label, path in (("a", args.a), ("b", args.b)):
        if f"/search/{SETUP}/" not in path.absolute().as_posix():
            parser.error(f"--{label} {path} is not under search/{SETUP}/ (G2 compares that setup)")
        rows = read_rows(path)
        if not rows:
            parser.error(f"--{label} {path} is missing or empty; G2 compares nothing")
        sides[label] = ranked_ids(rows)
    report = compare(sides)
    frozen = FROZEN.get(args.dataset)
    if not args.prefreeze and report["questions_compared"] != frozen:
        parser.error(
            f"{args.dataset}: {report['questions_compared']} questions compared, "
            f"the frozen count is {frozen}"
        )
    report.update(
        {
            "dataset": args.dataset,
            "setup": SETUP,
            "prefreeze": args.prefreeze,
            "a": str(args.a),
            "b": str(args.b),
        }
    )
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
