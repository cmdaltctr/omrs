"""Ranking keys, ranking comparison and the Part C neighbour comparison.

Shared copy of the Experiment 48 helpers (``ranking_lib.py`` and the ranking
functions of ``sweep_lib.py``), so later experiments import them and the
closed Experiment 48 folder stays as it ran.

The first sweep run stored ``item.get("id", "")`` for every search result, but
the engine returns ``chunk_id``, so every stored id was blank and the
determinism check compared lists of blanks. :func:`result_id` reads the right
key and refuses a blank one. Part C compared two empty dicts;
:func:`neighbour_mismatches` compares the top-k cosine neighbours of every
chunk under exact and fast mode.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class EmptyResultIdError(ValueError):
    """A search result carries no usable id, so rankings cannot be compared."""


class PopulatedCollectionError(RuntimeError):
    """A slice's collection already holds chunks, so a resume would mix old and new files."""


def result_id(item: Mapping[str, Any]) -> str:
    """Return the chunk id of one search result; refuse a blank one.

    Raises:
        EmptyResultIdError: neither ``chunk_id`` nor ``id`` holds a value.
    """
    value = item.get("chunk_id") or item.get("id")
    if not value:
        raise EmptyResultIdError(f"search result has no chunk_id or id; keys: {sorted(item)}")
    return str(value)


def neighbour_mismatches(
    exact: Mapping[str, Sequence[float]],
    fast: Mapping[str, Sequence[float]],
    k: int = 10,
) -> list[dict[str, Any]]:
    """Compare each chunk's top-k cosine neighbours under exact and fast vectors.

    Each chunk is used as a query against the other chunks of the same slice.
    A mismatch names the query chunk and both neighbour lists.
    A list never holds its own query chunk, so a slice of *k* or fewer chunks
    lists every other chunk and no more.

    Raises:
        ValueError: the two maps do not hold the same chunk ids.
    """
    import numpy as np

    if set(exact) != set(fast):
        raise ValueError("exact and fast must hold the same chunk ids")
    ids = sorted(exact)

    def top_k(vectors: Mapping[str, Sequence[float]]) -> list[list[str]]:
        matrix = np.asarray([vectors[i] for i in ids], dtype=np.float64)
        matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
        scores = matrix @ matrix.T
        np.fill_diagonal(scores, -np.inf)
        # The query chunk sits last (its score is -inf), so a slice of k or fewer
        # chunks would list it. Keep at most n - 1 other chunks.
        order = np.argsort(-scores, axis=1, kind="stable")[:, : min(k, len(ids) - 1)]
        return [[ids[j] for j in row] for row in order]

    left, right = top_k(exact), top_k(fast)
    return [
        {"query": ids[n], "exact": a, "fast": b}
        for n, (a, b) in enumerate(zip(left, right, strict=True))
        if a != b
    ]


def server_snapshot(
    model_names: Sequence[str],
    get: Any,
    environ: Mapping[str, str],
) -> dict[str, Any]:
    """Return the router's ``/props`` per model and the ``LLAMA_ARG_*`` names set.

    *get* takes a router path and returns its JSON. Only call it for models the
    router already loaded: ``/props`` on an unloaded model may load it.

    Raises:
        ValueError: ``/props`` answered with nothing for a model.
    """
    from urllib.parse import quote

    props: dict[str, Any] = {}
    for name in model_names:
        answer = get(f"/props?model={quote(name, safe='')}")
        if not answer:
            raise ValueError(f"/props returned nothing for {name}")
        props[name] = answer
    llama_args = sorted(k for k in environ if k.startswith("LLAMA_ARG_"))
    return {"props": props, "llama_arg_env": llama_args}


def source_matches(source: str, expected: str) -> bool:
    """True when *expected* appears in the file name of *source*, ignoring case.

    Only the file name counts, so a folder whose name holds the keyword cannot
    make a wrong document score as a hit.
    """
    from pathlib import PurePath

    return expected.lower() in PurePath(source).name.lower()


def write_props_snapshot(
    base_url: str,
    model_names: Sequence[str],
    environ: Mapping[str, str],
    path: Path,
    argv: Sequence[str],
) -> None:
    """Append one :func:`server_snapshot` line, with *argv*, to the JSONL file *path*.

    *base_url* is the router address without ``/v1``. Call it only for models the
    router already loaded.
    """
    import urllib.request

    def get(route: str) -> dict:
        # S310: the URL is the fixed local router address, never caller input.
        with urllib.request.urlopen(base_url + route, timeout=60) as response:  # noqa: S310
            return json.loads(response.read().decode())

    snap = server_snapshot(model_names, get, environ)
    snap["argv"] = list(argv)
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snap) + "\n")


def answer_fields(answer: Mapping[str, Any], verify: bool) -> dict[str, Any]:
    """Return the status and verification fields of one answer, with an ``error``.

    ``error`` is empty unless the answer cannot count as a pass: the engine
    reported ``status`` ``error``, or this was a claim-checking run
    (*verify*) and the result shows neither ``verified`` nor failing claims
    (the judge was skipped, unavailable or absent).
    """
    verified = answer.get("verified") is True
    skipped = answer.get("verification_skipped")
    failing = answer.get("unverified_claims") or []
    error = ""
    if answer.get("status") == "error":
        error = str(answer.get("error") or "answer status is error")
    elif verify and not verified and not failing:
        error = (
            f"verification unavailable: {skipped}"
            if skipped
            else "verification missing from the answer result"
        )
    return {
        "status": answer.get("status"),
        "verified": verified,
        "verification_skipped": skipped,
        "unverified_claims": failing,
        "error": error,
    }


def require_empty_collection(collection: str, chunks: int) -> None:
    """Refuse a slice whose collection already holds *chunks* chunks.

    Raises:
        PopulatedCollectionError: *chunks* is above zero; the message names the collection.
    """
    if chunks:
        raise PopulatedCollectionError(
            f"collection {collection} already holds {chunks} chunks; a resumed slice "
            "would mix old and new files. Delete the collection and rerun the slice."
        )


def compare_rankings(
    mode: str, run1: Mapping[str, Sequence[str]], run2: Mapping[str, Sequence[str]]
) -> list[dict[str, Any]]:
    """Compare two per-question rankings; report every difference in full.

    The comparison covers the union of the questions of both runs. A question
    that only one run holds is a mismatch, even when its ranking is empty, and
    the row names the run it is missing from (``missing_from``).
    """
    mismatches: list[dict[str, Any]] = []
    for question in sorted(set(run1) | set(run2)):
        left, right = list(run1.get(question, [])), list(run2.get(question, []))
        missing = [name for name, run in (("run1", run1), ("run2", run2)) if question not in run]
        if left != right or missing:
            row: dict[str, Any] = {"question": question, "mode": mode, "run1": left, "run2": right}
            if missing:
                row["missing_from"] = missing[0]
            mismatches.append(row)
    return mismatches


def incomplete_comparisons(
    baseline: Sequence[Mapping[str, Any]], repeat: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """List the (question, mode) pairs a determinism check could not compare.

    A search that failed in either run leaves an empty ranking, and two empty
    rankings compare equal. Each such pair, and each repeat row with no
    baseline row, becomes a row with an ``incomplete`` reason, so it cannot
    pass as a match.
    """
    first = {(row["question"], row["mode"]): row for row in baseline}
    found: list[dict[str, Any]] = []
    for row in repeat:
        key = (row["question"], row["mode"])
        reason = ""
        if row.get("error"):
            reason = f"repeat search failed: {row['error']}"
        elif key not in first:
            reason = "no baseline row"
        elif first[key].get("error"):
            reason = f"baseline search failed: {first[key]['error']}"
        if reason:
            found.append({"question": key[0], "mode": key[1], "incomplete": reason})
    return found
