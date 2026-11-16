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
key (limit, corpus sample, seed, question IDs and, from task 3.4, the
configuration fields of :func:`config_fields`) and ``.done-<stage>.json`` marks
a finished stage. Summaries and markers are written atomically (``.tmp``, then
rename).

A ``RowFile`` holds ``<stage folder>/.lock`` while it is open (task 3.2), so a
second runner on the same folder stops before it reads a row or sends a call.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments._lib.run_safety import exclusive_lock

CONFIG_FIELDS = ("settings_sha256", "runtime_sha256", "prompt_sha256", "harness_commit")
"""The configuration fields of a stage key, also kept in the done-marker."""


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
    limit: int | None,
    corpus_sample: int | None,
    seed: int,
    qids: Sequence[str],
    *,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return what makes two runs comparable: the inputs a resume must match.

    Args:
        limit: The question limit, or None.
        corpus_sample: The corpus sample size, or None.
        seed: The selection seed.
        qids: The selected question IDs, in frozen order.
        config: The result of :func:`config_fields`, or None for today's key.
    """
    key = {"limit": limit, "corpus_sample": corpus_sample, "seed": seed, "qids": list(qids)}
    return {**key, **(config or {})}


def _without_keys(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(k): _without_keys(v) for k, v in value.items() if not str(k).endswith("api_key")
        }
    if isinstance(value, (list, tuple)):
        return [_without_keys(item) for item in value]
    return value


def _sha256(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def config_fields(
    *,
    settings: Mapping[str, Any],
    runtime: Mapping[str, Any],
    prompts: Mapping[str, str],
    commit: str,
) -> dict[str, Any]:
    """Return the configuration fields of a stage key (H-09, design D39).

    Args:
        settings: The resolved settings. Every key whose name ends in
            ``api_key`` is left out at any depth, so a key never reaches the
            hash or a file.
        runtime: The plan ``runtime`` block.
        prompts: The P13 prompt template hashes, by template name.
        commit: The harness commit.

    Returns:
        One SHA-256 of the settings and one of the runtime block, the prompt
        hashes by name and the commit, under the names of :data:`CONFIG_FIELDS`.
    """
    return {
        "settings_sha256": _sha256(_without_keys(settings)),
        "runtime_sha256": _sha256(runtime),
        "prompt_sha256": dict(sorted(prompts.items())),
        "harness_commit": commit,
    }


def write_json(path: Path, value: Any) -> None:
    """Write *value* as JSON to *path* atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _differences(found: Mapping[str, Any], key: Mapping[str, Any]) -> list[str]:
    return [name for name in key if found.get(name) != key.get(name)]


def check_stage_key(folder: Path, stage: str, key: Mapping[str, Any]) -> None:
    """Refuse when an earlier start of *stage* in *folder* had another key.

    The runner calls it before it skips a stage that finished earlier, so a
    finished stage with a differing key refuses too. Nothing happens when the
    stage never started.

    Raises:
        ResumeMismatchError: The message names each differing field.
    """
    key_path = folder / f"{stage}.key.json"
    if not key_path.exists():
        return
    differ = _differences(json.loads(key_path.read_text(encoding="utf-8")), key)
    if differ:
        raise ResumeMismatchError(
            f"--resume refused: stage {stage} in {folder} started with another "
            f"{', '.join(differ)}. Use another --out-dir, or the same inputs."
        )


def check_index_config(index_dir: Path, config: Mapping[str, Any]) -> None:
    """Refuse an index whose ingest done-marker holds another configuration.

    Args:
        index_dir: The index folder that holds ``.done-ingest.json``.
        config: The :func:`config_fields` the calling stage expects of the index.

    Raises:
        ResumeMismatchError: The message names each differing field.
    """
    marker = json.loads((index_dir / ".done-ingest.json").read_text(encoding="utf-8"))
    differ = _differences(marker.get("config") or {}, config)
    if differ:
        raise ResumeMismatchError(
            f"the index in {index_dir} was built with another {', '.join(differ)}; "
            "rebuild it, or run with the configuration it was built with."
        )


class RowFile:
    """One stage's JSONL row file with its key file and done-marker.

    The object holds the stage folder's runner lock until :meth:`close`; use it
    in a ``with`` block.
    """

    def __init__(self, folder: Path, stage: str, key: Mapping[str, Any], *, resume: bool) -> None:
        """Take the runner lock, then open the stage and check the key of an earlier start.

        Raises:
            RunStop: Another runner holds ``<folder>/.lock``. Nothing was read.
            StageFileExistsError: The stage started before and *resume* is off.
            ResumeMismatchError: The earlier start had another key; the message
                names each differing field.
        """
        self.path = folder / f"{stage}.jsonl"
        self.stage = stage
        self._key = dict(key)
        self._key_path = folder / f"{stage}.key.json"
        self._done_path = folder / f".done-{stage}.json"
        self._lock = ExitStack()
        self._lock.enter_context(exclusive_lock(folder / ".lock"))
        try:
            self._open(folder, resume)
        except BaseException:
            self._lock.close()
            raise

    def _open(self, folder: Path, resume: bool) -> None:
        if self._key_path.exists():
            if not resume:
                raise StageFileExistsError(
                    f"{self.path} exists; pass --resume to continue it, or use another --out-dir"
                )
            check_stage_key(folder, self.stage, self._key)
        else:
            write_json(self._key_path, self._key)
        self._drop_partial_last_line()

    def close(self) -> None:
        """Release the runner lock."""
        self._lock.close()

    def __enter__(self) -> RowFile:
        """Return the open row file."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Release the runner lock."""
        self.close()

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
        """Write the done-marker with *payload*.

        A key with configuration fields adds them under ``config``, so a later
        stage can check the index it reads (:func:`check_index_config`).
        """
        config = {name: self._key[name] for name in CONFIG_FIELDS if name in self._key}
        write_json(self._done_path, {**payload, "config": config} if config else dict(payload))


def read_rows(path: Path) -> list[dict[str, Any]]:
    """Return the rows of a JSONL file, or an empty list when it is missing."""
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def say(text: str) -> None:
    """Print one progress line and flush it."""
    print(text, flush=True)
