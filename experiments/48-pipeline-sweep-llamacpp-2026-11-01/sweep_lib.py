"""Pure helpers for the pipeline-sweep experiment (change tasks 3.1, 4.1, 2.3).

No I/O except where a function takes a path: the runners own the network,
the engine and the output files. Tests live in ``test_sweep_lib.py``.
"""

from __future__ import annotations

import hashlib
import statistics
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

PAGE_CAP = 200
"""D1: a FinanceBench PDF enters the fixed set only with this many pages or fewer."""


class ChangedInputError(RuntimeError):
    """A frozen input file differs from its recorded SHA-256."""


class ChunkingGuardError(RuntimeError):
    """Markdown chunking did not resolve to the model-token-aware path."""


class LimitMismatchError(RuntimeError):
    """A resumed artefact came from a run with a different ``--limit``."""


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


def require_same_limit(recorded: int | None, current: int | None, what: str) -> None:
    """Refuse to reuse *what* when its ``--limit`` differs from this run's.

    A smoke run (``--limit 1``) writes the same markers and files as a full
    run. Without this check a later ``--resume`` skips the stage and reports
    the full run complete.

    Args:
        recorded: The ``limit`` stored with the artefact (``None`` for a full run).
        current: The ``--limit`` of this run (``None`` for a full run).
        what: Name of the artefact, for the message.

    Raises:
        LimitMismatchError: The two limits differ. Names both and the fix.
    """
    if recorded != current:
        raise LimitMismatchError(
            f"{what} came from a run with --limit {recorded}; this run has --limit {current}. "
            "Move the old output and the scratch index aside, then run again."
        )


def stray_files(folder: Path, wanted: Sequence[str]) -> list[str]:
    """Return the names in *folder* that are not in *wanted*, sorted; empty if it is missing."""
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if p.name not in set(wanted))


def ingest_failure(result: Mapping[str, Any]) -> str:
    """Return a message when an ingest result shows a failure, else an empty string.

    ``ingest_path_async`` returns ``status: "error"`` without raising when
    every file fails, and ``warnings`` when some fail.
    """
    if result.get("status") == "error":
        return f"ingest status error: {result.get('message') or result.get('error_type') or ''}"
    warnings = result.get("warnings")
    if warnings:
        return "ingest warnings: " + "; ".join(str(w) for w in warnings)
    return ""


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


def speed_summary(
    exact: Mapping[str, Mapping[str, float]], fast: Mapping[str, Mapping[str, float]]
) -> dict[str, dict[str, float]]:
    """Vectors per second of each mode and the gain, per slice (design D6a step 5).

    Args:
        exact: Slice name to ``{"seconds", "vectors"}`` for exact mode.
        fast: The same for fast mode.

    Raises:
        ValueError: The two modes did not time the same slices.
    """
    if set(exact) != set(fast):
        raise ValueError(
            f"exact timed {sorted(exact)} but fast timed {sorted(fast)}; "
            "run both modes on the same slices"
        )
    summary = {}
    for name in sorted(exact):
        slow = exact[name]["vectors"] / exact[name]["seconds"]
        quick = fast[name]["vectors"] / fast[name]["seconds"]
        summary[name] = {
            "exact_vectors_per_second": slow,
            "fast_vectors_per_second": quick,
            "speed_gain": quick / slow,
        }
    return summary


# --- Part C vector comparison (task 4.0) ------------------------------------


def compare_vectors(
    exact: Mapping[str, Sequence[float]],
    fast: Mapping[str, Sequence[float]],
    threshold: float = 0.9999,
) -> dict[str, Any]:
    """Compare every vector pair; list the chunks below *threshold* cosine."""
    import math

    cosines = []
    failed = []
    for chunk_id in sorted(exact):
        left, right = exact[chunk_id], fast.get(chunk_id)
        if right is None:
            failed.append(chunk_id)
            continue
        dot = sum(a * b for a, b in zip(left, right, strict=False))
        norm = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
        cosine = dot / norm if norm else 0.0
        cosines.append(cosine)
        if cosine < threshold:
            failed.append(chunk_id)
    median = statistics.median(cosines) if cosines else 1.0
    return {
        "pairs": len(cosines),
        "lowest_cosine": min(cosines) if cosines else 1.0,
        "median_cosine": median,
        "failed_chunks": failed,
    }


def preset_has_parallel(models: Sequence[Mapping[str, Any]]) -> None:
    """Require an explicit ``parallel`` in every embedding preset (D6a)."""
    for model in models:
        if "parallel" not in model.get("server_args", {}):
            raise ValueError(
                f"{model.get('file', '<model>')}: preset has no parallel value; "
                "write it out so no default can change silently"
            )


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
