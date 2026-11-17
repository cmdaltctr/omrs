"""Experiment 35 release kit: TREC run export and re-judge (task 16.21, pre-registration 19).

TREC run export. Each saved ranked list (stored chunks, best first) is
collapsed to units with the scorer's own rule (``scoring35.unit_list``) and
written as ``qid Q0 unit rank score tag``. The score is ``1000 - rank``, so it
falls strictly with rank: ``trec_eval`` sorts by score and would re-sort tied
RRF scores, and a rank-derived score keeps the saved order (H-25). Only IDs are
written, never corpus text::

    uv run python release35.py trec --dataset financebench --saved <search.jsonl> \\
        --tag <setup> --out <release>/<setup>.trec

``--saved`` holds one ``{"qid", "chunks": [...]}`` object per line, the chunks
as the search stage saves them. A FreshStack export also needs
``--unit-map`` (file stem to parent ID, JSON).

Re-judge kit. The released cited evidence holds unit and chunk IDs, never text.
To judge the answers again, rebuild the index from the pinned dataset
revisions with the harness ingest stage (the scratch settings of the run), then
read the cited chunks back from it::

    uv run python release35.py rejudge --evidence <released evidence.jsonl> \\
        --collection <collection> --out <local folder>/rejudge.jsonl

Each released evidence line is ``{"dataset", "setup", "run", "qid",
"evidence": [{"chunk_id", "unit"}, ...]}``. A cited chunk missing from the
rebuilt index, or whose unit differs from the released one, stops the kit:
the index was not rebuilt from the pinned revisions. The output holds corpus
text, so it stays local and is never released.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import scoring35

TOP_SCORE = 1000


def trec_run(
    dataset: str,
    saved: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    tag: str,
    unit_map: Mapping[str, str] | None = None,
) -> list[str]:
    """Return the TREC run lines of one setup, questions in sorted order.

    Args:
        dataset: ``financebench``, ``freshstack``, ``bioasq`` or ``legal``.
        saved: Question ID to its saved stored chunks, best first.
        tag: The run tag, the setup name.
        unit_map: FreshStack file stem to parent ID.

    Returns:
        ``qid Q0 unit rank score tag`` lines; rank from 1, score ``1000 - rank``.
    """
    lines = []
    for qid in sorted(saved):
        units, _ = scoring35.unit_list(dataset, saved[qid], unit_map)
        for rank, unit in enumerate(units, start=1):
            lines.append(f"{qid} Q0 {unit} {rank} {TOP_SCORE - rank} {tag}")
    return lines


def write_trec_run(
    path: Path,
    dataset: str,
    saved: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    tag: str,
    unit_map: Mapping[str, str] | None = None,
) -> None:
    """Write :func:`trec_run` lines to *path* atomically."""
    _write_lines(path, trec_run(dataset, saved, tag=tag, unit_map=unit_map))


def read_chunks(store: Any, collection: str, chunk_ids: set[str]) -> dict[str, dict[str, Any]]:
    """Read the named stored chunks from a rebuilt index.

    Args:
        store: The OMRS vector store of the rebuilt index (``iter_documents``).
        collection: The collection name.
        chunk_ids: The chunk IDs to keep.

    Returns:
        Chunk ID to ``{"chunk_id", "text", "metadata", "page_label"}``.
    """
    chunks = {}
    for chunk_id, text, metadata in store.iter_documents(collection):
        if chunk_id in chunk_ids:
            chunks[chunk_id] = {
                "chunk_id": chunk_id,
                "text": text,
                "metadata": metadata,
                "page_label": metadata.get("page_label"),
            }
    return chunks


def rebuild_evidence(
    released: Iterable[Mapping[str, Any]],
    chunks: Mapping[str, Mapping[str, Any]],
    *,
    unit_map: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Put the rebuilt chunk text beside each released chunk and unit ID.

    Raises:
        ValueError: A cited chunk is missing from the rebuilt index, or its
            unit differs from the released unit. The message names the chunk.
    """
    rows = []
    for row in released:
        evidence = []
        for item in row["evidence"]:
            chunk = chunks.get(item["chunk_id"])
            if chunk is None:
                raise ValueError(
                    f"chunk {item['chunk_id']} of question {row['qid']} is not in the rebuilt "
                    "index; rebuild it from the pinned dataset revisions"
                )
            (unit,), _ = scoring35.unit_list(row["dataset"], [chunk], unit_map)
            if unit != item["unit"]:
                raise ValueError(
                    f"chunk {item['chunk_id']}: released unit {item['unit']}, rebuilt unit "
                    f"{unit}; rebuild the index from the pinned dataset revisions"
                )
            evidence.append({"chunk_id": item["chunk_id"], "unit": unit, "text": chunk["text"]})
        rows.append(
            {**{k: row[k] for k in ("dataset", "setup", "run", "qid")}, "evidence": evidence}
        )
    return rows


def run_rejudge(
    evidence_path: Path,
    store: Any,
    collection: str,
    out: Path,
    *,
    unit_map: Mapping[str, str] | None = None,
) -> None:
    """Rebuild the evidence text of every released evidence line and write it to *out*."""
    released = _read_jsonl(evidence_path)
    wanted = {item["chunk_id"] for row in released for item in row["evidence"]}
    rows = rebuild_evidence(released, read_chunks(store, collection, wanted), unit_map=unit_map)
    _write_lines(out, [json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows])


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def _write_lines(path: Path, lines: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    tmp.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``trec`` or ``rejudge`` command. Returns 0."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    trec = commands.add_parser("trec")
    trec.add_argument("--dataset", required=True)
    trec.add_argument("--saved", type=Path, required=True)
    trec.add_argument("--tag", required=True)
    trec.add_argument("--out", type=Path, required=True)
    rejudge = commands.add_parser("rejudge")
    rejudge.add_argument("--evidence", type=Path, required=True)
    rejudge.add_argument("--collection", required=True)
    rejudge.add_argument("--out", type=Path, required=True)
    for command in (trec, rejudge):
        command.add_argument("--unit-map", type=Path)
    args = parser.parse_args(argv)
    unit_map = json.loads(args.unit_map.read_text(encoding="utf-8")) if args.unit_map else None
    if args.command == "trec":
        saved = {row["qid"]: row["chunks"] for row in _read_jsonl(args.saved)}
        write_trec_run(args.out, args.dataset, saved, tag=args.tag, unit_map=unit_map)
        return 0
    from omrs.compose import build_engine

    engine = build_engine()
    run_rejudge(args.evidence, engine.store, args.collection, args.out, unit_map=unit_map)
    return 0


if __name__ == "__main__":
    sys.exit(main())
