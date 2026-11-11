"""Score one LLM-AggreFact result file by leaderboard rules (Exp 35 pre-freeze, task 6.5).

Reads ``<out>/aggrefact-<strategy>.jsonl`` and writes
``<out>/aggrefact-<strategy>-scores.json`` atomically (``.tmp``, then rename):
balanced accuracy per dataset, counts, error counts, the average, RAGTruth,
the pass rule and its gaps, and the judge call facts (model, GGUF SHA-256,
prompt version). A file without every row of the TEST split is refused
unless ``--allow-partial`` is given; the summary then says ``partial``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

PREFREEZE = Path(__file__).resolve().parent
DEFAULT_OUT = PREFREEZE.parent / "output" / "prefreeze"
if str(PREFREEZE) not in sys.path:
    sys.path.insert(0, str(PREFREEZE))

import aggrefact_lib as lib  # noqa: E402


def score_file(path: Path, *, allow_partial: bool = False) -> dict[str, Any]:
    """Return the score summary of the result file at *path*.

    Raises:
        ScoreError: The file is broken, partial (without *allow_partial*) or
            names a strategy with no published value.
    """
    header, facts, rows = lib.read_results(path)
    return lib.score_results(header, facts, rows, allow_partial=allow_partial)


def write_atomic(path: Path, summary: dict[str, Any]) -> None:
    """Write *summary* as JSON to *path* through a ``.tmp`` file and a rename."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def summary_line(summary: dict[str, Any]) -> str:
    """Return the one printed result line."""

    def points(value: Any) -> str:
        return "undefined" if value is None else f"{value:.1f}"

    rule = summary["pass_rule"] or {}
    return (
        f"[score] {summary['strategy']}: {summary['status']}; average {points(summary['average'])} "
        f"(gap {rule.get('average_gap')}), RAGTruth {points(summary[lib.RAGTRUTH])} "
        f"(gap {rule.get('ragtruth_gap')}); {summary['rows_scored']} rows, "
        f"{summary['rows_counted_wrong']} counted wrong"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Score one strategy's result file; return the exit code (2 on a refusal)."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strategy", required=True, choices=sorted(lib.PUBLISHED))
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args(argv)
    source = args.out_dir / f"aggrefact-{args.strategy}.jsonl"
    target = args.out_dir / f"aggrefact-{args.strategy}-scores.json"
    try:
        if not source.is_file():
            raise lib.ScoreError(f"{source.name} does not exist in {args.out_dir}")
        summary = score_file(source, allow_partial=args.allow_partial)
    except lib.ScoreError as error:
        print(f"[error] {error}", flush=True)
        return 2
    write_atomic(target, summary)
    print(summary_line(summary), flush=True)
    for note in summary["notes"]:
        print(f"[note] {note}", flush=True)
    print(f"[score] wrote {target}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
