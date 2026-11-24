"""BM25 calibration before the Exp 35 freeze: the old OMRS BM25 against the reference BM25.

The check compares four BM25 configurations on public BEIR sets. None of these sets is an
Exp 35 dataset, so the choice of BM25 does not depend on the Exp 35 questions.

- ``old``: the BM25 OMRS used before 2026-11-24 (k1 1.5, b 0.75, no stemming).
- ``k1b``: the reference k1 0.9 and b 0.4 only, without stemming.
- ``stem``: Porter stemming at k1 1.5 and b 0.75. OMRS ships this BM25 since 2026-11-24,
  because it scored highest here (``sparse.BM25_K1`` and ``sparse.BM25_B``).
- ``reference``: the Anserini/Pyserini BEIR setup (k1 0.9, b 0.4, Porter stems; Lin et al.
  2021, SIGIR, 10.1145/3404835.3463238). Its scores check this implementation against the
  published Pyserini "flat" numbers.

All four use ``rank_bm25.BM25Okapi`` (epsilon 0.25) and the OMRS list of 47 stop words.
A document is indexed as its title and text joined by a space, as in the Pyserini "flat"
index. The scores are nDCG@10, as in BEIR, and Recall@100. Recall@100 matters most for
Exp 35, because hybrid search keeps 100 BM25 results per side before fusion.

Run (from the repo root)::

    uv run --no-sync python experiments/35-full-rag-benchmark-2026-11-01/prefreeze/\
bm25_calibration35.py --beir-dir ~/Development/DATA/omrs/benchmarks/beir --out <folder>
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import random
import re
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from omrs.core.retrieval import sparse

#: Pyserini BM25 flat, BEIR test split (castorini.github.io/pyserini/2cr/beir.html, read
#: 2026-11-24): (nDCG@10, Recall@100).
PYSERINI_FLAT: dict[str, tuple[float, float]] = {
    "scifact": (0.679, 0.925),
    "nfcorpus": (0.322, 0.246),
    "fiqa": (0.236, 0.539),
    "cqadupstack-programmers": (0.280, 0.559),
}
DATASETS = tuple(PYSERINI_FLAT)
#: plan.json ``seeds.bm25_calibration`` (pre-registration section 16). It replaced the
#: retired seed 20261124 on 2026-11-24.
SEED = 20261139
RESAMPLES = 10_000
_WORD = re.compile(r"\b\w+\b")


def old_tokens(text: str) -> list[str]:
    """Tokenise as OMRS did before 2026-11-24: lowercase words, no stop words, no stems."""
    return [t for t in _WORD.findall(text.lower()) if t and t not in sparse._STOP_WORDS]


@dataclass(frozen=True)
class Config:
    """One BM25 configuration."""

    name: str
    k1: float
    b: float
    tokens: Callable[[str], list[str]]


CONFIGS: tuple[Config, ...] = (
    Config("old", 1.5, 0.75, old_tokens),
    Config("k1b", 0.9, 0.4, old_tokens),
    Config("stem", sparse.BM25_K1, sparse.BM25_B, sparse.tokenize_english),
    Config("reference", 0.9, 0.4, sparse.tokenize_english),
)


@dataclass
class Dataset:
    """A BEIR test split: documents, queries and graded judgements."""

    doc_ids: list[str]
    doc_texts: list[str]
    queries: dict[str, str]
    qrels: dict[str, dict[str, int]]


def _rows(folder: Path, part: str) -> list[dict]:
    """Read ``corpus`` or ``queries`` rows from BeIR parquet or MTEB jsonl."""
    parquet = sorted(glob.glob(str(folder / part / "*.parquet")))
    if parquet:
        import pyarrow.parquet as pq

        return pq.read_table(parquet[0]).to_pylist()
    with (folder / f"{part}.jsonl").open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


#: Download folder of each set under ``--beir-dir`` (BeIR on Hugging Face; CQADupStack
#: from the MTEB copy, which carries its qrels inside).
FOLDERS = {
    "scifact": ("scifact", "scifact-qrels"),
    "nfcorpus": ("nfcorpus", "nfcorpus-qrels"),
    "fiqa": ("fiqa", "fiqa-qrels"),
    "cqadupstack-programmers": ("cqa-programmers-mteb", "cqa-programmers-mteb/qrels"),
}


def load(beir_dir: Path, name: str) -> Dataset:
    """Load the test split of *name*. Only queries with a positive judgement are kept."""
    corpus_dir, qrels_dir = FOLDERS[name]
    folder = beir_dir / corpus_dir
    qrels: dict[str, dict[str, int]] = {}
    with (beir_dir / qrels_dir / "test.tsv").open(encoding="utf-8") as fh:
        next(fh)
        for line in fh:
            qid, did, score = line.rstrip("\n").split("\t")[:3]
            if int(score) > 0:
                qrels.setdefault(qid, {})[did] = int(score)
    docs = _rows(folder, "corpus")
    queries = {str(r["_id"]): str(r["text"]) for r in _rows(folder, "queries")}
    return Dataset(
        doc_ids=[str(r["_id"]) for r in docs],
        doc_texts=[f"{r.get('title') or ''} {r.get('text') or ''}".strip() for r in docs],
        queries={q: queries[q] for q in sorted(qrels) if q in queries},
        qrels=qrels,
    )


def ndcg_at(ranked: Sequence[str], rels: Mapping[str, int], k: int = 10) -> float:
    """nDCG@k with linear gain, as trec_eval and BEIR compute it."""
    dcg = sum(rels.get(d, 0) / math.log2(i + 2) for i, d in enumerate(ranked[:k]))
    ideal = sorted(rels.values(), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def recall_at(ranked: Sequence[str], rels: Mapping[str, int], k: int = 100) -> float:
    """The share of the relevant documents found in the top *k*."""
    relevant = {d for d, g in rels.items() if g > 0}
    return len(relevant.intersection(ranked[:k])) / len(relevant) if relevant else 0.0


def run_config(data: Dataset, config: Config, depth: int = 100) -> dict[str, dict[str, float]]:
    """Score every query of *data* with *config*; return per-query nDCG@10 and Recall@100."""
    from rank_bm25 import BM25Okapi

    index = BM25Okapi([config.tokens(t) for t in data.doc_texts], k1=config.k1, b=config.b)
    out: dict[str, dict[str, float]] = {}
    for qid, text in data.queries.items():
        scores = index.get_scores(config.tokens(text))
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], data.doc_ids[i]))[:depth]
        ranked = [data.doc_ids[i] for i in order]
        out[qid] = {
            "ndcg10": ndcg_at(ranked, data.qrels[qid]),
            "recall100": recall_at(ranked, data.qrels[qid]),
        }
    return out


def paired_stats(a: Sequence[float], b: Sequence[float], seed: int = SEED) -> dict[str, float]:
    """Mean of ``b - a`` with a 95% bootstrap interval and a two-sided sign-flip p-value."""
    diffs = [y - x for x, y in zip(a, b, strict=True)]
    n = len(diffs)
    mean = sum(diffs) / n
    rng = random.Random(seed)
    boots = sorted(sum(rng.choices(diffs, k=n)) / n for _ in range(RESAMPLES))
    extreme = 0
    for _ in range(RESAMPLES):
        flipped = sum(d if rng.random() < 0.5 else -d for d in diffs) / n
        extreme += abs(flipped) >= abs(mean) - 1e-12
    return {
        "mean_diff": mean,
        "ci_low": boots[int(0.025 * RESAMPLES)],
        "ci_high": boots[int(0.975 * RESAMPLES) - 1],
        "p": (extreme + 1) / (RESAMPLES + 1),
        "n": n,
        "wins": sum(d > 0 for d in diffs),
        "losses": sum(d < 0 for d in diffs),
    }


def holm(pvalues: Mapping[str, float]) -> dict[str, float]:
    """Holm-adjusted p-values (family-wise error control)."""
    order = sorted(pvalues, key=lambda k: pvalues[k])
    adjusted: dict[str, float] = {}
    running = 0.0
    for i, key in enumerate(order):
        running = max(running, min(1.0, (len(order) - i) * pvalues[key]))
        adjusted[key] = running
    return adjusted


def summarise(per_query: Mapping[str, Mapping[str, Mapping[str, dict[str, float]]]]) -> dict:
    """Build the means, the reference gaps and the old-versus-reference tests."""
    means: dict = {}
    tests: dict = {}
    for ds, by_config in per_query.items():
        qids = sorted(by_config["old"])
        means[ds] = {
            cfg: {m: sum(rows[q][m] for q in qids) / len(qids) for m in ("ndcg10", "recall100")}
            for cfg, rows in by_config.items()
        }
        for metric in ("ndcg10", "recall100"):
            a = [by_config["old"][q][metric] for q in qids]
            b = [by_config["reference"][q][metric] for q in qids]
            tests[f"{ds}:{metric}"] = paired_stats(a, b)
    adjusted = holm({k: v["p"] for k, v in tests.items()})
    for key, value in tests.items():
        value["p_holm"] = adjusted[key]
    return {"means": means, "pyserini_flat": PYSERINI_FLAT, "old_vs_reference": tests}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the calibration and write ``bm25-calibration.json`` and per-query rows."""
    parser = argparse.ArgumentParser(description="BM25 calibration on BEIR before the Exp 35 freeze.")
    parser.add_argument("--beir-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--datasets", nargs="*", default=list(DATASETS))
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    per_query: dict = {}
    for name in args.datasets:
        data = load(args.beir_dir.expanduser(), name)
        print(f"[bm25] {name}: {len(data.doc_ids)} documents, {len(data.queries)} queries", flush=True)
        per_query[name] = {}
        for config in CONFIGS:
            started = time.perf_counter()
            per_query[name][config.name] = run_config(data, config)
            print(f"[bm25] {name}/{config.name}: {time.perf_counter() - started:.1f} s", flush=True)
    summary = summarise(per_query)
    summary["configs"] = {c.name: {"k1": c.k1, "b": c.b} for c in CONFIGS}
    summary["seed"], summary["resamples"] = SEED, RESAMPLES
    tmp = args.out / "bm25-calibration.json.tmp"
    tmp.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    tmp.replace(args.out / "bm25-calibration.json")
    rows = args.out / "bm25-per-query.jsonl.tmp"
    with rows.open("w", encoding="utf-8") as fh:
        for ds, by_config in per_query.items():
            for cfg, by_q in by_config.items():
                for qid, scores in by_q.items():
                    fh.write(json.dumps({"dataset": ds, "config": cfg, "qid": qid, **scores}) + "\n")
    rows.replace(args.out / "bm25-per-query.jsonl")
    print(json.dumps(summary["means"], indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
