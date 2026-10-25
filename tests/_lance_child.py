"""Run a short-lived Python child that writes to LanceDB (TDR-040).

lancedb < 0.40 leaves its Tokio worker threads running into interpreter
shutdown, where one can crash the process (SIGSEGV or SIGABRT) after a
successful write (lancedb PR #4175). Tests that write from a child process
use :func:`run_lance_child`. It ends the child with a marker line and
``os._exit(0)`` once the script body has finished, so a committed write is
not reported as a failure. A child that fails earlier still exits non-zero.
The leading underscore keeps pytest from collecting this file.
"""

from __future__ import annotations

import os
import subprocess
import sys

FINISHED_MARKER = "lance child finished"

# Appended to every child script. It runs only when the body has finished.
_EPILOGUE = f"""
import os as _os
import sys as _sys
print({FINISHED_MARKER!r}, flush=True)
_sys.stderr.flush()
_os._exit(0)
"""


def run_lance_child(
    script: str, *args: str, label: str, timeout: float = 120
) -> subprocess.CompletedProcess[str]:
    """Run *script* in a new interpreter and assert that it finished.

    The child runs with ``PYTHONFAULTHANDLER=1``, so a native crash prints
    each thread's Python stack. The assertion message shows stdout and
    stderr: stdout holds :data:`FINISHED_MARKER` when the body finished.

    Args:
        script: The child's Python source, run with ``python -c``.
        *args: Arguments the child reads from ``sys.argv[1:]``.
        label: Names the child in the failure message.
        timeout: Seconds before the child is killed.

    Returns:
        The completed process.
    """
    completed = subprocess.run(
        [sys.executable, "-c", script + _EPILOGUE, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "PYTHONFAULTHANDLER": "1"},
    )
    assert completed.returncode == 0, (
        f"{label} failed with exit code {completed.returncode}:\n"
        f"stdout: {completed.stdout!r}\nstderr:\n{completed.stderr}"
    )
    return completed
