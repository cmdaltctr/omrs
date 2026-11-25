"""Reranker rank check before a reranker GGUF is pinned (task 15.10, M8; task 9.2 step 2a; G12).

A Qwen3-Reranker GGUF is pinned in ``plan.json`` only when its llama.cpp scores
rank 200 seeded query-passage pairs (seed 20261117) like the transformers
recipe of the model card: Spearman correlation at least 0.95 (pre-registration
section 16, design M8). Task 9.2 step 2a (design D24 item 1) adds two anchor
pairs: the relevant one scores near 1 and the irrelevant one near 0. The spec
gives no number, so the check uses ``ANCHOR_RELEVANT_MIN`` (0.9) and
``ANCHOR_IRRELEVANT_MAX`` (0.1) on both sides. A llama.cpp score outside
[0, 1] also fails the file: the OMRS backend reads it as a probability (task
12.2, design D27). The anchors are not in the Spearman correlation.

Five commands, in this order on the test pod::

    rerank_check35.py pool --dataset bioasq --dataset freshstack \\
        --passages-dir /workspace/passages --out <dir>
    rerank_check35.py draw --pool <dir>/pool.jsonl --out <dir>
    rerank_check35.py llamacpp --pairs <dir>/pairs.jsonl --role reranker-4b --out <dir>
    rerank_check35.py reference --pairs <dir>/pairs.jsonl --hf-model Qwen/Qwen3-Reranker-4B \\
        --hf-revision <commit> --out <dir>
    rerank_check35.py verdict --llamacpp <dir>/<file>.llamacpp.json \\
        --reference <dir>/reference-Qwen3-Reranker-4B.json --out <dir>

* ``pool``: per dataset, ``POOL_QUERIES`` questions drawn with the seed, each
  with up to ``POOL_GOLD`` gold and ``POOL_OTHERS`` other passage files of the
  prepared folder (task 5.4c), text cut at ``MAX_CHARS``, then both anchors.
  Data folder: ``$EXP35_DATA_DIR``. Writes ``pool.jsonl`` and ``pool-summary.json``.
* ``draw``: 200 pairs with the seed, then both anchors. Writes ``pairs.jsonl``.
* ``llamacpp``: the candidate is a ``plan.json`` runtime role (``--role``) or one
  runtime model object in a JSON file (``--entry``, a second candidate). With
  no ``--base-url`` it starts OMRS's managed router with that file only (from
  ``$SWEEP_GGUF_DIR``) and stops it at the end; ``--base-url`` reuses a server.
  Before any score it calls ``guard_run`` with ``prefreeze=True`` (task 16.35):
  the server must serve that file, SHA-256 and server arguments, and one
  ``prefreeze: true`` line goes to ``output/run-records.jsonl``.
  Writes ``<file>.llamacpp.json``.
* ``reference``: runs in its own environment with the ``torch`` extra, for
  example ``UV_PROJECT_ENVIRONMENT=/workspace/reference-venv uv sync --frozen
  --extra torch``, then ``uv run --no-sync`` with the same variable. It refuses
  while a server answers at ``--server-url`` (default: the scratch router), and
  for 4B and 8B with no CUDA device unless ``--allow-cpu``. Writes one
  pre-freeze run record and ``reference-<model>.json``, which serves every
  candidate file of that size.
* ``verdict``: one llama.cpp file against the reference file of the same size
  and pairs. Writes ``<file>.rerank-check.json``.

VRAM: an 8B reference in bfloat16 and an 8B llama.cpp server need more than
24 GB together. Run ``llamacpp`` and ``reference`` one after the other.

Exit codes: 0 done (``verdict``: pinned), 2 refused (nothing scored or
written), 3 not pinned. No score file holds query or passage text.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
for _folder in (EXP_DIR.parent.parent, EXP_DIR):
    if str(_folder) not in sys.path:
        sys.path.insert(0, str(_folder))

import arms  # noqa: E402
import datasets35  # noqa: E402
import rerank_scorers35 as scorers  # noqa: E402
from experiments._lib import router_env  # noqa: E402
from experiments._lib.preflight import PreflightError  # noqa: E402
from rerank_scorers35 import CheckRefused, write_json  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

#: Pre-registration section 16: the reranker rank check (200 pairs per size).
SEED = 20261117
PAIRS = 200
MIN_SPEARMAN = 0.95
#: Not in the spec: design D24 item 1 and task 9.2 step 2a say "near 1" and "near 0".
ANCHOR_RELEVANT_MIN = 0.9
ANCHOR_IRRELEVANT_MAX = 0.1
#: The pool shape is this check's own choice (the spec fixes the 200 pairs and the seed).
POOL_QUERIES = 20
POOL_GOLD = 2
POOL_OTHERS = 8
#: About 1,600 Qwen3 tokens at 3.68 characters per token: a pair fits an 8,192-token batch.
MAX_CHARS = 6000
EXIT_REFUSED = 2
EXIT_NOT_PINNED = 3

#: The two anchor pairs (texts from the Qwen3-Reranker model card example).
ANCHORS: tuple[dict[str, str], ...] = (
    {
        "pair_id": "anchor:relevant",
        "kind": "anchor-relevant",
        "query": "What is the capital of China?",
        "passage": "The capital of China is Beijing.",
    },
    {
        "pair_id": "anchor:irrelevant",
        "kind": "anchor-irrelevant",
        "query": "What is the capital of China?",
        "passage": (
            "Gravity is a force that attracts two bodies towards each other. It gives weight to "
            "physical objects and is responsible for the movement of planets around the sun."
        ),
    },
)
ANCHOR_IDS = tuple(anchor["pair_id"] for anchor in ANCHORS)

Pair = Mapping[str, str]

# --- pool and draw -----------------------------------------------------------------


def build_pool(
    dataset: str, questions: Sequence[datasets35.Question], folder: Path
) -> list[dict[str, str]]:
    """Return the pairs of one prepared dataset folder; the same pairs on every run.

    A generator seeded with ``SEED`` draws the questions (sorted by ID first),
    then for each question its gold and other passage files.

    Raises:
        DatasetError: A drawn question has no gold passage file in *folder*.
    """
    stems = sorted(path.stem for path in folder.glob("*.md"))
    fresh = dataset == "freshstack"
    to_unit = datasets35.freshstack_unit_map(folder) if fresh else {s: s for s in stems}
    rng = random.Random(SEED)  # noqa: S311 - seeded draw
    pairs = []
    for question in rng.sample(sorted(questions, key=lambda q: q.qid), POOL_QUERIES):
        gold = [s for s in stems if to_unit.get(s) in set(question.relevant)]
        if not gold:
            raise datasets35.DatasetError(
                f"{dataset} question {question.qid} has no gold passage file in {folder}"
            )
        others = [s for s in rng.sample(stems, POOL_OTHERS + len(gold)) if s not in set(gold)]
        chosen = [("gold", s) for s in rng.sample(gold, min(POOL_GOLD, len(gold)))]
        for kind, stem in [*chosen, *(("other", s) for s in others[:POOL_OTHERS])]:
            text = (folder / f"{stem}.md").read_text(encoding="utf-8")
            pairs.append(
                {
                    "pair_id": f"{dataset}:{question.qid}:{stem}",
                    "dataset": dataset,
                    "qid": question.qid,
                    "unit": to_unit[stem],
                    "kind": kind,
                    "query": question.text[:MAX_CHARS],
                    "passage": text[:MAX_CHARS],
                }
            )
    return pairs


def make_pool(
    names: Sequence[str], root: Path, passages_dir: Path, plan: Mapping[str, Any], out: Path
) -> dict[str, Any]:
    """Check each dataset's inputs and passage folder, build the pool, add both anchors.

    Returns:
        The summary written to ``pool-summary.json``.

    Raises:
        DatasetError: An input or a passage file differs from its record.
    """
    pairs: list[dict[str, str]] = []
    summary: dict[str, Any] = {"seed": SEED, "max_chars": MAX_CHARS, "datasets": {}}
    for name in sorted(set(names)):
        datasets35.verify_inputs(root, datasets35.input_hashes(name, plan))
        folder = passages_dir / name
        tree = datasets35.verify_tree(folder)
        found = build_pool(name, datasets35.load_questions(name, root), folder)
        summary["datasets"][name] = {"passages_tree_sha256": tree, "pairs": len(found)}
        pairs += found
    path = _write_jsonl(out / "pool.jsonl", [*pairs, *(dict(a) for a in ANCHORS)])
    summary.update(pairs=len(pairs) + len(ANCHORS), pool_sha256=datasets35.file_sha256(path))
    write_json(out / "pool-summary.json", summary)
    return summary


def draw_pairs(pool: Sequence[Pair], *, n: int = PAIRS, seed: int = SEED) -> list[dict[str, str]]:
    """Draw *n* pairs from *pool* with *seed*, whatever the pool order; add both anchors.

    Returns:
        The drawn pairs sorted by ``pair_id``, then the two anchor pairs.

    Raises:
        CheckRefused: The pool holds fewer than *n* other pairs, a ``pair_id``
            twice, or not both anchor pairs.
    """
    by_id: dict[str, dict[str, str]] = {}
    for pair in pool:
        if pair["pair_id"] in by_id:
            raise CheckRefused(f"pair_id {pair['pair_id']} appears twice in the pool")
        by_id[pair["pair_id"]] = dict(pair)
    if any(pair_id not in by_id for pair_id in ANCHOR_IDS):
        raise CheckRefused("the pool lacks an anchor pair; build it with the pool command")
    anchors = [by_id.pop(pair_id) for pair_id in ANCHOR_IDS]
    if len(by_id) < n:
        raise CheckRefused(f"the pool holds {len(by_id)} pairs; the check needs {n}")
    drawn = random.Random(seed).sample(sorted(by_id), n)  # noqa: S311 - seeded draw
    return [by_id[pair_id] for pair_id in sorted(drawn)] + anchors


# --- verdict -----------------------------------------------------------------------


def _anchors(scores: Mapping[str, float]) -> dict[str, Any]:
    relevant, irrelevant = (scores[pair_id] for pair_id in ANCHOR_IDS)
    ok = relevant >= ANCHOR_RELEVANT_MIN and irrelevant <= ANCHOR_IRRELEVANT_MAX
    return {"relevant": relevant, "irrelevant": irrelevant, "ok": ok}


def verdict(llamacpp: Mapping[str, float], reference: Mapping[str, float]) -> dict[str, Any]:
    """Apply the rank rule and the anchor check to two maps of pair ID to score.

    Returns:
        ``pairs``, ``spearman`` (None when a side gives constant scores),
        ``anchors`` per side, ``probabilities`` (every llama.cpp score in
        [0, 1]), ``pinned``, ``status`` and the ``reasons`` the file fails.

    Raises:
        CheckRefused: The maps hold other pair IDs, no anchors, or not exactly
            ``PAIRS`` pairs besides the anchors.
    """
    if set(llamacpp) != set(reference) or not set(ANCHOR_IDS) <= set(llamacpp):
        raise CheckRefused("the two score files hold different pair IDs, or no anchor pairs")
    ids = sorted(set(llamacpp) - set(ANCHOR_IDS))
    if len(ids) != PAIRS:
        raise CheckRefused(f"the score files hold {len(ids)} pairs and the anchors; need {PAIRS}")
    rho = float(spearmanr([llamacpp[i] for i in ids], [reference[i] for i in ids]).statistic)
    spearman = None if math.isnan(rho) else rho
    anchors = {"llamacpp": _anchors(llamacpp), "reference": _anchors(reference)}
    probabilities = all(0.0 <= score <= 1.0 for score in llamacpp.values())
    reasons = []
    if spearman is None:
        reasons.append("a side gives constant scores, so Spearman is undefined")
    elif spearman < MIN_SPEARMAN:
        reasons.append(f"Spearman {spearman:.4f} is below {MIN_SPEARMAN}")
    for side, found in anchors.items():
        if not found["ok"]:
            reasons.append(
                f"{side} anchors: relevant {found['relevant']:.4f} (needs at least "
                f"{ANCHOR_RELEVANT_MIN}), irrelevant {found['irrelevant']:.4f} (needs at most "
                f"{ANCHOR_IRRELEVANT_MAX})"
            )
    if not probabilities:
        reasons.append("a llama.cpp score is outside [0, 1]: the D27 reading fails; reopen 12.2")
    return {
        "pairs": len(ids),
        "spearman": spearman,
        "min_spearman": MIN_SPEARMAN,
        "anchors": anchors,
        "anchor_rule": {
            "relevant_min": ANCHOR_RELEVANT_MIN,
            "irrelevant_max": ANCHOR_IRRELEVANT_MAX,
        },
        "probabilities": probabilities,
        "pinned": not reasons,
        "status": "not pinned" if reasons else "pinned",
        "reasons": reasons,
    }


def run_verdict(
    llamacpp_file: Path,
    reference_file: Path,
    *,
    out: Path,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, Any]:
    """Compare one llama.cpp score file with the reference file of its size; write the verdict.

    Raises:
        CheckRefused: The files come from different pairs files or reranker
            sizes, or :func:`verdict` refuses them. Nothing is written.
    """
    llama, ref = _read_json(llamacpp_file), _read_json(reference_file)
    if llama["pairs_sha256"] != ref["pairs_sha256"]:
        raise CheckRefused("the two score files come from different pairs files")
    if scorers.model_size(llama["file"]) != scorers.model_size(ref["hf_model"]):
        raise CheckRefused(f"{llama['file']} and {ref['hf_model']} differ in reranker size")
    a = {row["pair_id"]: row["score"] for row in llama["scores"]}
    b = {row["pair_id"]: row["score"] for row in ref["scores"]}
    result = {
        **{key: llama.get(key) for key in ("file", "repository", "sha256", "build", "role")},
        **{key: ref.get(key) for key in ("hf_model", "hf_revision", "gpu", "dtype")},
        "seed": SEED,
        "pairs_sha256": llama["pairs_sha256"],
        **verdict(a, b),
        "llamacpp_times": [llama["started_at"], llama["finished_at"]],
        "reference_times": [ref["started_at"], ref["finished_at"]],
        "checked_at": now().isoformat(),
        "scores": [{"pair_id": i, "llamacpp": a[i], "reference": b[i]} for i in a],
    }
    write_json(out / f"{llama['file']}.rerank-check.json", result)
    return result


# --- files and the command line ----------------------------------------------------


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    tmp.replace(path)
    return path


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _plan() -> dict[str, Any]:
    return _read_json(EXP_DIR / "plan.json")


def _cmd_pool(args: argparse.Namespace) -> int:
    root = datasets35.data_root()
    summary = make_pool(args.dataset, root, args.passages_dir, _plan(), args.out)
    print(f"pool: {summary['pairs']} pairs, SHA-256 {summary['pool_sha256']}", flush=True)
    return 0


def _cmd_draw(args: argparse.Namespace) -> int:
    _write_jsonl(args.out / "pairs.jsonl", draw_pairs(_read_jsonl(args.pool)))
    return 0


def _cmd_llamacpp(args: argparse.Namespace) -> int:
    entry = _read_json(args.entry) if args.entry else dict(arms.plan_role(_plan(), args.role))
    if args.base_url:
        model = args.model or router_env.model_name(entry)
        router = scorers.external_router(args.base_url, model)
    else:
        router = scorers.managed_router(entry, args.out / "router")
    result = scorers.run_llamacpp(
        EXP_DIR,
        entry,
        _read_jsonl(args.pairs),
        out=args.out,
        router=router,
        kind="external" if args.base_url else "managed",
        pairs_sha256=datasets35.file_sha256(args.pairs),
        score=scorers.llamacpp_scores,
    )
    print(f"llamacpp: {result['file']} scored {len(result['scores'])} pairs", flush=True)
    return 0


def _cmd_reference(args: argparse.Namespace) -> int:
    result = scorers.run_reference(
        EXP_DIR,
        _read_jsonl(args.pairs),
        model_id=args.hf_model,
        revision=args.hf_revision,
        out=args.out,
        server_url=args.server_url,
        pairs_sha256=datasets35.file_sha256(args.pairs),
        live=scorers.server_live,
        device=scorers.cuda_device,
        score=scorers.transformers_scores,
        allow_cpu=args.allow_cpu,
    )
    where = f"{result.get('device')} ({result.get('dtype')})"
    print(f"reference: {args.hf_model} on {where}", flush=True)
    return 0


def _cmd_verdict(args: argparse.Namespace) -> int:
    result = run_verdict(args.llamacpp, args.reference, out=args.out)
    print(f"{result['file']}: Spearman {result['spearman']}, {result['status']}", flush=True)
    for reason in result["reasons"]:
        print(f"  {reason}", flush=True)
    return 0 if result["pinned"] else EXIT_NOT_PINNED


_COMMANDS: Mapping[str, Callable[[argparse.Namespace], int]] = {
    "pool": _cmd_pool,
    "draw": _cmd_draw,
    "llamacpp": _cmd_llamacpp,
    "reference": _cmd_reference,
    "verdict": _cmd_verdict,
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    pool = sub.add_parser("pool", help="build pool.jsonl from the prepared datasets")
    names = datasets35.PASSAGE_DATASETS
    pool.add_argument("--dataset", action="append", required=True, choices=names)
    pool.add_argument("--passages-dir", type=Path, required=True)
    draw = sub.add_parser("draw", help="draw the 200 pairs and add both anchors")
    draw.add_argument("--pool", type=Path, required=True)
    llama = sub.add_parser("llamacpp", help="score the pairs on a llama.cpp server")
    which = llama.add_mutually_exclusive_group(required=True)
    which.add_argument("--role", help="a plan.json runtime role, for example reranker-4b")
    which.add_argument("--entry", type=Path, help="a JSON file holding one runtime model object")
    llama.add_argument("--base-url", help="reuse this server (default: start the managed router)")
    llama.add_argument("--model", help="request name on --base-url (default <repository>:<quant>)")
    ref = sub.add_parser("reference", help="score the pairs with the transformers recipe")
    ref.add_argument("--hf-model", required=True)
    ref.add_argument("--hf-revision", required=True)
    ref.add_argument("--server-url", default=router_env.ROUTER_URL.removesuffix("/v1"))
    ref.add_argument("--allow-cpu", action="store_true")
    for scoring in (llama, ref):
        scoring.add_argument("--pairs", type=Path, required=True)
    check = sub.add_parser("verdict", help="apply the rule to two score files")
    check.add_argument("--llamacpp", type=Path, required=True)
    check.add_argument("--reference", type=Path, required=True)
    for command in (pool, draw, llama, ref, check):
        command.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command. Returns 0, 2 (refused) or 3 (``verdict``: not pinned)."""
    args = _parser().parse_args(argv)
    refusals = (ValueError, PreflightError, datasets35.DatasetError, arms.ArmConfigError)
    try:
        return _COMMANDS[args.command](args)
    except (*refusals, router_env.RouterConfigError) as exc:
        print(f"rerank_check35 {args.command} refused: {exc}", file=sys.stderr, flush=True)
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
