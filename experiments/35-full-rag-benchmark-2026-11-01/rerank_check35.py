"""Reranker rank check before a reranker GGUF is pinned (task 15.10, M8; task 16.35).

A reranker file is pinned in ``plan.json`` only when its scores rank 200
seeded query-passage pairs (seed 20261117) like the transformers recipe of the
model card: Spearman correlation at least 0.95. Below that, or when a side
gives constant scores, the file is "not pinned".

Two commands, run on the test pod (task 9.2 step 2a)::

    uv run python rerank_check35.py draw --pool pool.jsonl --out <dir>
    uv run python rerank_check35.py check --pairs <dir>/pairs.jsonl \\
        --file Qwen3-Reranker-0.6B-Q8_0.gguf --sha256 <hex> \\
        --repository ggml-org/Qwen3-Reranker-0.6B-GGUF --build 11941 --model <router id> \\
        --hf-model Qwen/Qwen3-Reranker-0.6B --hf-revision <commit> \\
        --base-url http://127.0.0.1:8080 --out <dir>

``pool.jsonl`` holds one ``{"pair_id", "query", "passage"}`` object per line.
``check`` is a pre-freeze tool: before any scoring it calls ``guard_run`` with
``prefreeze=True`` (the router must serve the named file with ``pooling: rank``
and that SHA-256), which appends one ``prefreeze: true`` line to
``output/run-records.jsonl``. It writes ``<out>/<file>.rerank-check.json`` with
the start and end times, the correlation, the verdict and both scores per pair
ID. No passage text is written.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from experiments._lib import run_guard
from scipy.stats import spearmanr

from omrs.core.experiment_records.runtime_block import RuntimeBlock

EXP_DIR = Path(__file__).resolve().parent
SEED = 20261117
PAIRS = 200
MIN_SPEARMAN = 0.95
_TIMEOUT_SECONDS = 600.0

Pair = Mapping[str, str]


def draw_pairs(pool: Sequence[Pair], *, n: int = PAIRS, seed: int = SEED) -> list[dict[str, str]]:
    """Draw *n* pairs from *pool* with *seed*, whatever the pool order.

    Returns:
        The drawn pairs, sorted by ``pair_id``.

    Raises:
        ValueError: The pool holds fewer than *n* pairs, or a ``pair_id`` twice.
    """
    by_id: dict[str, dict[str, str]] = {}
    for pair in pool:
        if pair["pair_id"] in by_id:
            raise ValueError(f"pair_id {pair['pair_id']} appears twice in the pool")
        by_id[pair["pair_id"]] = dict(pair)
    if len(by_id) < n:
        raise ValueError(f"the pool holds {len(by_id)} pairs; the check needs {n}")
    drawn = random.Random(seed).sample(sorted(by_id), n)  # noqa: S311 - seeded draw
    return [by_id[pair_id] for pair_id in sorted(drawn)]


def verdict(file: str, llamacpp: Sequence[float], reference: Sequence[float]) -> dict[str, Any]:
    """Compare the two score lists of one file by Spearman correlation.

    Returns:
        ``{"file", "pairs", "spearman", "pinned", "status"}``. ``spearman`` is
        None when a side gives constant scores; the file is then not pinned.
    """
    rho = float(spearmanr(llamacpp, reference).statistic)
    spearman = None if math.isnan(rho) else rho
    pinned = spearman is not None and spearman >= MIN_SPEARMAN
    return {
        "file": file,
        "pairs": len(llamacpp),
        "spearman": spearman,
        "pinned": pinned,
        "status": "pinned" if pinned else "not pinned",
    }


def _post_json(url: str, body: Mapping[str, Any]) -> Any:
    # The URL is the loopback router address that guard_run has already checked.
    request = urllib.request.Request(  # noqa: S310
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310
        return json.loads(response.read())


def llamacpp_scores(
    pairs: Sequence[Pair],
    *,
    base_url: str,
    model: str,
    post: Callable[[str, Mapping[str, Any]], Any] = _post_json,
) -> list[float]:
    """Score each pair with one ``POST /v1/rerank`` holding that one passage.

    Returns:
        The ``relevance_score`` of each pair, in pair order.
    """
    url = base_url.rstrip("/") + "/v1/rerank"
    scores = []
    for pair in pairs:
        reply = post(url, {"model": model, "query": pair["query"], "documents": [pair["passage"]]})
        scores.append(float(reply["results"][0]["relevance_score"]))
    return scores


def transformers_scores(pairs: Sequence[Pair], *, model_id: str, revision: str) -> list[float]:
    """Score each pair with the transformers recipe of the Qwen3-Reranker model card.

    The probability of "yes" against "no" at the last position, with the card's
    default instruction, one pair at a time. Runs on the pod only: it imports
    ``torch`` and ``transformers`` here, never at module level.
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(model_id, revision=revision).eval()
    yes, no = tokenizer.convert_tokens_to_ids("yes"), tokenizer.convert_tokens_to_ids("no")
    prefix = (
        "<|im_start|>system\nJudge whether the Document meets the requirements based on the "
        'Query and the Instruct provided. Note that the answer can only be "yes" or "no".'
        "<|im_end|>\n<|im_start|>user\n"
    )
    suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
    task = "Given a web search query, retrieve relevant passages that answer the query"
    scores = []
    with torch.no_grad():
        for pair in pairs:
            text = f"<Instruct>: {task}\n<Query>: {pair['query']}\n<Document>: {pair['passage']}"
            ids = tokenizer(prefix + text + suffix, return_tensors="pt", add_special_tokens=False)
            logits = model(**ids).logits[0, -1, [no, yes]]
            scores.append(float(torch.log_softmax(logits, dim=0)[1].exp()))
    return scores


def candidate_block(*, build: int, repository: str, file: str, sha256: str) -> RuntimeBlock:
    """Return a runtime block for one candidate reranker file, loaded with ``pooling: rank``."""
    return RuntimeBlock.model_validate(
        {
            "models": [
                {
                    "role": "reranker-candidate",
                    "repository": repository,
                    "file": file,
                    "sha256": sha256,
                    "runtime": "llama.cpp",
                    "build": build,
                    "server_args": {"pooling": "rank"},
                }
            ],
            "tolerance": [{"metric": "spearman", "max_abs_change": 0.0}],
        }
    )


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def run_check(
    folder: Path,
    block: RuntimeBlock,
    pairs: Sequence[Pair],
    *,
    base_url: str,
    model: str,
    reference: Callable[[Sequence[Pair]], list[float]],
    out: Path,
    score: Callable[..., list[float]] = llamacpp_scores,
    guard: Callable[..., Any] = run_guard.guard_run,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    command: str | None = None,
) -> dict[str, Any]:
    """Guard the run as a pre-freeze run, score both sides, write the verdict.

    Raises:
        PreflightError: The router does not serve the planned file, hash or
            arguments. Nothing is scored and nothing is written.
    """
    started = now()
    guard(folder, block, base_url=base_url, command=command, check_args=True, prefreeze=True)
    file = block.models[0].file
    llama = score(pairs, base_url=base_url, model=model)
    ref = reference(pairs)
    result = {
        **verdict(file, llama, ref),
        "seed": SEED,
        "started_at": started.isoformat(),
        "finished_at": now().isoformat(),
        "scores": [
            {"pair_id": pair["pair_id"], "llamacpp": a, "reference": b}
            for pair, a, b in zip(pairs, llama, ref, strict=True)
        ],
    }
    _write_json(out / f"{file}.rerank-check.json", result)
    return result


def _read_jsonl(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``draw`` or ``check`` command. Returns 0."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    draw = commands.add_parser("draw")
    draw.add_argument("--pool", type=Path, required=True)
    draw.add_argument("--out", type=Path, required=True)
    run = commands.add_parser("check")
    run.add_argument("--pairs", type=Path, required=True)
    for name in ("file", "sha256", "repository", "model", "hf-model", "hf-revision", "base-url"):
        run.add_argument(f"--{name}", required=True)
    run.add_argument("--build", type=int, required=True)
    run.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "draw":
        pairs = draw_pairs(_read_jsonl(args.pool))
        args.out.mkdir(parents=True, exist_ok=True)
        tmp = args.out / "pairs.jsonl.tmp"
        tmp.write_text("".join(json.dumps(p) + "\n" for p in pairs), encoding="utf-8")
        tmp.replace(args.out / "pairs.jsonl")
        return 0
    block = candidate_block(
        build=args.build, repository=args.repository, file=args.file, sha256=args.sha256
    )
    reference = partial(transformers_scores, model_id=args.hf_model, revision=args.hf_revision)
    result = run_check(
        EXP_DIR,
        block,
        _read_jsonl(args.pairs),
        base_url=args.base_url,
        model=args.model,
        reference=reference,
        out=args.out,
    )
    print(f"{result['file']}: Spearman {result['spearman']}, {result['status']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
