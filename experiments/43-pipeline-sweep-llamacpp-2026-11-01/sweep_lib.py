"""Pure helpers for the pipeline-sweep experiment (change tasks 3.1, 4.1, 2.3).

No I/O except where a function takes a path: the runners own the network,
the engine and the output files. Tests live in ``test_sweep_lib.py``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

PAGE_CAP = 200
"""D1: a FinanceBench PDF enters the fixed set only with this many pages or fewer."""


class ChangedInputError(RuntimeError):
    """A frozen input file differs from its recorded SHA-256."""


class ChunkingGuardError(RuntimeError):
    """Markdown chunking did not resolve to the model-token-aware path."""


# --- input hashes (task 3.1) -----------------------------------------------


def file_sha256(path: Path, chunk_bytes: int = 1 << 20) -> str:
    """Return the SHA-256 hex digest of *path*."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk_bytes), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_input_hashes(directory: Path, recorded: Mapping[str, str]) -> None:
    """Stop when any recorded file changed; name the file and both hashes.

    Args:
        directory: Folder that holds the input files.
        recorded: File name to expected SHA-256, from the protocol.

    Raises:
        ChangedInputError: A file is missing or its hash differs.
    """
    for name, expected in sorted(recorded.items()):
        path = directory / name
        if not path.is_file():
            raise ChangedInputError(f"{name}: input file is missing (expected {expected})")
        found = file_sha256(path)
        if found != expected:
            raise ChangedInputError(f"{name}: SHA-256 changed; recorded {expected}, found {found}")


# --- FinanceBench page conversion (D1) --------------------------------------


def convert_evidence_page(page_num: int) -> int:
    """Convert a zero-indexed FinanceBench ``evidence_page_num`` to a 1-based page."""
    if page_num < 0:
        raise ValueError(f"evidence_page_num must be 0 or greater, got {page_num}")
    return page_num + 1


# --- determinism comparison (task 3.1) --------------------------------------


def compare_rankings(
    mode: str, run1: Mapping[str, Sequence[str]], run2: Mapping[str, Sequence[str]]
) -> list[dict[str, Any]]:
    """Compare two per-question rankings; report every difference in full."""
    mismatches: list[dict[str, Any]] = []
    for question in sorted(run1):
        left, right = list(run1[question]), list(run2.get(question, []))
        if left != right:
            mismatches.append({"question": question, "mode": mode, "run1": left, "run2": right})
    return mismatches


# --- FinanceBench selection (D1, task 2.3) ----------------------------------


def select_financebench(docs: Sequence[Mapping[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """Rank by question count (highest first, ties by name) under the page cap."""
    capped = [dict(doc) for doc in docs if doc["pages"] <= PAGE_CAP]
    ranked = sorted(capped, key=lambda doc: (-doc["question_count"], doc["doc_name"]))
    return ranked[:limit]


# --- extrapolation (task 4.1) ------------------------------------------------


def extrapolate(
    *,
    tokens_per_second: float,
    corpus_tokens: int | None = None,
    tokens_per_page: float | None = None,
    total_pages: int | None = None,
    corpus: str | None = None,
) -> float:
    """Estimate embedding hours for one corpus from a measured rate.

    Either pass the corpus token count, or tokens per page times total pages.
    """
    if corpus_tokens is None:
        if tokens_per_page is None or total_pages is None:
            name = corpus or "this corpus"
            raise ValueError(f"{name}: token count missing; pass corpus_tokens or page figures")
        corpus_tokens = int(tokens_per_page * total_pages)
    return corpus_tokens / tokens_per_second / 3600.0


# --- chunking guard (task 3.1) ----------------------------------------------


def chunking_guard(
    settings: Any,
    resolver: Callable[[Any], Any] | None = None,
) -> Any:
    """Require the model-token-aware Markdown path; stop and name the tokenizer.

    Args:
        settings: Effective settings for the run.
        resolver: Injectable ``resolve_markdown_chunking``; defaults to the
            OMRS implementation (``core/chunking/model_token.py``).

    Returns:
        The resolution, with the loaded tokenizer.

    Raises:
        ChunkingGuardError: The splitter resolved to ``legacy_fallback``.
    """
    if resolver is None:
        from omrs.core.chunking.model_token import resolve_markdown_chunking

        resolver = resolve_markdown_chunking
    resolution = resolver(settings)
    if not resolution.model_token_aware:
        identity = resolution.tokenizer_identity
        raise ChunkingGuardError(
            "Markdown chunking resolved to legacy_fallback; the sweep stops. "
            f"Tokenizer model {identity.get('model', '<unset>')!r}, "
            f"revision {identity.get('revision', '<unset>')!r}. "
            "Fix embedding.tokenizer_model and tokenizer_revision."
        )
    return resolution
