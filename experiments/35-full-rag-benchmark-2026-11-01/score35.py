"""Score the saved search lists of one half (tasks 15.1a and 16.17; pre-registration 6, 14.2).

Usage (reads saved files only; runs on the Mac without the environment record)::

    score35.py --out-dir OUT --half A|B --halves HALVES [--dataset D ...] [--passages-dir P]

The search stage saves, per question, the ranked list of 100 stored chunks and
no metric. This tool reads ``<out>/<dataset>/search/<setup>/run1/search.jsonl``
with the gold labels and scores the questions of one half through
``scoring35.score_question``. ``evidence_recall_20k`` uses the saved Qwen3
token counts: the head is every chunk taken while the token total before it
is below 20,480 (the crossing chunk counts; it covers its unit).

Half B runs behind the half-B guard (``scoring35.require_half_b``): it stops
before it reads a list or computes a score until ``selection.json`` exists and
``osf-timestamp.json`` holds its configuration hash.

Files written (``scoring35.write_scores``, atomic):

- ``<out>/scores/<half>/<dataset>/<setup>.jsonl``: one score record per question.
- ``<out>/scores/<half>/<dataset>/summary.json``: per setup, the means of
  ``scoring35.summarise`` plus ``missing`` (questions whose search is still
  missing; they score 0 and stay in the denominator, section 12).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
for _folder in (EXP_DIR.parent.parent, EXP_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import datasets35  # noqa: E402
import scoring35  # noqa: E402
import split35  # noqa: E402
from outputs35 import Layout, read_rows  # noqa: E402


class MissingTokenCounts(ValueError):
    """A saved ranked list holds a chunk with no ``tokens`` count (protocol 0.14 item 31)."""


def token_cut_k(chunks: Sequence[Mapping[str, Any]], budget: int = scoring35.TOKEN_BUDGET) -> int:
    """Return how many head chunks the 20,480-token cut keeps, from the saved token counts.

    A chunk is taken while the total before it is below *budget*; the chunk
    that crosses the limit is taken (truncated) and nothing after it.

    Raises:
        MissingTokenCounts: A chunk read by the cut has no ``tokens`` count.
    """
    total = 0
    k = 0
    for chunk in chunks:
        if total >= budget:
            break
        if chunk.get("tokens") is None:
            raise MissingTokenCounts(
                f"chunk {chunk.get('chunk_id')!r} has no saved 'tokens' count; the scorer reads "
                "token counts from the saved list and never counts chunk text. Run the search "
                "stage again (task 15.1a) so every chunk carries its Qwen3 token count."
            )
        total += min(int(chunk["tokens"]), budget - total)
        k += 1
    return k


def _evidence_k(dataset: str, setup: str, row: Mapping[str, Any]) -> int:
    """Return the token cut of one saved row, naming the question when a count is missing."""
    try:
        return token_cut_k(row.get("chunks") or [])
    except MissingTokenCounts as error:
        raise MissingTokenCounts(f"{dataset} {setup} question {row['qid']}: {error}") from error


def score(
    out_dir: Path,
    half: str,
    *,
    halves: Mapping[str, Mapping[str, str]],
    golds: Mapping[str, Mapping[str, scoring35.Gold]],
    unit_maps: Mapping[str, Mapping[str, str]] | None = None,
    datasets: Sequence[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Score every saved search setup of *half*; return the summary per dataset and setup.

    Args:
        out_dir: The run output folder.
        half: ``A`` or ``B``.
        halves: Per dataset, the half of each question ID (``halves.json``).
        golds: Per dataset, the gold labels per question ID.
        unit_maps: Per dataset, the file stem to unit map (FreshStack).
        datasets: The datasets to score; every dataset with a ``search`` folder when None.

    Raises:
        scoring35.HalfBLocked: Half B before it is open; nothing read or written.
        MissingTokenCounts: A saved chunk has no ``tokens`` count; that setup writes no score.
        ValueError: A setup lacks a question of the half, or scores one twice.
        outputs35.NoRunFiles: A dataset holds no saved search list.
    """
    if half == "B":
        scoring35.require_half_b(out_dir)
    layout = Layout(out_dir)
    saved = {d for d, *_ in layout.need_runs("search", "search.jsonl")}
    names = datasets or [d for d in datasets35.DATASETS if d in saved]
    result: dict[str, dict[str, Any]] = {}
    for dataset in names:
        wanted = split35.ids_in_half(halves, dataset, half)
        target = out_dir / "scores" / half / dataset
        summary: dict[str, Any] = {}
        for _, setup, run, folder in layout.need_runs("search", "search.jsonl", dataset):
            if run != 1:
                continue
            rows = [r for r in read_rows(folder / "search.jsonl") if r["qid"] in wanted]
            records = [
                scoring35.score_question(
                    dataset,
                    setup,
                    golds[dataset][r["qid"]],
                    r.get("chunks") or [],
                    evidence_k=_evidence_k(dataset, setup, r),
                    unit_map=(unit_maps or {}).get(dataset),
                )
                for r in rows
            ]
            scoring35.write_scores(target / f"{setup}.jsonl", records, half=half, root=out_dir)
            summary[setup] = {
                **scoring35.summarise(records, expected_n=len(wanted)),
                "missing": [r["qid"] for r in rows if r.get("missing")],
            }
        scoring35.write_scores(target / "summary.json", summary, half=half, root=out_dir)
        result[dataset] = summary
    return result


def _questions(dataset: str) -> list[datasets35.Question]:
    return datasets35.load_questions(dataset, datasets35.data_root())


def main(argv: Sequence[str] | None = None) -> int:
    """Score one half of the saved search lists; return 0, or 2 when the data is refused."""
    parser = argparse.ArgumentParser(prog="score35.py", description=__doc__.split("\n")[0])
    parser.add_argument("--out-dir", type=Path, required=True, help="the run output folder")
    parser.add_argument("--half", choices=scoring35.HALVES, required=True)
    parser.add_argument("--halves", type=Path, required=True, help="the halves.json file")
    parser.add_argument("--dataset", action="append", choices=datasets35.DATASETS)
    parser.add_argument(
        "--passages-dir", type=Path, help="prepared passage folder (FreshStack manifest)"
    )
    args = parser.parse_args(argv)
    if args.half == "B":
        scoring35.require_half_b(args.out_dir)
    halves = split35.read_halves(args.halves)
    saved = {d for d, *_ in Layout(args.out_dir).need_runs("search", "search.jsonl")}
    names = args.dataset or [d for d in datasets35.DATASETS if d in saved]
    try:
        golds = {d: scoring35.gold_table(d, _questions(d)) for d in names}
    except datasets35.DatasetError as error:
        print(f"[error] {error}", flush=True)
        return 2
    unit_maps = {}
    if "freshstack" in names:
        if args.passages_dir is None:
            parser.error("FreshStack needs --passages-dir: its file stems map to units there")
        unit_maps["freshstack"] = datasets35.freshstack_unit_map(args.passages_dir / "freshstack")
    summary = score(
        args.out_dir, args.half, halves=halves, golds=golds, unit_maps=unit_maps, datasets=names
    )
    print(json.dumps({d: sorted(s) for d, s in summary.items()}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
