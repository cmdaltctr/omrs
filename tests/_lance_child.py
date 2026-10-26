"""Run a short-lived Python child that writes to LanceDB (TDR-040, ADR-098).

lancedb 0.40.0 and later shut their runtime down at interpreter exit (lancedb
PR #4175). Older releases left worker threads running into shutdown, where one
could crash the process after a successful write. The child now runs normal
interpreter shutdown, so a crash at exit fails the test. The script body ends
with a marker line on stdout, which shows whether the body finished before a
crash. ``PYTHONFAULTHANDLER=1`` makes a native crash print each thread's
Python stack. The leading underscore keeps pytest from collecting this file.
"""

from __future__ import annotations

import os
import subprocess
import sys

FINISHED_MARKER = "lance child finished"

# Appended to every child script. It runs only when the body has finished.
# Interpreter shutdown follows it as normal.
_EPILOGUE = f"""
import sys as _sys
print({FINISHED_MARKER!r}, flush=True)
_sys.stderr.flush()
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
