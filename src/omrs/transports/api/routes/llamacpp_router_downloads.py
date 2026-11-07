"""Which listed router models have no file, and how big they are (one-llamacpp-router, B).

The Router panel asks this before a Start, so one dialog can name the models and the
total download size. The size of a model is the size of its quantisation in the file
listing of its Hugging Face repository, read the way the download job reads it
(``hf_models.list_repo_files`` and ``model_sources.group_gguf_files``). The host is
contacted only when :func:`downloads_needed` runs, and only for an entry with no file.
A size that cannot be read (offline, a label the repository lacks) is ``None``.
"""

from __future__ import annotations

from typing import Any

from ....core.providers import model_sources as rules
from ....integrations import huggingface_models as hf_models
from ..llamacpp_server import RouterConfig


def model_size(model: str) -> int | None:
    """Return the download size in bytes of *model* (``org/name:LABEL``), or ``None``.

    The name is checked before any request. Any failure to read the listing, and a label
    that the repository does not list, give ``None``.
    """
    repo, _, label = model.rpartition(":")
    if not (rules.is_valid_repo_id(repo) and rules.is_valid_label(label)):
        return None
    try:
        found = hf_models.list_repo_files(repo)
    except hf_models.ModelHostError:
        return None
    entry = next((e for e in rules.group_gguf_files(found.files) if e.label == label), None)
    return entry.size_bytes if entry is not None else None


def downloads_needed(config: RouterConfig) -> dict[str, Any]:
    """Return the body of ``GET /v1/llamacpp/router/downloads-needed`` (without ``status``).

    Blocks on the network, so call it in a thread.

    Args:
        config: The saved router values; its entries are the list.

    Returns:
        ``models`` (an ``id``, a ``model`` and a ``size_bytes`` or ``None`` for each entry
        with no file, in list order) and ``total_bytes`` (the sum, or ``None`` when any
        size is unknown; ``0`` when no entry is missing).
    """
    models = [
        {"id": entry_id, "model": entry.model, "size_bytes": model_size(entry.model)}
        for entry_id, entry in config.entries.items()
        if not (entry.file or "").strip()
    ]
    sizes = [item["size_bytes"] for item in models]
    known = all(size is not None for size in sizes)
    return {"models": models, "total_bytes": sum(sizes) if known else None}  # type: ignore[arg-type]
