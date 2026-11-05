"""Run-safety helpers for experiment runners (issue #171, Experiment 47).

These helpers close four gaps that the review of the Experiment 43 harness
found. They are new functions: no existing ``_lib`` function changes.

- :func:`exclusive_lock` takes an exclusive lock before a runner reads its
  checkpoint, so two runners cannot both resume the same run.
- :func:`start_until_ready` starts a child server and stops it when startup
  fails before the readiness check passes, so no child process is left behind.
- :func:`population_gaps` names every scored population that is incomplete,
  so an analysis can withhold its verdict.
- :func:`parse_free_memory_percent` stops the run when ``memory_pressure``
  prints no percentage, instead of reading the missing value as "free".

Standard library only. A stop raises :class:`RunStop`, a ``SystemExit``, so a
runner ends with the message and a non-zero exit code.
"""

from __future__ import annotations

import fcntl
import os
import re
import subprocess
import time
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

__all__ = [
    "RunStop",
    "check_free_memory",
    "exclusive_lock",
    "free_memory_percent",
    "parse_free_memory_percent",
    "population_gaps",
    "start_until_ready",
    "stop_child",
]

_FREE_PERCENT = re.compile(r"free percentage:\s*(\d+)%")
MEMORY_PRESSURE = "/usr/bin/memory_pressure"


class RunStop(SystemExit):
    """A planned stop: the runner ends with this message and exit code 1."""


@contextmanager
def exclusive_lock(lock_path: Path) -> Iterator[Path]:
    """Hold an exclusive, non-blocking lock on *lock_path* for the ``with`` block.

    Take the lock before the checkpoint is read. A second runner then stops
    before it reads a checkpoint that the first runner is about to replace.

    Args:
        lock_path: The lock file. Its folder is created when missing.

    Yields:
        The lock path.

    Raises:
        RunStop: Another open file already holds the lock.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RunStop(f"another runner holds {lock_path.name}: stop") from None
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")
        handle.flush()
        try:
            yield lock_path
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def stop_child(process: subprocess.Popen, grace_seconds: float = 60.0) -> None:
    """Stop *process*: terminate, wait up to *grace_seconds*, then kill."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=grace_seconds)


def start_until_ready(
    command: Sequence[str],
    *,
    ready: Callable[[], bool],
    log_path: Path,
    timeout_seconds: float = 600.0,
    poll_seconds: float = 2.0,
    grace_seconds: float = 60.0,
) -> subprocess.Popen:
    """Start *command* and return the process once *ready* returns True.

    Every failure before *ready* passes stops the child first: the child
    exits, the deadline passes, *ready* raises an error that is not an
    ``OSError``, or the runner is interrupted. An ``OSError`` from *ready*
    means "not yet" (the port is not open).

    Args:
        command: The program and its arguments.
        ready: Returns True when the child serves requests.
        log_path: The child's standard output and error go here.
        timeout_seconds: The longest wait for *ready*.
        poll_seconds: The wait between two readiness checks.
        grace_seconds: The wait after ``terminate`` before ``kill``.

    Returns:
        The running process.

    Raises:
        RunStop: The child exited or the deadline passed.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as handle:
        process = subprocess.Popen(list(command), stdout=handle, stderr=subprocess.STDOUT)  # noqa: S603
    try:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RunStop(f"{Path(command[0]).name} exited with code {process.returncode}")
            try:
                if ready():
                    return process
            except OSError:
                pass
            time.sleep(poll_seconds)
        raise RunStop(f"{Path(command[0]).name} was not ready in {timeout_seconds:.0f} s")
    except BaseException:
        stop_child(process, grace_seconds)
        raise


def population_gaps(
    expected: Mapping[str, set[Any]],
    scored: Mapping[str, set[Any]],
    failed: Mapping[str, set[Any]] | None = None,
) -> list[str]:
    """Return one reason for each scored population that is not complete.

    A population is complete when it is not empty, every expected item has a
    score and no expected item is listed as failed. An analysis that gets any
    reason back withholds its verdict.

    Args:
        expected: Population name to the items the plan says it holds.
        scored: Population name to the items that have a score.
        failed: Population name to the items whose last attempt failed.

    Returns:
        The reasons, in population order. An empty list means complete.
    """
    reasons = []
    for name, items in expected.items():
        if not items:
            reasons.append(f"population {name} is empty")
            continue
        missing = items - scored.get(name, set())
        broken = items & (failed or {}).get(name, set())
        if missing:
            reasons.append(f"population {name}: {len(missing)} of {len(items)} items have no score")
        if broken:
            reasons.append(f"population {name}: {len(broken)} of {len(items)} items failed")
    return reasons


def parse_free_memory_percent(text: str) -> int:
    """Return the free memory percentage from ``memory_pressure -Q`` output.

    Raises:
        RunStop: The output holds no percentage. A missing value never counts
            as free memory.
    """
    match = _FREE_PERCENT.search(text)
    if match is None:
        raise RunStop("memory_pressure printed no free percentage: stop")
    return int(match.group(1))


def free_memory_percent(run: Callable[..., Any] = subprocess.run) -> int:
    """Run ``memory_pressure -Q`` (macOS) and return the free percentage.

    Raises:
        RunStop: The tool is missing, fails or prints no percentage.
    """
    try:
        out = run([MEMORY_PRESSURE, "-Q"], capture_output=True, text=True, check=False)
    except OSError:
        raise RunStop("memory_pressure cannot run: stop") from None
    if out.returncode:
        raise RunStop(f"memory_pressure exited with code {out.returncode}: stop")
    return parse_free_memory_percent(out.stdout)


def check_free_memory(minimum: int, read: Callable[[], int] = free_memory_percent) -> int:
    """Stop when free memory is under *minimum* percent; return the reading."""
    free = read()
    if free < minimum:
        raise RunStop(f"free memory {free}% is under {minimum}%: stop")
    return free
