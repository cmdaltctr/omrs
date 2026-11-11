"""Test helpers for the LLM-AggreFact runner and scorer: a tiny split and stub judges.

A plain module, not a ``conftest.py``: other pre-freeze scripts share this folder.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

PREFREEZE = Path(__file__).resolve().parent
if str(PREFREEZE) not in sys.path:
    sys.path.insert(0, str(PREFREEZE))

import aggrefact_lib as lib  # noqa: E402

#: Three datasets of 10 rows; the text carries a marker the tests look for in output.
DATASETS = ("AggreFact-CNN", "Wice", "RAGTruth")
ROW_MARK = "ROWTEXT-MARK"


def write_split(path: Path, per_dataset: int = 10) -> Path:
    """Write a tiny parquet split; row ``idx`` has label ``idx % 2``. Return *path*."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = [
        (name, f"{ROW_MARK} doc {name} {i}", f"{ROW_MARK} claim {d * per_dataset + i}",
         (d * per_dataset + i) % 2)
        for d, name in enumerate(DATASETS)
        for i in range(per_dataset)
    ]  # fmt: skip
    table = pa.table(
        {
            "dataset": [r[0] for r in rows],
            "doc": [r[1] for r in rows],
            "claim": [r[2] for r in rows],
            "label": [r[3] for r in rows],
            "contamination_identifier": ["x"] * len(rows),
        }
    )
    pq.write_table(table, path)
    return path


def make_split(tmp_path: Path, monkeypatch: Any) -> Path:
    """Return a tiny split whose SHA-256 the runner accepts as the pinned one (30 rows)."""
    path = write_split(tmp_path / "test.parquet")
    monkeypatch.setattr(lib, "PARQUET_SHA256", lib.file_sha256(path))
    monkeypatch.setattr(lib, "EXPECTED_ROWS", 30)
    return path


def isolate_env(monkeypatch: Any) -> None:
    """Give the test its own copy of ``os.environ`` (the runner rewrites it)."""
    monkeypatch.setattr(os, "environ", dict(os.environ))


class StubJudge:
    """A claim judge with no router: *decide(idx)* gives ``(verdict, error)`` or raises."""

    def __init__(self, strategy: str, decide: Callable[[int], tuple[str, str | None]]) -> None:
        """Take the strategy's registered version, as the production judge does."""
        from omrs.core.answer.judges import registry

        self.name = strategy
        self.version = registry.get(strategy).VERSION
        self._decide = decide
        self.calls: list[int] = []

    async def judge(self, claim: str, evidence_texts: Any) -> Any:
        """Return the verdict *decide* gives for the row index the claim carries."""
        from omrs.core.answer.judges.base import JudgeCall, Judgement

        assert len(evidence_texts) == 1 and ROW_MARK in evidence_texts[0]  # noqa: S101
        idx = int(claim.rsplit(" ", 1)[-1])
        self.calls.append(idx)
        verdict, error = self._decide(idx)
        call = JudgeCall(
            strategy=self.name,
            model="stub/model:Q8_0",
            host=None,
            sha256="ab" * 32,
            version=self.version,
            settings={"threshold": 0.5},
            p_yes=0.9 if verdict == "supported" else 0.1,
            error=error,
        )
        return Judgement(verdict, call)


def truthful(idx: int) -> tuple[str, str | None]:
    """Return the right verdict for the tiny split (label = idx % 2)."""
    return ("supported" if idx % 2 else "unsupported"), None
