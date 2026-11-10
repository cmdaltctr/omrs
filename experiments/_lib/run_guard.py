"""One call that guards an Experiment 35 run before any scoring (task 2.7).

The runner calls :func:`guard_run` once, after it starts the llama.cpp server
and before it scores anything::

    from _lib.run_guard import guard_run

    found = guard_run(EXP_DIR, block, base_url="http://127.0.0.1:9931")

The call checks the live server against the plan. A wrong build or a wrong
GGUF hash raises ``PreflightError`` and writes nothing, so no score file and no
run record exists for a run on the wrong model. When the check passes, the call
appends the run record with the found runtime.
"""

from __future__ import annotations

from pathlib import Path

from omrs.core.experiment_records.runtime_block import RuntimeBlock

try:
    from .llamacpp_runtime import FoundRuntime, verify_llamacpp_runtime
    from .run_record import record_run_start
except ImportError:  # imported as top-level ``_lib`` from an experiment folder
    from _lib.llamacpp_runtime import (  # type: ignore[no-redef]
        FoundRuntime,
        verify_llamacpp_runtime,
    )
    from _lib.run_record import record_run_start  # type: ignore[no-redef]

__all__ = ["guard_run"]


def guard_run(
    folder: Path,
    block: RuntimeBlock,
    *,
    base_url: str,
    command: str | None = None,
) -> FoundRuntime:
    """Check the live llama.cpp server, then append the run record.

    The check runs first. The run record is written only when it passes.

    Args:
        folder: The experiment folder. It must be inside a git repository.
        block: The ``runtime`` block of the experiment's ``plan.json``.
        base_url: The loopback URL of the llama.cpp server.
        command: The command that started the run. Defaults to ``sys.argv``.

    Returns:
        What the check found: the build and the SHA-256 of each model file.

    Raises:
        PreflightError: The server differs from the plan. Nothing is written.
        RuntimeError: git cannot report the commit. Nothing is written.
    """
    found = verify_llamacpp_runtime(block, base_url=base_url)
    record_run_start(folder, command=command, runtime=found.as_run_record())
    return found
