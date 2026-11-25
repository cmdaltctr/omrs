"""Claim-kind gate for Experiment 35: sample, labelling page, classify and gate (8.3 to 8.7).

Usage (``sample``, ``page`` and ``gate`` read saved files only and run on the Mac;
``classify`` makes hosted calls and runs on the pod)::

    refusals35.py sample --seed 20261112 --n 100 --out-dir OUT \\
        --folder bioasq=PATH --folder financebench=PATH --folder freshstack=PATH \\
        [--exclude SAMPLE.json --exclude EXAMPLES.json]
    refusals35.py page --out-dir OUT
    refusals35.py classify --out-dir OUT --examples EXAMPLES.json
    refusals35.py gate --out-dir OUT --labels L1.json [--labels L2.json] [--resolved FILE]

The sample draws from the valid claims of the pre-freeze test pod session (pre-freeze
amendment 2026-11-23; task 9.2). Those answers use the main-run answer settings, with
reasoning ``none``. Before then, the source was the 2026-11-11 smoke runs, which used
the default reasoning. Pass each ``--folder DATASET=PATH`` as the dataset folder of the
session output (``<out>/<dataset>``, with ``answer/<setup>/run<n>/answer.jsonl`` inside).
A run folder whose ``traces.jsonl`` does not show ``answer_reasoning`` ``none`` is refused.
The sample takes about a third from each dataset, and inside each dataset half from
claims the pre-freeze regular expression flags and half from the rest (design D15). A
claim that sits in several setups or runs counts once (one key per question ID and
claim text).
The ``classify`` command (:func:`classify_command`) runs the classifier on the sample through
the hosted gate and writes ``sample-kinds.jsonl``, which ``gate`` reads. It reads the model,
host, reasoning, temperature and seed from ``plan.json`` and sends 100 hosted calls. The
report on the main run is in ``refusalreport35.py``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import re
import sys
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import claimcontext35
import claimkinds35
import labelpage35
from experiments._lib.hosted_calls import HostedGate, RateLimitStop
from experiments._lib.ordered_rows import append_line, read_lines
from experiments._lib.stats_d6 import wilson
from claimcontext35 import SampleError
from outputs35 import read_rows, write_json

PARTIAL = "sample-kinds.partial.jsonl"
ReplyCall = Callable[[list[dict[str, str]]], Awaitable[Any]]

#: The pre-freeze regular expression, copied unchanged from the FreshStack smoke
#: rerun analysis script (``fs-rerun/fs_analyse.py`` in the Experiment 35 data
#: folder). It is a baseline and a sampling stratum only.
PREFREEZE_REGEX = re.compile(
    r"(do(es)? not (cover|include|identify|contain|mention|address|provide|list|say|state"
    r"|establish|discuss|support an answer)|not (covered|provided|found|available)"
    r"|only (retrieved |available |provided )?source|source only"
    r"|cannot (be )?(conclusively )?(determin|answer)|no information|insufficient|add no"
    r"|unrelated|ZZQJ-9097|no exchange-registered)",
    re.I,
)
#: Pass marks of the gate (design D15, 2026-11-12; precision added 2026-11-23, pre-freeze).
THRESHOLDS = {"agreement": 0.90, "recall": 0.90, "precision": 0.90}


def session_claims(
    folders: Mapping[str, Path | Sequence[Path]], questions: Mapping[str, Mapping[str, str]]
) -> list[dict[str, Any]]:
    """Return the distinct claims of the given dataset folders of a test pod session.

    Args:
        folders: Dataset name to its dataset folder in the session output
            (``<out>/<dataset>``), or a list of them. Each holds
            ``answer/<setup>/run<n>/answer.jsonl`` and ``traces.jsonl`` per run folder (``outputs35.Layout``).
        questions: Dataset name to (question ID to question text).

    Returns:
        One record per distinct (question ID, claim text), in folder order, with
        the full answer and cited passages of the first answer that holds it
        (``claimcontext35.claim_contexts``).

    Raises:
        SampleError: A folder holds no answer file, or a run folder does not show
            answer reasoning ``none`` in its ``traces.jsonl`` (names the folder).
    """
    claims: dict[str, dict[str, Any]] = {}
    for dataset in sorted(folders):
        given = folders[dataset]
        for folder in [given] if isinstance(given, Path) else given:
            _folder_claims(claims, dataset, folder, questions)
    return list(claims.values())


def _folder_claims(claims: dict, dataset: str, folder: Path, questions: Mapping) -> None:
    """Add the claims of one dataset folder to *claims*; the first answer of a claim wins."""
    found = sorted(folder.glob("answer/*/run*/answer.jsonl"))
    if not found:
        raise SampleError(
            f"{folder}: no answer/<setup>/run<n>/answer.jsonl; pass the dataset folder "
            "of the pre-freeze test pod session output"
        )
    for answers in found:
        claimcontext35.check_reasoning(answers.parent)
        for row in read_rows(answers):
            for claim, passages in claimcontext35.claim_contexts(row):
                key = claimkinds35.claim_key(row["qid"], claim)
                claims.setdefault(
                    key,
                    {
                        "claim_key": key,
                        "dataset": dataset,
                        "qid": row["qid"],
                        "question": questions[dataset][row["qid"]],
                        "claim": claim,
                        "answer": row["answer"],
                        "passages": passages,
                        "flagged": bool(PREFREEZE_REGEX.search(claim)),
                    },
                )


def _takes(quota: int, flagged: int, plain: int) -> tuple[int, int]:
    """Split one dataset's quota: half flagged (rounded up), a short stratum filled by the other."""
    take_f, take_p = (quota + 1) // 2, quota // 2
    if flagged < take_f:
        take_f, take_p = flagged, quota - flagged
    elif plain < take_p:
        take_f, take_p = quota - plain, plain
    return min(take_f, flagged), min(take_p, plain)


def draw_sample(claims: Sequence[Mapping[str, Any]], *, seed: int, n: int) -> dict[str, Any]:
    """Draw the gate sample.

    Args:
        claims: Records from :func:`session_claims`.
        seed: The sample seed (20261112).
        n: The sample size (100).

    Returns:
        ``seed``, ``n``, ``strata`` (size, drawn and fraction each), ``items``
        (shuffled with the seed) and ``pool`` (claims outside the sample).

    Raises:
        SampleError: A dataset holds fewer claims than its quota.
    """
    datasets = sorted({c["dataset"] for c in claims})
    rng = random.Random(seed)  # noqa: S311 - seeded draw, not security
    strata: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    for d, dataset in enumerate(datasets):
        quota = n // len(datasets) + (1 if d < n % len(datasets) else 0)
        pools = {
            name: sorted(
                (
                    c
                    for c in claims
                    if c["dataset"] == dataset and c["flagged"] == (name == "flagged")
                ),
                key=lambda c: c["claim_key"],
            )
            for name in ("flagged", "plain")
        }
        sizes = (len(pools["flagged"]), len(pools["plain"]))
        if sum(sizes) < quota:  # a short draw must not be recorded as the registered n
            raise SampleError(f"{dataset}: {sum(sizes)} claims left, below its quota {quota}")
        takes = dict(zip(("flagged", "plain"), _takes(quota, *sizes), strict=True))
        for name in ("flagged", "plain"):
            stratum = f"{dataset}/{name}"
            picked = rng.sample(pools[name], takes[name])
            size = len(pools[name])
            strata.append(
                {
                    "stratum": stratum,
                    "size": size,
                    "drawn": len(picked),
                    "fraction": len(picked) / size if size else 0.0,
                }
            )
            items += [{"item_id": c["claim_key"], **c, "stratum": stratum} for c in picked]
    rng.shuffle(items)
    keys = {i["claim_key"] for i in items}
    pool = [
        dict(c) for c in sorted(claims, key=lambda c: c["claim_key"]) if c["claim_key"] not in keys
    ]
    return {"seed": seed, "n": n, "strata": strata, "items": items, "pool": pool}


def write_sample(out_dir: Path, drawn: Mapping[str, Any]) -> None:
    """Write ``sample.json`` (with ``excluded`` after ``--exclude``) and ``examples-pool.json``."""
    keys = ("seed", "n", "strata", "items", "excluded")
    write_json(out_dir / "sample.json", {k: drawn[k] for k in keys if k in drawn})
    write_json(out_dir / "examples-pool.json", drawn["pool"])


def _sample(out_dir: Path) -> dict[str, Any]:
    return json.loads((out_dir / "sample.json").read_text(encoding="utf-8"))


def write_claim_page(out_dir: Path) -> Path:
    """Write the blind claim-kind labelling page for the saved sample; return its path."""
    path = out_dir / "label-claim-kinds.html"
    labelpage35.write_page(path, "claim_kinds", _sample(out_dir)["items"])
    return path


async def classify_sample(
    out_dir: Path, call: ReplyCall, *, prompt: str, version: str, concurrency: int = 16
) -> None:
    """Classify each sample claim and write ``sample-kinds.jsonl`` (a pod stage).

    Each finished call is saved at once to ``sample-kinds.partial.jsonl``. A rerun sends only
    the claims with no saved kind, so a stop keeps the paid calls. The partial file goes
    away after ``sample-kinds.jsonl`` is written.

    Args:
        out_dir: The folder holding ``sample.json``.
        call: The gated model call; it returns the reply (``text``, ``model_returned``,
            ``provider_returned``).
        prompt: The fixed prompt.
        version: The classifier version.
        concurrency: Calls in flight.

    Raises:
        SystemExit: The partial file holds a kind of another classifier version.
    """
    items = _sample(out_dir)["items"]
    partial = out_dir / PARTIAL
    saved = {r["claim_key"]: r for r in read_lines(partial)}
    stale = sorted({r["version"] for r in saved.values()} - {version})
    if stale:
        raise SystemExit(f"{partial} holds classifier versions {stale}; delete it to start again")
    gate_ = asyncio.Semaphore(concurrency)

    async def one(item: Mapping[str, Any]) -> None:
        async with gate_:
            reply = await call(claimkinds35.messages(prompt, item["question"], item["claim"]))
            row = {
                "claim_key": item["claim_key"],
                "kind": claimkinds35.parse_kind(str(reply.text)),
                "version": version,
                "model_returned": getattr(reply, "model_returned", None),
                "provider_returned": getattr(reply, "provider_returned", None),
            }
            append_line(partial, row)
            saved[item["claim_key"]] = row

    await asyncio.gather(*(one(i) for i in items if i["claim_key"] not in saved))
    rows = [saved[i["claim_key"]] for i in items]
    tmp = out_dir / "sample-kinds.jsonl.tmp"
    tmp.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    tmp.replace(out_dir / "sample-kinds.jsonl")
    partial.unlink(missing_ok=True)


def _scores(scored: list[tuple[float, bool, bool | None]]) -> dict[str, float]:
    """Weighted and unweighted agreement, recall and precision.

    Each entry is (weight, human says refusal, predicted refusal or None when unreadable).
    """

    def ratio(pairs: list[tuple[float, bool]]) -> float:
        total = sum(w for w, _ in pairs)
        return sum(w for w, hit in pairs if hit) / total if total else math.nan

    out: dict[str, float] = {}
    for prefix, weigh in (("weighted_", True), ("", False)):

        def w(x: float, weigh: bool = weigh) -> float:
            return x if weigh else 1.0

        out[prefix + "agreement"] = ratio([(w(x), p is not None and p == h) for x, h, p in scored])
        out[prefix + "recall"] = ratio([(w(x), p is True) for x, h, p in scored if h])
        out[prefix + "precision"] = ratio([(w(x), h) for x, h, p in scored if p is True])
    return out


def _intervals(scored: list[tuple[float, bool, bool | None]]) -> dict[str, Any]:
    """95% Wilson intervals on the unweighted counts; None when the count is zero."""
    counts = {
        "agreement": [p is not None and p == h for _, h, p in scored],
        "recall": [p is True for _, h, p in scored if h],
        "precision": [h for _, h, p in scored if p is True],
    }
    out: dict[str, Any] = {"method": "wilson", "confidence": 0.95}
    for name, hits in counts.items():
        low, high = wilson(sum(hits), len(hits), 0.95)
        found = {"successes": sum(hits), "n": len(hits), "low": low, "high": high}
        out[name] = found if hits else None
    return out


def gate(
    sample: Mapping[str, Any], labels: Mapping[str, str], kinds: Mapping[str, str], *, version: str
) -> dict[str, Any]:
    """Score the classifier and the regular expression against the human labels.

    "Can't tell" items are left out and counted. Mixed and factual both count
    as not refusal. An ``unreadable`` kind counts as a miss. Each item weighs
    the inverse of its stratum's sampling fraction. The gate passes only when
    the weighted agreement, the weighted refusal recall and the weighted refusal
    precision (human label is refusal when the classifier says refusal) all
    reach 0.90; an undefined figure (no human refusal, or no predicted refusal)
    fails. The 95% Wilson intervals in ``intervals`` use the unweighted counts.
    They are reported only and decide nothing.

    Args:
        sample: The saved sample (``strata`` and ``items``).
        labels: The reference human label by item ID.
        kinds: The classifier kind by claim key.
        version: The classifier version the kinds came from.

    Returns:
        The ``gate.json`` record.
    """
    weight = {s["stratum"]: 1 / s["fraction"] for s in sample["strata"] if s["fraction"]}
    classifier: list[tuple[float, bool, bool | None]] = []
    baseline: list[tuple[float, bool, bool | None]] = []
    cant_tell = unreadable = 0
    for item in sample["items"]:
        human = labels[item["item_id"]]
        kind = kinds[item["claim_key"]]
        unreadable += kind == claimkinds35.UNREADABLE
        if human == labelpage35.CANT_TELL:
            cant_tell += 1
            continue
        w = weight[item["stratum"]]
        predicted = None if kind == claimkinds35.UNREADABLE else kind == "refusal"
        classifier.append((w, human == "refusal", predicted))
        baseline.append((w, human == "refusal", bool(item["flagged"])))
    scores = _scores(classifier)
    passed = all(
        not math.isnan(scores[f"weighted_{name}"]) and scores[f"weighted_{name}"] >= bar
        for name, bar in THRESHOLDS.items()
    )
    return {
        "pass": passed,
        "version": version,
        "thresholds": THRESHOLDS,
        "classifier": scores,
        "intervals": _intervals(classifier),
        "baseline_regex": _scores(baseline),
        "labelled": len(sample["items"]),
        "scored": len(classifier),
        "refusal_count": sum(1 for _, h, _ in classifier if h),
        "cant_tell_count": cant_tell,
        "unreadable_count": unreadable,
    }


PLAN = Path(__file__).resolve().parent / "plan.json"
EXIT_RATE_LIMIT = 5
Builder = Callable[[Mapping[str, Any], list[Mapping[str, str]]], tuple[Any, str, str]]


def classify_command(
    out_dir: Path,
    examples_file: Path,
    *,
    concurrency: int,
    attempts: int,
    build_classifier: Builder | None = None,
) -> int:
    """Run the classifier on the saved sample through the hosted gate (a pod stage).

    Args:
        out_dir: The folder holding ``sample.json``; ``sample-kinds.jsonl`` goes there.
        examples_file: JSON list of prompt examples (``qid``, ``question``, ``claim``, ``kind``).
        concurrency: Calls in flight (``--classify-concurrency``).
        attempts: The most sends of one rate-limited call (``--rate-limit-attempts``).
        build_classifier: Builds ``(call, version, prompt)`` from the plan and the examples.
            Tests inject a stub; the default builds the real classifier from ``plan.json``.

    Returns:
        0 after the kinds are saved, or 5 on a rate-limit stop (finished kinds stay in ``sample-kinds.partial.jsonl``).

    Raises:
        SystemExit: A prompt example is a sample claim.
    """
    items = _sample(out_dir)["items"]
    examples = json.loads(examples_file.read_text(encoding="utf-8"))
    try:
        claimkinds35.check_examples(examples, {i["claim_key"] for i in items})
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if build_classifier is None:
        import claimstage35

        build_classifier = claimstage35.build_classifier
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    call, version, prompt = build_classifier(plan, examples)
    gate_ = HostedGate("claim-classifier", concurrency, attempts=attempts)

    async def gated(messages: list[dict[str, str]]) -> Any:
        return await gate_.call(lambda: call(messages))

    try:
        asyncio.run(
            classify_sample(out_dir, gated, prompt=prompt, version=version, concurrency=concurrency)
        )
    except RateLimitStop as stop:
        print(f"[classify] stopped: {stop}", flush=True)
        return EXIT_RATE_LIMIT
    print(f"[classify] {len(items)} kinds saved, version {version}", flush=True)
    return 0


def _gate_cli(out_dir: Path, label_files: Sequence[Path], resolved: Path | None) -> int:
    sample = _sample(out_dir)
    ids = [i["item_id"] for i in sample["items"]]
    found = dict(labelpage35.read_labels(p, "claim_kinds", ids) for p in label_files)
    resolved_labels = json.loads(resolved.read_text(encoding="utf-8")) if resolved else {}
    labels, unresolved = labelpage35.reference_labels(
        found["L1"], found.get("L2", {}), resolved_labels
    )
    rows = read_rows(out_dir / "sample-kinds.jsonl")
    versions = {r["version"] for r in rows}
    if len(versions) != 1:
        raise SystemExit(f"sample-kinds.jsonl holds versions {sorted(versions)}; need exactly one")
    result = gate(sample, labels, {r["claim_key"]: r["kind"] for r in rows}, version=versions.pop())
    result["unresolved_count"] = unresolved
    result["labellers"] = sorted(found)
    write_json(out_dir / "gate.json", result)
    box = result["intervals"]
    spans = {
        name: [round(box[name]["low"], 3), round(box[name]["high"], 3)] if box[name] else None
        for name in THRESHOLDS
    }
    verdict = "pass" if result["pass"] else "fail"
    print(
        f"gate {verdict}: {result['classifier']}; "
        f"95% wilson intervals (reported only, decide nothing): {spans}",
        flush=True,
    )
    return 0


def _questions(datasets: Sequence[str]) -> dict[str, dict[str, str]]:
    import datasets35

    root = datasets35.data_root()
    return {d: {q.qid: q.text for q in datasets35.load_questions(d, root)} for d in datasets}


def main(argv: Sequence[str] | None = None, *, build_classifier: Builder | None = None) -> int:
    """Run one subcommand: ``sample``, ``page``, ``classify`` or ``gate``."""
    parser = argparse.ArgumentParser(prog="refusals35.py")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--seed", type=int, required=True)
    s.add_argument("--n", type=int, required=True)
    s.add_argument("--folder", action="append", required=True, help="DATASET=PATH")
    s.add_argument("--out-dir", type=Path, required=True)
    s.add_argument("--exclude", type=Path, action="append", default=[], help="sample or examples")
    p = sub.add_parser("page")
    p.add_argument("--out-dir", type=Path, required=True)
    c = sub.add_parser("classify")
    c.add_argument("--out-dir", type=Path, required=True)
    c.add_argument("--examples", type=Path, required=True)
    c.add_argument("--classify-concurrency", type=int, default=16)
    c.add_argument("--rate-limit-attempts", type=int, default=6)
    g = sub.add_parser("gate")
    g.add_argument("--out-dir", type=Path, required=True)
    g.add_argument("--labels", type=Path, action="append", required=True)
    g.add_argument("--resolved", type=Path)
    args = parser.parse_args(argv)
    if args.command == "sample":
        folders: dict[str, list[Path]] = {}
        for d, p in (f.split("=", 1) for f in args.folder):
            folders.setdefault(d, []).append(Path(p))
        claims = session_claims(folders, _questions(sorted(folders)))
        banned = claimcontext35.excluded_keys(args.exclude)
        kept = [c for c in claims if c["claim_key"] not in banned]
        drawn = draw_sample(kept, seed=args.seed, n=args.n)
        if args.exclude:
            names = [p.name for p in args.exclude]
            drawn["excluded"] = {"files": names, "claims": len(claims) - len(kept)}
        write_sample(args.out_dir, drawn)
        return 0
    if args.command == "page":
        print(write_claim_page(args.out_dir), flush=True)
        return 0
    if args.command == "classify":
        return classify_command(
            args.out_dir,
            args.examples,
            concurrency=args.classify_concurrency,
            attempts=args.rate_limit_attempts,
            build_classifier=build_classifier,
        )
    return _gate_cli(args.out_dir, args.labels, args.resolved)


if __name__ == "__main__":
    sys.exit(main())
