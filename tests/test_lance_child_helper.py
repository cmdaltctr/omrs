"""Tests for the short-lived LanceDB child runner (``tests/_lance_child.py``)."""

from __future__ import annotations

import pytest
from tests._lance_child import FINISHED_MARKER, run_lance_child

# Registers a handler that crashes the interpreter during shutdown, like a
# lancedb < 0.40 worker thread that wakes during finalisation (TDR-040).
_CRASH_AT_SHUTDOWN = """
import atexit, ctypes
atexit.register(lambda: ctypes.string_at(0))
print("body done", flush=True)
"""


def test_a_finished_child_passes_and_prints_the_marker() -> None:
    """A child whose body finishes passes, and stdout ends with the marker."""
    completed = run_lance_child("import sys\nprint(sys.argv[1])", "hello", label="echo child")
    assert completed.stdout.splitlines() == ["hello", FINISHED_MARKER]


def test_a_crash_at_shutdown_after_the_body_does_not_fail() -> None:
    """The runner skips interpreter shutdown once the body has finished."""
    completed = run_lance_child(_CRASH_AT_SHUTDOWN, label="shutdown crash child")
    assert FINISHED_MARKER in completed.stdout


def test_the_shutdown_crash_is_real_without_the_runner() -> None:
    """Without the runner the same child dies with a signal (guards the test above)."""
    import subprocess
    import sys

    completed = subprocess.run(
        [sys.executable, "-c", _CRASH_AT_SHUTDOWN], capture_output=True, text=True, timeout=60
    )
    assert completed.returncode < 0


def test_a_child_that_raises_fails_with_its_stderr() -> None:
    """A body that fails exits non-zero, and the message shows its stderr."""
    with pytest.raises(AssertionError) as caught:
        run_lance_child("raise SystemExit('bad phase')", label="failing child")
    message = str(caught.value)
    assert "failing child failed with exit code 1" in message
    assert "bad phase" in message
    assert FINISHED_MARKER not in message


def test_a_crash_in_the_body_fails_with_a_python_stack() -> None:
    """A native crash before the marker fails and shows the faulthandler stack."""
    with pytest.raises(AssertionError) as caught:
        run_lance_child("import ctypes\nctypes.string_at(0)", label="crashing child")
    message = str(caught.value)
    assert "Fatal Python error" in message
    assert FINISHED_MARKER not in message
