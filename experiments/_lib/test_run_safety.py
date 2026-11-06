"""Tests for ``_lib.run_safety`` (issue #171 points 1, 2, 5 and 6).

uv run --no-sync pytest experiments/_lib -q
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib.run_safety import (  # noqa: E402
    RunStop,
    check_free_memory,
    exclusive_lock,
    free_memory_percent,
    parse_free_memory_percent,
    population_gaps,
    start_until_ready,
)

SLEEPER = [sys.executable, "-c", "import time; time.sleep(120)"]


def _gone(pid: int) -> bool:
    """True when no process with *pid* runs (a zombie child was reaped by wait)."""
    out = subprocess.run(["ps", "-p", str(pid)], capture_output=True, text=True, check=False)
    return str(pid) not in out.stdout


# ---------------------------------------------------------------- point 6: lock


def test_second_lock_on_the_same_checkpoint_stops(tmp_path: Path) -> None:
    lock = tmp_path / "scores.lock"
    with exclusive_lock(lock):
        with pytest.raises(RunStop, match="another runner"):
            with exclusive_lock(lock):
                pass


def test_lock_is_free_again_after_the_block(tmp_path: Path) -> None:
    lock = tmp_path / "sub" / "scores.lock"
    with exclusive_lock(lock):
        pass
    with exclusive_lock(lock) as held:
        assert held == lock


# ---------------------------------------------------------------- point 5: child server


def test_child_is_stopped_when_the_readiness_check_raises(tmp_path: Path) -> None:
    started: list[subprocess.Popen] = []
    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):
        started.append(real_popen(*args, **kwargs))
        return started[-1]

    def broken_ready() -> bool:
        raise RuntimeError("health reply was not JSON")

    subprocess.Popen = recording_popen  # type: ignore[misc]
    try:
        with pytest.raises(RuntimeError, match="not JSON"):
            start_until_ready(
                SLEEPER,
                ready=broken_ready,
                log_path=tmp_path / "s.log",
                poll_seconds=0.05,
                grace_seconds=5,
            )
    finally:
        subprocess.Popen = real_popen  # type: ignore[misc]
    assert started and started[0].poll() is not None
    assert _gone(started[0].pid)


def test_child_is_stopped_on_timeout(tmp_path: Path) -> None:
    started: list[subprocess.Popen] = []
    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):
        started.append(real_popen(*args, **kwargs))
        return started[-1]

    subprocess.Popen = recording_popen  # type: ignore[misc]
    try:
        with pytest.raises(RunStop, match="not ready"):
            start_until_ready(
                SLEEPER,
                ready=lambda: False,
                log_path=tmp_path / "s.log",
                timeout_seconds=0.3,
                poll_seconds=0.05,
                grace_seconds=5,
            )
    finally:
        subprocess.Popen = real_popen  # type: ignore[misc]
    assert started[0].poll() is not None


def test_ready_child_is_returned_running(tmp_path: Path) -> None:
    calls = iter([OSError("refused"), True])

    def ready() -> bool:
        value = next(calls)
        if isinstance(value, Exception):
            raise value
        return value

    process = start_until_ready(
        SLEEPER, ready=ready, log_path=tmp_path / "s.log", poll_seconds=0.01
    )
    try:
        assert process.poll() is None
    finally:
        process.kill()
        process.wait()


def test_child_that_exits_early_stops_the_run(tmp_path: Path) -> None:
    command = [sys.executable, "-c", "raise SystemExit(3)"]
    start = time.monotonic()
    with pytest.raises(RunStop, match="code 3"):
        start_until_ready(
            command, ready=lambda: False, log_path=tmp_path / "s.log", poll_seconds=0.05
        )
    assert time.monotonic() - start < 30


# ---------------------------------------------------------------- point 1: populations


def test_complete_populations_give_no_reason() -> None:
    expected = {"junk": {("a", 1)}, "healthy": {("a", 2), ("b", 1)}}
    assert population_gaps(expected, expected) == []


def test_missing_and_failed_items_are_named() -> None:
    expected = {"junk": {("a", 1), ("a", 3)}, "healthy": {("a", 2)}}
    scored = {"junk": {("a", 1)}, "healthy": {("a", 2)}}
    failed = {"healthy": {("a", 2)}}
    reasons = population_gaps(expected, scored, failed)
    assert reasons == [
        "population junk: 1 of 2 items have no score",
        "population healthy: 1 of 1 items failed",
    ]


def test_empty_population_is_a_gap() -> None:
    assert population_gaps({"junk": set()}, {}) == ["population junk is empty"]


# ---------------------------------------------------------------- point 2: memory


def test_free_percentage_is_read() -> None:
    assert parse_free_memory_percent("System-wide memory free percentage: 42%\n") == 42


@pytest.mark.parametrize("text", ["", "memory_pressure: command output changed\n"])
def test_output_without_a_percentage_stops(text: str) -> None:
    with pytest.raises(RunStop, match="no free percentage"):
        parse_free_memory_percent(text)


def test_failed_tool_stops() -> None:
    def failing(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

    with pytest.raises(RunStop, match="exited"):
        free_memory_percent(run=failing)


def test_low_memory_stops() -> None:
    with pytest.raises(RunStop, match="under 15%"):
        check_free_memory(15, read=lambda: 9)
    assert check_free_memory(15, read=lambda: 40) == 40
