"""Read the model names from a llama.cpp ``GET /models`` reply.

A llama.cpp server can list its models in two layouts: OpenAI style
``{"data": [{"id": ...}]}`` and ``{"models": [{"model" or "name": ...}]}``.
Every check that asks "does the server list this model?" reads the reply
here, so the checks cannot disagree about which models a server has.
"""

from __future__ import annotations

from typing import Any


def served_model_names(body: Any) -> list[str]:
    """Return the model names in a ``/models`` reply, in order, without repeats.

    Args:
        body: The decoded JSON reply.

    Returns:
        The names from both layouts. A reply that is not an object gives ``[]``.
    """
    if not isinstance(body, dict):
        return []
    names: list[str] = []
    for entry in body.get("data") or []:
        if isinstance(entry, dict) and entry.get("id"):
            names.append(str(entry["id"]))
    for entry in body.get("models") or []:
        if not isinstance(entry, dict):
            continue
        for key in ("model", "name"):
            if entry.get(key):
                names.append(str(entry[key]))
    return list(dict.fromkeys(names))
