"""Command line of the Experiment 35 stage runner (``run_arms.py``), tasks 4.1 and 13.2.

``run_arms.py`` holds no parser: it calls :func:`parse_args`. One process runs
one stage of one dataset and one setup (``--setup NAME``) or one index
(``--index NAME``). ``--setup all`` runs every setup of the stage, and
``--index NAME`` with a search or answer stage runs that index's setups, each
in its own process, in table order.

Exit codes: 0 done; 2 setup or input error (nothing scored, also an unknown
name or a value below 1); 3 a determinism or rebuild check found a difference;
4 a judge could not start, or a ``chat`` claim call failed (``--resume`` sends
it again); 5 a hosted call was rate-limited past the attempt
limit or the account is out of credit (finished rows kept, no done-marker);
6 items are still open after their errors (no done-marker; run again with
``--resume``).
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import arms
import claimstage35
import datasets35
import ragas35
from outputs35 import say

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
    parser.add_argument(
        "--answers",
        choices=arms.ANSWER_KINDS,
        default="answer",
        help="the answer folder the judge and ragas stages read (default answer)",
    )
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
    ragas35.add_arguments(parser)
    claimstage35.add_arguments(parser)
    return parser


def print_plan(
    args: argparse.Namespace,
    setup: arms.Setup,
    name: str,
    path: Path,
    layout: Any,
    roles: Sequence[str],
    questions: Sequence[Any],
    problems: list,
    *,
    concurrency: dict[str, int],
    resolved: dict[str, Any],
) -> int:
    """Print the ``--dry-run`` plan of one stage; return 1 when OMRS lists role problems."""
    plan = {
        "nothing_started": True,
        "settings_file": str(path),
        "out_dir": str(args.out_dir),
        "dataset": args.dataset,
        "stage": args.stage,
        "name": name,
        "run": args.run,
        "collection": setup.collection(args.dataset),
        "store": str(layout.store(setup.index)),
        "search": {"rerank": setup.rerank, "hybrid": setup.hybrid_on},
        "models": list(roles),
        "corpus_sample": args.corpus_sample,
        "questions": [q.qid for q in questions],
        "prefreeze": args.prefreeze,
        "smoke": args.smoke,
        "concurrency": concurrency,
        "keys_set": {n: bool(os.environ.get(n)) for n in ("OPENROUTER_API_KEY", arms.GLM_KEY_ENV)},
        "resolved": resolved,
        "role_problems": problems,
    }
    say("[dry-run] nothing started, nothing sent")
    say(json.dumps(plan, indent=2, default=str))
    return 1 if problems else 0


def resolved(settings: Any) -> dict[str, Any]:
    """Return the resolved values a trace records (no key fields)."""
    answer, retrieval = settings.answer, settings.retrieval
    return {
        "embed_model": settings.llamacpp_embed_model,
        "router_url": settings.llamacpp_router_url,
        "router_models_max": settings.llamacpp_router_models_max,
        "rag_profile": settings.rag_profile,
        "tokenizer_model": settings.embedding.tokenizer_model,
        "tokenizer_revision": settings.embedding.tokenizer_revision,
        "query_instruction": settings.embedding.query_instruction,
        "metadata_extraction": settings.metadata.extraction_mode,
        "pdf_reader": settings.pdf_reader,
        "chunk_size": settings.chunking.chunk_size,
        "markdown_chunk_size": settings.chunking.markdown_chunk_size,
        "chunk_overlap": settings.chunking.chunk_overlap,
        "rerank_backend": retrieval.rerank_backend,
        "rerank_model": retrieval.rerank_model,
        "hybrid_sparse_backend": retrieval.hybrid_sparse_backend,
        "hybrid_rrf_k": retrieval.hybrid_rrf_k,
        "answer_provider": answer.provider,
        "answer_model": answer.model,
        "answer_temperature": answer.temperature,
        "answer_seed": answer.seed,
        "answer_allowed_hosts": answer.allowed_hosts,
        "answer_reasoning": answer.reasoning,
        "answer_max_output_tokens": answer.max_output_tokens,
        "answer_context_window": answer.context_window,
        "answer_max_rounds": answer.max_rounds,
        "verify_claims": answer.verify_claims,
    }


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
