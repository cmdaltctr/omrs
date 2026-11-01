"""The ``flock`` helpers of the shared runtime manager (design D4).

Each :class:`LockFile` owns one descriptor, so a lease can hold its shared
``clients.lock`` on one descriptor while another descriptor probes the same
file exclusively. Kernel locks free themselves when a process dies, which is
what makes the lease safe against SIGKILL.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from omrs.integrations.llamacpp_runtime.locks import LockFile

CHILD = """
import sys, time
sys.path.insert(0, {root!r})
from omrs.integrations.llamacpp_runtime.locks import LockFile
lock = LockFile(sys.argv[1])
assert lock.acquire(shared=True)
print("held", flush=True)
time.sleep(120)
"""

ROOT = str(__import__("pathlib").Path(__file__).resolve().parents[1])


def _child(path: Path) -> subprocess.Popen:
    return subprocess.Popen(  # noqa: S603 - test child, fixed code
        [sys.executable, "-c", CHILD.format(root=ROOT), str(path)],
        stdout=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )


def _wait_held(proc: subprocess.Popen, seconds: float = 10.0) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        line = proc.stdout.readline() if proc.stdout else ""
        if line.strip() == "held":
            return
        time.sleep(0.05)
    raise AssertionError("the child never held its lock")


def test_a_shared_lock_in_a_child_blocks_a_non_blocking_exclusive_attempt(
    tmp_path: Path,
) -> None:
    path = tmp_path / "clients.lock"
    child = _child(path)
    try:
        _wait_held(child)
        # A broken acquire that ignores the non-blocking flag would hang this
        # process, so the attempt runs in a thread with its own deadline.
        probe = LockFile(path)
        outcome: dict[str, object] = {}

        def attempt() -> None:
            outcome["value"] = probe.acquire(shared=False, blocking=False)

        thread = threading.Thread(target=attempt, daemon=True)
        thread.start()
        thread.join(timeout=5)
        assert not thread.is_alive(), "acquire blocked although blocking=False"
        assert outcome["value"] is False
        probe.close()
    finally:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=10)


def test_the_lock_frees_when_the_child_is_killed(tmp_path: Path) -> None:
    path = tmp_path / "clients.lock"
    child = _child(path)
    _wait_held(child)
    os.killpg(child.pid, signal.SIGKILL)
    child.wait(timeout=10)
    probe = LockFile(path)
    try:
        assert probe.acquire(shared=False, blocking=False)
    finally:
        probe.close()


def test_release_allows_the_next_acquisition(tmp_path: Path) -> None:
    path = tmp_path / "start.lock"
    lock = LockFile(path)
    assert lock.acquire(shared=False, blocking=False)
    lock.release()
    again = LockFile(path)
    try:
        assert again.acquire(shared=False, blocking=False)
    finally:
        again.close()
    lock.close()


def test_a_blocking_exclusive_acquire_waits_for_the_holder(tmp_path: Path) -> None:
    path = tmp_path / "request.lock"
    holder = LockFile(path)
    assert holder.acquire(shared=False, blocking=False)
    waiter = LockFile(path)
    begun = time.monotonic()
    try:
        # A blocking call in this process would deadlock the test, so prove
        # the wait with a short-lived blocking child instead.
        child = subprocess.Popen(  # noqa: S603 - test child, fixed code
            [
                sys.executable,
                "-c",
                CHILD.format(root=ROOT).replace("shared=True", "shared=False"),
                str(path),
            ],
            stdout=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        time.sleep(0.5)
        assert child.poll() is None, "the child must still wait"
        holder.release()
        _wait_held(child, seconds=5)
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=10)
        assert time.monotonic() - begun >= 0.5
    finally:
        holder.close()
        waiter.close()


def test_windows_reports_not_supported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from omrs.integrations.llamacpp_runtime import locks

    monkeypatch.setattr(locks, "LOCKS_SUPPORTED", False)
    lock = LockFile(tmp_path / "clients.lock")
    with pytest.raises(locks.LockNotSupportedError):
        lock.acquire(shared=True)
