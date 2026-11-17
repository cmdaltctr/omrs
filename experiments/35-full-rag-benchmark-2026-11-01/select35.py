"""Selection rule of Experiment 35 on half A (pre-registration section 14.1, task 14.3).

Reads saved per-question nDCG@10 records of the 72 search setups, keeps the
three core datasets and half A only, and applies the three steps of section
14.1. It also holds the setup grid that ``factorial35.py`` shares, the
configuration hash and the expected-maximum curve of section 14.3.

A score record is a mapping with ``dataset``, ``setup``, ``qid`` and
the metric key (``ndcg_at_10``). Other keys are ignored here.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CORE = ("financebench", "freshstack", "bioasq")
EMBEDDERS = ("0.6b", "4b", "8b")
CHUNKS = (512, 1024, 2048)
RERANKERS = ("off", "0.6b", "4b", "8b")
HYBRIDS = ("off", "on")
NDCG = "ndcg_at_10"
WITHIN = 0.01 + 1e-9

_SETUP = re.compile(r"^e(0\.6b|4b|8b)-c(512|1024|2048)-r(off|0\.6b|4b|8b)-h(off|on)(-t20k)?$")


class SelectionError(ValueError):
    """The saved scores cannot feed the selection rule. The message names the gap."""


@dataclass(frozen=True)
class Setup:
    """The factor levels of one setup name."""

    embedder: str
    chunk: int
    reranker: str
    hybrid: str
    t20k: bool = False

    @property
    def name(self) -> str:
        """Return the setup name, ``e<embedder>-c<chunk>-r<reranker>-h<hybrid>[-t20k]``."""
        tail = "-t20k" if self.t20k else ""
        return f"e{self.embedder}-c{self.chunk}-r{self.reranker}-h{self.hybrid}{tail}"

    @property
    def index(self) -> str:
        """Return the index name, ``e<embedder>-c<chunk>``."""
        return f"e{self.embedder}-c{self.chunk}"


def parse_setup(name: str) -> Setup:
    """Parse a setup name into its factor levels.

    Raises:
        SelectionError: The name does not follow the setup grid.
    """
    found = _SETUP.match(name)
    if not found:
        raise SelectionError(f"not a setup name: {name!r}")
    embedder, chunk, reranker, hybrid, t20k = found.groups()
    return Setup(embedder, int(chunk), reranker, hybrid, bool(t20k))


SEARCH_SETUPS = tuple(
    Setup(e, c, r, h).name for e in EMBEDDERS for c in CHUNKS for r in RERANKERS for h in HYBRIDS
)


def within(best: float, score: float) -> bool:
    """Return True when ``score`` is within 0.01 of ``best`` (gap at most 0.01 + 1e-9)."""
    return best - score <= WITHIN


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    return math.fsum(items) / len(items)


def half_a_means(
    records: Iterable[Mapping[str, Any]], halves: Mapping[str, Mapping[str, str]]
) -> dict[str, dict[str, float]]:
    """Return the half-A mean nDCG@10 per setup and core dataset.

    Records of half B and of other datasets are dropped before any mean.

    Raises:
        SelectionError: A setup lacks a score for a half-A question; names both.
    """
    wanted = {d: {q for q, h in halves[d].items() if h == "A"} for d in CORE}
    scores: dict[tuple[str, str], dict[str, float]] = {}
    for row in records:
        dataset, qid = row["dataset"], str(row["qid"])
        if dataset in wanted and qid in wanted[dataset] and row.get(NDCG) is not None:
            scores.setdefault((row["setup"], dataset), {})[qid] = float(row[NDCG])
    means: dict[str, dict[str, float]] = {}
    for setup in SEARCH_SETUPS:
        for dataset in CORE:
            found = scores.get((setup, dataset), {})
            missing = wanted[dataset] - set(found)
            if missing:
                raise SelectionError(
                    f"setup {setup} on {dataset} lacks {len(missing)} half-A scores"
                    f" (for example {sorted(missing)[0]})"
                )
            means.setdefault(setup, {})[dataset] = _mean(found[q] for q in sorted(found))
    return means


def index_costs(
    chunks: Mapping[str, Mapping[str, int]], dimensions: Mapping[str, int]
) -> dict[str, int]:
    """Return stored vector values per index: chunks times dimension, over the core datasets.

    Args:
        chunks: Chunk count per index name and dataset, read from the sealed indexes.
        dimensions: Embedding dimension per embedder level.

    Returns:
        Index cost per index name.
    """
    costs = {}
    for index, counts in chunks.items():
        embedder = index.split("-")[0][1:]
        costs[index] = sum(int(counts[d]) for d in CORE) * int(dimensions[embedder])
    return costs


def _smallest_within(scores: Mapping[str, float]) -> str:
    best = max(scores.values())
    return next(level for level in scores if within(best, scores[level]))


def select(
    records: Iterable[Mapping[str, Any]],
    halves: Mapping[str, Mapping[str, str]],
    chunks: Mapping[str, Mapping[str, int]],
    dimensions: Mapping[str, int],
) -> dict[str, Any]:
    """Apply the three selection steps of section 14.1 on half A.

    Args:
        records: Per-question search score records.
        halves: Per dataset, the half of each question ID.
        chunks: Chunk count per index name and dataset (sealed indexes).
        dimensions: Embedding dimension per embedder level.

    Returns:
        Every pooled score, the step scores, the chosen embedder and reranker
        size, the A3 cell and the index costs.
    """
    means = half_a_means(records, halves)
    pooled = {s: _mean(means[s][d] for d in CORE) for s in SEARCH_SETUPS}
    grid = {s: parse_setup(s) for s in SEARCH_SETUPS}

    embedder_scores = {
        e: _mean(pooled[s] for s, g in grid.items() if g.embedder == e) for e in EMBEDDERS
    }
    embedder = _smallest_within(embedder_scores)
    reranker_scores = {
        r: _mean(pooled[s] for s, g in grid.items() if g.embedder == embedder and g.reranker == r)
        for r in RERANKERS[1:]
    }
    reranker = _smallest_within(reranker_scores)

    cells = [
        s for s, g in grid.items() if g.embedder == embedder and g.reranker in ("off", reranker)
    ]
    cell_scores = {s: pooled[s] for s in cells}
    best = max(cell_scores.values())
    tied = [s for s in cells if within(best, cell_scores[s])]
    costs = index_costs(chunks, dimensions)
    for prefer in (lambda g: g.reranker == "off", lambda g: g.hybrid == "off"):
        if any(prefer(grid[s]) for s in tied):
            tied = [s for s in tied if prefer(grid[s])]
    lowest = min(costs[grid[s].index] for s in tied)
    tied = [s for s in tied if costs[grid[s].index] == lowest]
    cell = min(tied, key=lambda s: grid[s].chunk)
    return {
        "pooled_scores": pooled,
        "dataset_means": means,
        "embedder_scores": embedder_scores,
        "reranker_scores": reranker_scores,
        "cell_scores": cell_scores,
        "embedder": embedder,
        "reranker": reranker,
        "cell": cell,
        "index_cost": {i: costs[i] for i in sorted(costs)},
    }


def configuration_hash(settings: Mapping[str, Any], halves_sha256: str) -> str:
    """Return the SHA-256 of the canonical JSON of the settings plus the halves hash.

    Canonical JSON: keys sorted, no spaces, UTF-8, with ``halves_sha256`` as one
    top-level field.
    """
    body = {**settings, "halves_sha256": halves_sha256}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_selection(
    path: Path, selection: Mapping[str, Any], settings: Mapping[str, Any], halves_sha256: str
) -> str:
    """Write ``selection.json`` atomically with the configuration hash; return the hash.

    Args:
        path: Target file.
        selection: Output of ``select``.
        settings: Resolved settings of the selected cell.
        halves_sha256: SHA-256 of ``halves.json``.

    Returns:
        The configuration hash.
    """
    digest = configuration_hash(settings, halves_sha256)
    body = {**selection, "halves_sha256": halves_sha256, "configuration_hash": digest}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(body, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return digest


def expected_max_curve(scores: Sequence[float]) -> list[float]:
    """Return the expected maximum of n setups drawn without replacement, n = 1 to N.

    Adapted from Dodge et al. 2019: with scores sorted ascending v(1) to v(N),
    E[max of n] = sum over i = n to N of v(i) x C(i - 1, n - 1) / C(N, n).
    """
    v = sorted(scores)
    total = len(v)
    return [
        math.fsum(v[i - 1] * math.comb(i - 1, n - 1) for i in range(n, total + 1))
        / math.comb(total, n)
        for n in range(1, total + 1)
    ]


def _half_a_records(out_dir: Path) -> list[dict[str, Any]]:
    """Return the half-A score records that ``score35.py`` wrote under *out_dir*."""
    return [
        json.loads(line)
        for path in sorted((out_dir / "scores" / "A").glob("*/*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main(argv: Sequence[str] | None = None) -> int:
    """Apply section 14.1 to saved files and write ``selection.json``; return 0, or 2 on a refusal.

    The configuration hash covers the selected cell's settings as the harness
    resolves them for its search stage (no answer host, no judge, no key field).
    """
    import argparse

    import arms
    import datasets35
    import outputs35
    import split35
    from experiments._lib import router_env

    parser = argparse.ArgumentParser(prog="select35.py", description=__doc__.split("\n")[0])
    parser.add_argument("--out-dir", type=Path, required=True, help="the run output folder")
    parser.add_argument("--halves", type=Path, required=True, help="the halves.json file")
    parser.add_argument("--plan", type=Path, default=Path(__file__).resolve().parent / "plan.json")
    args = parser.parse_args(argv)
    layout = outputs35.Layout(args.out_dir)
    try:
        chunks: dict[str, dict[str, int]] = {}
        dimensions: dict[str, int] = {}
        for index in sorted({parse_setup(s).index for s in SEARCH_SETUPS}):
            for dataset in CORE:
                path = layout.fingerprint(dataset, index)
                seal = json.loads(path.read_text(encoding="utf-8"))
                chunks.setdefault(index, {})[dataset] = int(seal["chunks"])
                dimensions[index.split("-")[0][1:]] = int(seal["embedding_dimension"])
        halves = split35.read_halves(args.halves)
        chosen = select(_half_a_records(args.out_dir), halves, chunks, dimensions)
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        settings = arms.settings_values(
            arms.parse_setup(chosen["cell"]), plan, router_env.gguf_dir(), answer_host="", judges=()
        )
        digest = write_selection(
            args.out_dir / "selection.json",
            chosen,
            arms.without_keys(settings),
            datasets35.file_sha256(args.halves),
        )
    except (
        SelectionError,
        OSError,
        arms.ArmConfigError,
        router_env.RouterConfigError,
    ) as error:
        print(f"[error] {error}", flush=True)
        return 2
    print(f"[select] {chosen['cell']}: configuration hash {digest}", flush=True)
    return 0


if __name__ == "__main__":
    import sys

    sys.path[:0] = [str(Path(__file__).resolve().parents[2])]
    sys.exit(main())
