"""Lock behaviour that the lease protocol relies on (design D4).

The join and leave steps work only if shared locks coexist, if each
:class:`LockFile` is its own descriptor (so one process can probe the lock
it holds), and if a started server never inherits a lock descriptor.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from omrs.integrations.llamacpp_runtime.locks import LockFile


def test_two_shared_locks_coexist(tmp_path: Path) -> None:
    path = tmp_path / "clients.lock"
    first, second = LockFile(path), LockFile(path)
    try:
        assert first.acquire(shared=True, blocking=False)
        assert second.acquire(shared=True, blocking=False)
    finally:
        first.close()
        second.close()


def test_a_second_descriptor_of_the_same_process_sees_the_shared_lock(tmp_path: Path) -> None:
    """The leave step: drop my shared lock, then probe exclusively on a new descriptor."""
    path = tmp_path / "clients.lock"
    mine, other_client = LockFile(path), LockFile(path)
    probe = LockFile(path)
    try:
        assert mine.acquire(shared=True)
        assert other_client.acquire(shared=True)
        mine.close()
        # Another client still holds a shared lock: the probe must fail.
        assert probe.acquire(shared=False, blocking=False) is False
        other_client.close()
        # No client is left: the same probe descriptor now succeeds.
        assert probe.acquire(shared=False, blocking=False) is True
    finally:
        for lock in (mine, other_client, probe):
            lock.close()


def test_an_exclusive_lock_blocks_a_shared_attempt(tmp_path: Path) -> None:
    path = tmp_path / "start.lock"
    holder, joiner = LockFile(path), LockFile(path)
    try:
        assert holder.acquire(shared=False)
        assert joiner.acquire(shared=True, blocking=False) is False
    finally:
        holder.close()
        joiner.close()


def test_close_drops_the_lock(tmp_path: Path) -> None:
    path = tmp_path / "clients.lock"
    held, probe = LockFile(path), LockFile(path)
    try:
        assert held.acquire(shared=True)
        assert probe.acquire(shared=False, blocking=False) is False
        held.close()
        assert probe.acquire(shared=False, blocking=False) is True
    finally:
        held.close()
        probe.close()


def test_close_twice_is_harmless(tmp_path: Path) -> None:
    lock = LockFile(tmp_path / "x.lock")
    lock.close()
    lock.close()


def test_a_child_process_does_not_inherit_the_descriptor(tmp_path: Path) -> None:
    """A started server must not keep the lock alive after its starter leaves."""
    path = tmp_path / "clients.lock"
    held, probe = LockFile(path), LockFile(path)
    try:
        assert held.acquire(shared=True)
        child = subprocess.Popen(  # noqa: S603 - fixed argv, test child
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        try:
            held.close()
            assert probe.acquire(shared=False, blocking=False) is True
        finally:
            child.kill()
            child.wait(timeout=10)
    finally:
        held.close()
        probe.close()


def test_the_lock_file_is_private_to_the_owner(tmp_path: Path) -> None:
    path = tmp_path / "runtimes" / "chat" / "clients.lock"
    lock = LockFile(path)
    try:
        assert path.exists()
        assert (path.stat().st_mode & 0o777) == 0o600
        assert os.get_inheritable(lock._fd) is False
    finally:
        lock.close()
