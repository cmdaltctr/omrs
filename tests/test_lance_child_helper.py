"""Tests for the short-lived LanceDB child runner (``tests/_lance_child.py``)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests._lance_child import FINISHED_MARKER, run_lance_child

# Registers a handler that crashes the interpreter during shutdown, like a
# lancedb < 0.40 worker thread that woke during finalisation (TDR-040). The
# child now runs normal shutdown, so this crash must fail the run.
_CRASH_AT_SHUTDOWN = """
import atexit, ctypes
atexit.register(lambda: ctypes.string_at(0))
print("body done", flush=True)
"""


def test_a_finished_child_passes_and_prints_the_marker() -> None:
    """A child whose body finishes passes, and stdout ends with the marker."""
    completed = run_lance_child("import sys\nprint(sys.argv[1])", "hello", label="echo child")
    assert completed.stdout.splitlines() == ["hello", FINISHED_MARKER]


def test_the_child_runs_its_exit_handlers() -> None:
    """The child runs normal interpreter shutdown, so its atexit handlers run."""
    script = "import atexit\natexit.register(lambda: print('exit handlers ran', flush=True))"
    completed = run_lance_child(script, label="atexit child")
    assert "exit handlers ran" in completed.stdout.splitlines()


def test_a_crash_at_shutdown_fails_the_run() -> None:
    """A crash in an atexit handler fails the run after the marker, with a Python stack."""
    with pytest.raises(AssertionError) as caught:
        run_lance_child(_CRASH_AT_SHUTDOWN, label="shutdown crash child")
    message = str(caught.value)
    assert FINISHED_MARKER in message
    assert "Fatal Python error" in message


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


# A short LanceDB write: create a table, add a row, merge schema metadata the
# way core/vectordb/lancedb/meta.py does. It reads the folder from argv.
_LANCE_WRITE = """
import sys
import lancedb
db = lancedb.connect(sys.argv[1])
table = db.create_table("t", data=[{"id": "a", "vector": [0.1, 0.2]}])
table.add([{"id": "b", "vector": [0.3, 0.4]}])
table.to_lance().update_schema_metadata({"k": "v"}, replace=False)
"""


def test_a_lance_write_child_exits_cleanly_twenty_times(tmp_path: Path) -> None:
    """Twenty short LanceDB write children each finish and exit 0 through shutdown."""
    for run in range(20):
        folder = tmp_path / f"run-{run}"
        completed = run_lance_child(_LANCE_WRITE, str(folder), label=f"lance write child {run}")
        assert completed.stdout.splitlines()[-1] == FINISHED_MARKER
