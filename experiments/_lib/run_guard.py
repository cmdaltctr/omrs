"""One call that guards an Experiment 35 run before any scoring (task 2.7; tasks 5.7, 5.8).

The runner calls :func:`guard_run` once, after it starts the llama.cpp server
and before it scores anything::

    from _lib.run_guard import guard_run

    found = guard_run(EXP_DIR, block, base_url="http://127.0.0.1:9931", check_args=True)

A main stage refuses first, before it reads the server, while ``plan.json``
``frozen`` is empty or the working tree has uncommitted changes (H-18). A
pre-freeze run passes ``prefreeze_dir``: it skips both refusals and writes its
run record to ``<prefreeze_dir>/run-records.jsonl``, never to
``output/run-records.jsonl``. That record also holds the SHA-256 of
``preregistration.md``.

Then the call checks the live server against the plan. A wrong build, a wrong
GGUF hash or, with ``check_args``, a wrong server argument raises
``PreflightError`` and writes nothing, so no score file and no run record
exists for a run on the wrong model. When the check passes, the call appends
the run record with the found runtime.
"""

from __future__ import annotations

import hashlib
import json
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path

from omrs.core.experiment_records.run_record import (
    RUN_RECORD_FORMAT,
    RUN_RECORDS_FILE,
    RunRecord,
    RunRuntime,
    plan_sha256,
)
from omrs.core.experiment_records.runtime_block import RuntimeBlock

try:
    from .llamacpp_runtime import FoundRuntime, verify_llamacpp_runtime
    from .manifest import git_commit, git_dirty
    from .preflight import PreflightError
    from .run_record import record_run_start
except ImportError:  # imported as top-level ``_lib`` from an experiment folder
    from _lib.llamacpp_runtime import (  # type: ignore[no-redef]
        FoundRuntime,
        verify_llamacpp_runtime,
    )
    from _lib.manifest import git_commit, git_dirty  # type: ignore[no-redef]
    from _lib.preflight import PreflightError  # type: ignore[no-redef]
    from _lib.run_record import record_run_start  # type: ignore[no-redef]

__all__ = ["guard_run"]

PREREGISTRATION = "preregistration.md"


def _git_facts(folder: Path) -> tuple[str, bool]:
    commit, dirty = git_commit(folder), git_dirty(folder)
    if commit is None or dirty is None:
        raise RuntimeError(
            f"git cannot report the commit for {folder}; run the experiment inside the repository"
        )
    return commit, dirty


def _refuse_main_run(folder: Path) -> None:
    plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    if not plan.get("frozen"):
        raise PreflightError(
            "plan.json field frozen is empty: a main stage runs only after the freeze; "
            "pass the pre-freeze flag for a test run"
        )
    if _git_facts(folder)[1]:
        raise PreflightError(
            "the working tree has uncommitted changes (git_dirty): a main stage runs only "
            "from a clean commit; commit or remove the changes"
        )


def _prefreeze_record(
    folder: Path, out_dir: Path, command: str | None, found: FoundRuntime
) -> None:
    commit, dirty = _git_facts(folder)
    record = RunRecord(
        format=RUN_RECORD_FORMAT,
        started_at=datetime.now(UTC),
        git_commit=commit,
        git_dirty=dirty,
        plan_sha256=plan_sha256(folder),
        command=command if command is not None else shlex.join(sys.argv),
        runtime=RunRuntime.model_validate(found.as_run_record()),
    )
    prereg = folder / PREREGISTRATION
    line = {
        **record.model_dump(mode="json"),
        "preregistration_sha256": (
            hashlib.sha256(prereg.read_bytes()).hexdigest() if prereg.is_file() else ""
        ),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / RUN_RECORDS_FILE).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False) + "\n")


def guard_run(
    folder: Path,
    block: RuntimeBlock,
    *,
    base_url: str,
    command: str | None = None,
    check_args: bool = False,
    prefreeze_dir: Path | None = None,
) -> FoundRuntime:
    """Refuse an unfrozen or dirty main run, check the live llama.cpp server, then record the run.

    The checks run first. The run record is written only when they pass.

    Args:
        folder: The experiment folder. It must be inside a git repository.
        block: The ``runtime`` block of the experiment's ``plan.json``.
        base_url: The loopback URL of the llama.cpp server.
        command: The command that started the run. Defaults to ``sys.argv``.
        check_args: Also compare the planned server arguments with the
            router's (passed to ``verify_llamacpp_runtime``). Experiment 35
            passes True.
        prefreeze_dir: Set for a pre-freeze run (the ``--prefreeze`` flag):
            the folder of its own run record. None for a main stage.

    Returns:
        What the check found: the build and the SHA-256 of each model file.

    Raises:
        PreflightError: A main stage with an empty ``frozen`` or a dirty tree,
            or the server differs from the plan. Nothing is written.
        RuntimeError: git cannot report the commit. Nothing is written.
    """
    if prefreeze_dir is None:
        _refuse_main_run(folder)
    found = verify_llamacpp_runtime(block, base_url=base_url, check_args=check_args)
    if prefreeze_dir is not None:
        _prefreeze_record(folder, prefreeze_dir, command, found)
        return found
    record_run_start(folder, command=command, runtime=found.as_run_record())
    return found
