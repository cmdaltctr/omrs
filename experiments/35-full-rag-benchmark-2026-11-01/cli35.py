"""Command line of the Experiment 35 stage runner (``run_arms.py``), tasks 4.1 and 13.2.

``run_arms.py`` holds no parser: it calls :func:`parse_args`. One process runs
one stage of one dataset and one setup (``--setup NAME``) or one index
(``--index NAME``). ``--setup all`` runs every setup of the stage, and
``--index NAME`` with a search or answer stage runs that index's setups, each
in its own process, in table order.

Exit codes: 0 done; 2 setup or input error (nothing scored, also an unknown
name or a value below 1); 3 a determinism or rebuild check found a difference;
4 a judge could not start; 5 a hosted call was rate-limited past the attempt
limit or the account is out of credit (finished rows kept, no done-marker);
6 items are still open after their errors (no done-marker; run again with
``--resume``).
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import arms
import datasets35

EXP_DIR = Path(__file__).resolve().parent
DEFAULT_OUT = EXP_DIR / "output" / "restricted" / "runs"
SMOKE_OUT = EXP_DIR / "output" / "restricted" / "smoke"
#: The concurrency and attempt options, all with a default from ``arms.CONCURRENCY_DEFAULTS``.
CONCURRENCY_OPTIONS = tuple(arms.CONCURRENCY_DEFAULTS)


def _positive(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be 1 or more, not {value}")
    return value


def _qids(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def build_parser() -> argparse.ArgumentParser:
    """Return the runner's argument parser."""
    parser = argparse.ArgumentParser(
        prog="run_arms.py",
        description="Experiment 35 stage runner (one stage, one setup or index).",
    )
    parser.add_argument("--dataset", required=True, choices=datasets35.DATASETS)
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--setup", help="a setup name e<emb>-c<chunk>-r<rerank>-h<hybrid>, or all")
    which.add_argument("--index", help="an index name e<emb>-c<chunk>")
    parser.add_argument("--stage", required=True, choices=list(arms.STAGES))
    parser.add_argument("--run", type=int, default=1, choices=(1, 2, 3))
    parser.add_argument("--limit", type=_positive, help="first N questions of the frozen order")
    parser.add_argument(
        "--corpus-sample", type=int, help="ingest gold documents plus N seeded others (smoke)"
    )
    parser.add_argument(
        "--qids", type=_qids, help="comma list of question IDs: a named-question smoke run"
    )
    parser.add_argument("--judges", default="", help=f"comma list of {', '.join(arms.JUDGE_NAMES)}")
    parser.add_argument("--answer-host", default="", help="the one OpenRouter host for answers")
    parser.add_argument("--resume", action="store_true", help="continue a started stage")
    parser.add_argument("--dry-run", action="store_true", help="print the plan; start nothing")
    parser.add_argument(
        "--prefreeze", action="store_true", help="a pre-freeze run: its run record is flagged"
    )
    parser.add_argument("--out-dir", type=Path, help="the run output folder")
    parser.add_argument(
        "--local-dir", type=Path, help="scratch settings and router state (container disk)"
    )
    parser.add_argument(
        "--index-from", type=Path, help="read the stores, index markers and fingerprints here"
    )
    parser.add_argument(
        "--passages-dir", type=Path, help="the prepared passage folder (prepare35.py)"
    )
    for name in CONCURRENCY_OPTIONS:
        parser.add_argument(
            f"--{name.replace('_', '-')}",
            type=_positive,
            default=arms.CONCURRENCY_DEFAULTS[name],
            help=f"default {arms.CONCURRENCY_DEFAULTS[name]}",
        )
    return parser


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Return the checked command line.

    Adds ``smoke`` (``--limit``, ``--corpus-sample`` or ``--qids`` given) and
    the default ``out_dir`` (the smoke folder for a smoke run).

    Raises:
        SystemExit: Code 2 for an unknown setup or index name, a value below 1
            or a negative corpus sample.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.setup not in (None, "all"):
            arms.parse_setup(args.setup)
        if args.index is not None:
            arms.index_setup(args.index)
    except arms.ArmConfigError as error:
        parser.error(str(error))
    if args.corpus_sample is not None and args.corpus_sample < 0:
        parser.error("--corpus-sample must be 0 or more")
    args.smoke = any(v is not None for v in (args.limit, args.corpus_sample, args.qids))
    if args.out_dir is None:
        args.out_dir = SMOKE_OUT if args.smoke else DEFAULT_OUT
    return args
