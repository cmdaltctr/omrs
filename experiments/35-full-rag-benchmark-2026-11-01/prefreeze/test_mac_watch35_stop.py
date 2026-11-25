"""Checks on the remote stop that mac_watch35.py sends before the pull after an abnormal end.

The stubs of test_mac_watch35.py play the pod: the tmux stub writes ``kill`` and the scp
stub writes ``scp`` into one ordered log, so a test sees which came first. The unit tests
at the end use a fake pod, so no test reaches RunPod or any network host.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import watch_stop35
from test_mac_watch35 import ENDS, POD, Session, _last

ABNORMAL = ("interrupted", "idle", "wall-cap")
NORMAL = ("stop-line", "session-ended")


def _order(s: Session) -> list[str]:
    return s.log("order.log")


@pytest.mark.parametrize("end", ABNORMAL)
def test_an_abnormal_end_stops_the_chain_before_the_first_copy(tmp_path: Path, end: str) -> None:
    steps, args, code = ENDS[end]
    s = Session(tmp_path, steps)
    result = s.run(*args)
    assert result.returncode == code, result.stdout + result.stderr
    order = _order(s)
    assert order.count("kill") == 1
    pulls = [i for i, line in enumerate(order) if "test-session.log" in line]
    assert pulls and order.index("kill") < min(pulls), order  # the setup copies come before
    assert "kill-session -t exp35" in "\n".join(s.log("tmux.log"))
    assert f"RESULT end={end} outputs=ok pulled-marker=written" in result.stdout


@pytest.mark.parametrize("end", NORMAL)
def test_an_end_the_chain_made_itself_sends_no_stop(tmp_path: Path, end: str) -> None:
    steps, args, code = ENDS[end]
    s = Session(tmp_path, steps)
    assert s.run(*args).returncode == code
    assert "kill" not in _order(s)


def test_a_finished_session_sends_no_stop(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    assert s.run().returncode == 0
    assert "kill" not in _order(s)


def test_a_failed_stop_does_not_skip_the_pull(tmp_path: Path) -> None:
    s = Session(tmp_path, ENDS["idle"][0])
    (tmp_path / "tmux.kill-fails").touch()
    result = s.run()
    assert result.returncode == 8, result.stdout + result.stderr
    order = _order(s)
    assert "kill" in order and any(
        "test-session.log" in line for line in order[order.index("kill") :]
    )
    assert "RESULT end=idle outputs=ok pulled-marker=written" in result.stdout
    assert _last(result) == f"DELETE_POD_NOW {POD}"


class FakePod:
    """An SSH stand-in that answers each command from a list of return codes."""

    def __init__(self, codes: list[int | None]) -> None:
        self.codes, self.commands = codes, []

    def ssh(self, command: str, timeout: float = 120) -> subprocess.CompletedProcess[bytes] | None:
        self.commands.append((command, timeout))
        code = self.codes.pop(0) if len(self.codes) > 1 else self.codes[0]
        return None if code is None else subprocess.CompletedProcess([], code, b"", b"")


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def pause(self, seconds: float) -> None:
        self.t += seconds


def _stop(pod: FakePod, reason: str = "idle") -> tuple[Clock, list[str]]:
    clock, said = Clock(), []
    watch_stop35.stop_chain(
        pod, reason, session="exp35", tarball="/w/t.tgz", say=said.append, now=clock.now,
        pause=clock.pause,
    )  # fmt: skip
    return clock, said


def test_a_stop_that_times_out_returns_after_one_bounded_call() -> None:
    pod = FakePod([None])
    _clock, said = _stop(pod)
    assert len(pod.commands) == 1 and pod.commands[0][1] <= watch_stop35.STOP_SSH_S
    assert any("pulling anyway" in line for line in said)


def test_a_chain_that_never_finishes_ends_the_wait_at_the_limit() -> None:
    pod = FakePod([0, 1])  # the stop is sent; the hash file never appears
    clock, said = _stop(pod)
    assert clock.t >= watch_stop35.DRAIN_S
    assert len(pod.commands) <= 2 + watch_stop35.DRAIN_S // watch_stop35.DRAIN_STEP_S
    assert any("pulling anyway" in line for line in said)


def test_a_finished_chain_ends_the_wait_at_once() -> None:
    pod = FakePod([0, 0])
    clock, _said = _stop(pod)
    assert clock.t == 0 and len(pod.commands) == 2


def test_a_lost_connection_ends_the_wait_at_once() -> None:
    pod = FakePod([0, 255])
    clock, _said = _stop(pod)
    assert clock.t == 0 and len(pod.commands) == 2


@pytest.mark.parametrize("reason", ["done", "stop-line", "session-ended", "ssh-lost"])
def test_other_ends_send_nothing(reason: str) -> None:
    pod = FakePod([0])
    _stop(pod, reason)
    assert pod.commands == []
