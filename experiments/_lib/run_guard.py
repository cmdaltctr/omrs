"""One call that guards an Experiment 35 run before any scoring (task 2.7; tasks 5.7, 5.8).

The runner calls :func:`guard_run` once, after it starts the llama.cpp server
and before it scores anything::

    from _lib.run_guard import guard_run

    found = guard_run(EXP_DIR, block, base_url="http://127.0.0.1:9931", check_args=True)

A main stage refuses first, before it reads the server, while ``plan.json``
``frozen`` is empty or the working tree has uncommitted changes (H-18). A
pre-freeze run (``prefreeze=True``, the ``--prefreeze`` flag) and a smoke run
(``smoke=True``, a ``--qids`` run) skip both refusals.

Then the call checks the live server against the plan. A wrong build, a wrong
GGUF hash or, with ``check_args``, a wrong server argument raises
``PreflightError`` and writes nothing, so no score file and no run record
exists for a run on the wrong model. When the check passes, the call appends
one line to ``output/run-records.jsonl`` with the found runtime and the
SHA-256 of ``preregistration.md``. A pre-freeze line carries
``prefreeze: true`` and a smoke line ``smoke: true``; a main-run line leaves
both out, so a main-run check can ignore the flagged lines.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from omrs.core.experiment_records.runtime_block import RuntimeBlock

try:
    from .llamacpp_runtime import FoundRuntime, verify_llamacpp_runtime
    from .manifest import git_dirty
    from .preflight import PreflightError
    from .run_record import record_run_start
except ImportError:  # imported as top-level ``_lib`` from an experiment folder
    from _lib.llamacpp_runtime import (  # type: ignore[no-redef]
        FoundRuntime,
        verify_llamacpp_runtime,
    )
    from _lib.manifest import git_dirty  # type: ignore[no-redef]
    from _lib.preflight import PreflightError  # type: ignore[no-redef]
    from _lib.run_record import record_run_start  # type: ignore[no-redef]

__all__ = ["guard_run"]

PREREGISTRATION = "preregistration.md"


def _refuse_main_run(folder: Path) -> None:
    plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    if not plan.get("frozen"):
        raise PreflightError(
            "plan.json field frozen is empty: a main stage runs only after the freeze; "
            "pass the pre-freeze flag for a test run"
        )
    dirty = git_dirty(folder)
    if dirty is None:
        raise RuntimeError(
            f"git cannot report the commit for {folder}; run the experiment inside the repository"
        )
    if dirty:
        raise PreflightError(
            "the working tree has uncommitted changes (git_dirty): a main stage runs only "
            "from a clean commit; commit or remove the changes"
        )


def _preregistration_sha256(folder: Path) -> str | None:
    path = folder / PREREGISTRATION
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def guard_run(
    folder: Path,
    block: RuntimeBlock,
    *,
    base_url: str,
    command: str | None = None,
    check_args: bool = False,
    prefreeze: bool = False,
    smoke: bool = False,
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
        prefreeze: True for a pre-freeze run (the ``--prefreeze`` flag).
        smoke: True for a smoke run on a few questions (a ``--qids`` run).

    Returns:
        What the check found: the build and the SHA-256 of each model file.

    Raises:
        PreflightError: A main stage with an empty ``frozen`` or a dirty tree,
            or the server differs from the plan. Nothing is written.
        RuntimeError: git cannot report the commit. Nothing is written.
    """
    if not (prefreeze or smoke):
        _refuse_main_run(folder)
    found = verify_llamacpp_runtime(block, base_url=base_url, check_args=check_args)
    record_run_start(
        folder,
        command=command,
        runtime=found.as_run_record(),
        prefreeze=prefreeze,
        smoke=smoke,
        preregistration_sha256=_preregistration_sha256(folder),
    )
    return found
