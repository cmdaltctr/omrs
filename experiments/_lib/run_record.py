"""Append a run record when an experiment run starts (experiment-format-v1, D8).

Call :func:`record_run_start` once at the top of a runner, before any work::

    from _lib.run_record import record_run_start

    record_run_start(Path(__file__).resolve().parent)

It reads the git commit and the dirty-tree flag with ``git`` (through the
helpers in ``_lib.manifest``), then calls the pure core function
``omrs.core.experiment_records.run_record.append_run_record``, which appends
one line to ``output/run-records.jsonl``.

A run that checked a llama.cpp server passes what the check found, so the
line holds the build and the SHA-256 of each model file::

    found = verify_llamacpp_runtime(block, base_url="http://127.0.0.1:9931")
    record_run_start(folder, runtime=found.as_run_record())
"""

from __future__ import annotations

import shlex
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from omrs.core.experiment_records.run_record import RunRecord, append_run_record

try:
    from .manifest import git_commit, git_dirty
except ImportError:  # imported as top-level ``_lib`` from an experiment folder
    from _lib.manifest import git_commit, git_dirty  # type: ignore[no-redef]


def record_run_start(
    folder: Path,
    *,
    command: str | None = None,
    runtime: Mapping[str, Any] | None = None,
) -> RunRecord:
    """Append a run record for the experiment in *folder*.

    Args:
        folder: The experiment folder. It must be inside a git repository.
        command: The command that started the run. Defaults to ``sys.argv``,
            quoted for a shell.
        runtime: The value of ``FoundRuntime.as_run_record()`` from the
            live-server check (``_lib.llamacpp_runtime``). None leaves the
            ``runtime`` key out of the line.

    Returns:
        The record that was written.

    Raises:
        RuntimeError: git cannot report the commit or the working-tree state.
            Nothing is written.
    """
    commit = git_commit(folder)
    dirty = git_dirty(folder)
    if commit is None or dirty is None:
        raise RuntimeError(
            f"git cannot report the commit for {folder}; run the experiment inside the repository"
        )
    if command is None:
        command = shlex.join(sys.argv)
    return append_run_record(
        folder, git_commit=commit, git_dirty=dirty, command=command, runtime=runtime
    )
