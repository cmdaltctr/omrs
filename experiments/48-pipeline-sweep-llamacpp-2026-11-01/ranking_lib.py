"""Ranking keys and the Part C neighbour comparison (review fixes, 2026-11-08).

The first sweep run stored ``item.get("id", "")`` for every search result, but
the engine returns ``chunk_id``, so every stored id was blank and the
determinism check compared lists of blanks. :func:`result_id` reads the right
key and refuses a blank one. Part C compared two empty dicts;
:func:`neighbour_mismatches` compares the top-k cosine neighbours of every
chunk under exact and fast mode.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class EmptyResultIdError(ValueError):
    """A search result carries no usable id, so rankings cannot be compared."""


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
        order = np.argsort(-scores, axis=1, kind="stable")[:, :k]
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
