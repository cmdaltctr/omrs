"""Experiment 35 output layout, resumable row files and done-markers.

Layout under the output folder (default ``output/restricted/...``: answers and
evidence hold corpus text, design D10)::

    <out>/<dataset>/<index arm>/index/ingest.jsonl    one row per file
    <out>/<dataset>/<arm>/run<n>/search.jsonl         one row per question
    <out>/<dataset>/<arm>/run<n>/answer.jsonl
    <out>/<dataset>/<arm>/run<n>/judge-<name>.jsonl
    <out>/<dataset>/<arm>/run<n>/traces.jsonl         D8 trace rows
    <out>/<dataset>/<arm>/determinism.json

Each row file is appended one line at a time, flushed and synced, so a stopped
run loses at most the line it was writing. ``<stage>.key.json`` holds the run
key (limit, corpus sample, seed, question IDs) and ``.done-<stage>.json`` marks
a finished stage. Summaries and markers are written atomically (``.tmp``, then
rename).
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class StageFileExistsError(RuntimeError):
    """A stage file exists and ``--resume`` is not set."""


class ResumeMismatchError(RuntimeError):
    """``--resume`` found a stage started with other inputs."""


@dataclass(frozen=True)
class Layout:
    """Paths of one output folder."""

    root: Path

    def arm_dir(self, dataset: str, arm: str) -> Path:
        """Return the folder of one dataset and arm."""
        return self.root / dataset / arm

    def index_dir(self, dataset: str, owner: str) -> Path:
        """Return the ingest folder of the arm that owns an index."""
        return self.arm_dir(dataset, owner) / "index"

    def run_dir(self, dataset: str, arm: str, run: int) -> Path:
        """Return the folder of one repetition."""
        return self.arm_dir(dataset, arm) / f"run{run}"

    @property
    def lancedb(self) -> Path:
        """The LanceDB store of every index."""
        return self.root / "lancedb"

    @property
    def state_dir(self) -> Path:
        """The router state folder (``OMRS_STATE_DIR``)."""
        return self.root / "state"

    @property
    def work_dir(self) -> Path:
        """Prepared corpus files (BioASQ passages)."""
        return self.root / "work"

    def config_dir(self, dataset: str, arm: str, stage: str) -> Path:
        """The scratch ``omrs.jsonc`` folder of one process."""
        return self.root / "config" / f"{dataset}-{arm}-{stage}"


def run_key(
    limit: int | None, corpus_sample: int | None, seed: int, qids: Sequence[str]
) -> dict[str, Any]:
    """Return what makes two runs comparable: the inputs a resume must match."""
    return {"limit": limit, "corpus_sample": corpus_sample, "seed": seed, "qids": list(qids)}


def write_json(path: Path, value: Any) -> None:
    """Write *value* as JSON to *path* atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _differences(found: Mapping[str, Any], key: Mapping[str, Any]) -> list[str]:
    return [name for name in key if found.get(name) != key.get(name)]


class RowFile:
    """One stage's JSONL row file with its key file and done-marker."""

    def __init__(self, folder: Path, stage: str, key: Mapping[str, Any], *, resume: bool) -> None:
        """Open the stage; check the key of an earlier start.

        Raises:
            StageFileExistsError: The stage started before and *resume* is off.
            ResumeMismatchError: The earlier start had another key; the message
                names each differing field.
        """
        self.path = folder / f"{stage}.jsonl"
        self.stage = stage
        self._key_path = folder / f"{stage}.key.json"
        self._done_path = folder / f".done-{stage}.json"
        if self._key_path.exists():
            if not resume:
                raise StageFileExistsError(
                    f"{self.path} exists; pass --resume to continue it, or use another --out-dir"
                )
            found = json.loads(self._key_path.read_text(encoding="utf-8"))
            differ = _differences(found, key)
            if differ:
                raise ResumeMismatchError(
                    f"--resume refused: stage {stage} in {folder} started with another "
                    f"{', '.join(differ)}. Use another --out-dir, or the same inputs."
                )
        else:
            write_json(self._key_path, dict(key))
        self._drop_partial_last_line()

    @property
    def done(self) -> bool:
        """True when the stage finished."""
        return self._done_path.exists()

    def _drop_partial_last_line(self) -> None:
        if not self.path.exists():
            return
        text = self.path.read_text(encoding="utf-8")
        if text and not text.endswith("\n"):
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(text[: text.rfind("\n") + 1], encoding="utf-8")
            tmp.replace(self.path)

    def rows(self) -> list[dict[str, Any]]:
        """Return every row written so far."""
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def done_ids(self, field: str) -> set[str]:
        """Return the *field* value of every row written so far."""
        return {str(row[field]) for row in self.rows()}

    def append(self, row: Mapping[str, Any]) -> None:
        """Append one row; flush and sync it."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def mark_done(self, payload: Mapping[str, Any]) -> None:
        """Write the done-marker with *payload*."""
        write_json(self._done_path, dict(payload))


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Return the rows of a JSONL file, or an empty list when it is missing."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def say(text: str) -> None:
    """Print one progress line and flush it."""
    print(text, flush=True)
