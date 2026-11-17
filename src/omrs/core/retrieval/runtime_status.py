"""What a reranker backend reports about its own runtime (issue #215).

The Settings runtime page lists the reranker model. Each backend knows what
it needs to run, so each backend class answers with a ``runtime_status``
classmethod and the page does not branch on backend names. A backend without
the method gives the page an unknown state.

This module is pure data and one helper. It imports nothing from
``transports/``, and it opens no file and no connection.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

State = Literal["ready", "missing", "unknown"]

#: Reads the local Hugging Face cache for one file: ``(repo, filename) -> cached``.
CacheProbe = Callable[[str, str], bool]


@dataclass(frozen=True)
class RerankerRuntimeStatus:
    """The runtime state of one reranker backend.

    Attributes:
        state: ``ready``, ``missing`` or ``unknown`` (the check could not run).
        reason: Why it is not ready, or ``None``.
        fix_command: A copy command that fixes it, or ``None``.
    """

    state: State
    reason: str | None = None
    fix_command: str | None = None


def hf_download_command(repo: str, files: Sequence[str], revision: str | None = None) -> str:
    """Return the ``hf download`` command for *files* of *repo*."""
    command = f"uvx --from huggingface_hub hf download {repo} {' '.join(files)}"
    return f"{command} --revision {revision}" if revision else command


def onnx_cache_status(
    model: str, candidates: Sequence[str], cached: CacheProbe, configured_backend: str
) -> RerankerRuntimeStatus:
    """Check the ONNX files of *model* in the local Hugging Face cache.

    Args:
        model: The Hugging Face model id (``retrieval.rerank_model``).
        candidates: The ONNX file names to try, in priority order.
        cached: The read-only cache probe. The caller supplies it.
        configured_backend: The ``rerank_backend`` setting. When it is not
            ``onnx``, the ONNX backend runs as the fallback and the reason says so.
    """
    if cached(model, "tokenizer.json") and any(cached(model, name) for name in candidates):
        return RerankerRuntimeStatus("ready")
    reason = f"{model} is not in the local cache. The first reranked search downloads it."
    if configured_backend != "onnx":
        reason = (
            f"The {configured_backend} backend is not available, so the ONNX backend runs. {reason}"
        )
    fix = hf_download_command(model, [candidates[0], "tokenizer.json"])
    return RerankerRuntimeStatus("missing", reason, fix)
