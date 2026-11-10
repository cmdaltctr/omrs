"""JSONL trace writer for the Experiment 35 harness (task 2.6, design D8).

The writer appends one JSON line per query and major stage to a file. It
never writes to stdout, because stdout is the MCP protocol channel. A failed
query keeps its row with status ``error`` or ``degraded``, so it stays in the
denominators.

Example::

    writer = TraceWriter(
        path,
        benchmark_revision="exp35-r1",
        run_id="run-001",
        arm="dense-rerank",
        repetition=1,
        effective_settings=settings_dict,
        model_identities={"embedding": {"file": "x.gguf", "sha256": "..."}},
    )
    writer.write(stage="retrieve", dataset="financebench", question_id="q-17")

A key that names a secret (an API key, a token, an authorisation header, a
password) anywhere in a row or in the run context raises ``ValueError``.
Token counts such as ``prompt_tokens`` are allowed. The caller removes
secrets before it passes settings in.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

__all__ = ["D8_FIELDS", "STATUSES", "TraceWriter"]

D8_FIELDS: tuple[str, ...] = (
    "benchmark_revision",
    "run_id",
    "arm",
    "repetition",
    "dataset",
    "question_id",
    "stage",
    "effective_settings",
    "model_identities",
    "reader_route",
    "chunk_counts",
    "retrieved",
    "rerank_input",
    "rerank_output",
    "durations_s",
    "token_counts",
    "answer_model",
    "judge_model",
    "status",
    "error",
)
"""Every key in each trace row. A field that does not apply holds ``None``."""

STATUSES: frozenset[str] = frozenset({"ok", "degraded", "error"})

_SECRET_KEY = re.compile(
    r"api[_-]?key|secret|passw(or)?d|authorization|credential|bearer"
    r"|(access|auth|refresh|session|api|bearer)[_-]?token|^token$",
    re.IGNORECASE,
)


def _refuse_secret_keys(value: Any, where: str) -> None:
    """Raise ``ValueError`` when a mapping key in *value* names a secret."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _SECRET_KEY.search(str(key)):
                raise ValueError(f"trace {where} holds secret-looking key {str(key)!r}")
            _refuse_secret_keys(item, where)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _refuse_secret_keys(item, where)


class TraceWriter:
    """Append D8 trace rows to one JSONL file."""

    def __init__(
        self,
        path: Path,
        *,
        benchmark_revision: str,
        run_id: str,
        arm: str,
        repetition: int,
        effective_settings: Mapping[str, Any],
        model_identities: Mapping[str, Any],
    ) -> None:
        """Fix the fields that stay the same for the whole run.

        Args:
            path: The JSONL file. Its parent folder is created on first write.
            benchmark_revision: The benchmark revision under test.
            run_id: The run identifier.
            arm: The arm name.
            repetition: The repetition number (1, 2 or 3).
            effective_settings: The effective settings, without secrets.
            model_identities: Model identities (file and SHA-256 for local models).

        Raises:
            ValueError: A key in the settings or identities names a secret.
        """
        _refuse_secret_keys(effective_settings, "effective_settings")
        _refuse_secret_keys(model_identities, "model_identities")
        self._path = path
        self._context: dict[str, Any] = {
            "benchmark_revision": benchmark_revision,
            "run_id": run_id,
            "arm": arm,
            "repetition": repetition,
            "effective_settings": dict(effective_settings),
            "model_identities": dict(model_identities),
        }

    def write(
        self,
        *,
        stage: str,
        dataset: str,
        question_id: str,
        status: str = "ok",
        error: str | None = None,
        reader_route: str | None = None,
        chunk_counts: Mapping[str, int] | None = None,
        retrieved: Mapping[str, Any] | None = None,
        rerank_input: list[str] | None = None,
        rerank_output: list[str] | None = None,
        durations_s: Mapping[str, float] | None = None,
        token_counts: Mapping[str, int] | None = None,
        answer_model: str | None = None,
        judge_model: str | None = None,
    ) -> None:
        """Append one row.

        Args:
            stage: The pipeline stage, such as ``retrieve`` or ``answer``.
            dataset: The dataset name.
            question_id: The question identifier.
            status: ``ok``, ``degraded`` or ``error``.
            error: The error or degradation message, when status is not ``ok``.
            reader_route: The reader and OCR route, where it applies.
            chunk_counts: Chunk counts for the stage.
            retrieved: Chunk IDs, parent or page IDs and scores.
            rerank_input: The ranking that went into the reranker.
            rerank_output: The ranking that came out of the reranker.
            durations_s: Stage durations in seconds.
            token_counts: Token counts, where the model reports them.
            answer_model: The answer model identity.
            judge_model: The judge model identity.

        Raises:
            ValueError: *status* is unknown, or a key in the row names a secret.
        """
        if status not in STATUSES:
            raise ValueError(f"trace status {status!r} is not one of {sorted(STATUSES)}")
        row: dict[str, Any] = {
            **self._context,
            "dataset": dataset,
            "question_id": question_id,
            "stage": stage,
            "reader_route": reader_route,
            "chunk_counts": chunk_counts,
            "retrieved": retrieved,
            "rerank_input": rerank_input,
            "rerank_output": rerank_output,
            "durations_s": durations_s,
            "token_counts": token_counts,
            "answer_model": answer_model,
            "judge_model": judge_model,
            "status": status,
            "error": error,
        }
        _refuse_secret_keys(row, "row")
        line = json.dumps({name: row[name] for name in D8_FIELDS}, ensure_ascii=False)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
