"""Checks on the watcher's reaction to a signal: it detaches and the chain runs on.

A Mac shutdown or a closed terminal sends SIGTERM, SIGINT or SIGHUP. The run must carry on:
the watcher sends no ``tmux kill-session``, does no final pull, writes no ``PULLED`` and
ends with ``KEEP_POD`` and the ``--attach`` command. Only a request in the file ``STOP`` of
the results folder (made before the signal) keeps the old behaviour: stop the chain, pull,
write the verdict. The stubs of test_mac_watch35.py play the pod; the fake ``tmux`` step
``detach`` sends a bare SIGTERM and ``term`` makes the STOP file first.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from types import SimpleNamespace

import mac_watch35
import pytest
import watch_modes35
from test_mac_watch35 import POD, Session, _last
from test_watch_stages35 import LoopPod, _stage

START = "+[00:00:01] == a: start (timeout 600s)"


def _kills(s: Session) -> list[str]:
    return [x for x in s.log("tmux.log") if x.startswith("kill-session")]


def test_a_signal_without_a_stop_file_only_detaches(tmp_path: Path) -> None:
    s = Session(tmp_path, [START, "detach"])
    _stage(s)
    result = s.run()
    assert result.returncode == mac_watch35.EXIT["detached"], result.stdout + result.stderr
    assert not _kills(s)  # the chain is not stopped
    assert not (s.work / "PULLED").exists()  # no verdict
    folder = s.folder()
    assert not (folder / "test-session-out.tgz").exists()  # no final pull
    assert not (folder / "watcher-out.tgz").exists()
    assert (s.pod / "alive").exists()  # the chain still runs
    out = result.stdout
    assert "DETACHED: the chain runs on; rejoin with --attach" in out
    assert "stage tarballs pulled: 1" in out  # the summary of what it holds
    assert "RESULT end=detached outputs=not-pulled pulled-marker=not-written" in out
    assert "end=detached" in (folder / "watch-summary.txt").read_text(encoding="utf-8")
    assert "DELETE_POD_NOW" not in out
    want = ["--pod-id", POD, "--commit", s.commit, "--stages", "test_session_stages.txt"]
    line = next(x for x in out.splitlines() if "rejoin: uv run" in x)
    command = line.split("rejoin: ", 1)[1]
    words = shlex.split(command)
    assert all(a in words for a in want) and "--examples" in words and "--attach" in words
    assert _last(out_result := result).startswith(f"KEEP_POD {POD}: DETACHED")
    assert "--attach" in _last(out_result)


def test_a_signal_with_a_stop_file_stops_the_chain_pulls_and_writes_the_verdict(
    tmp_path: Path,
) -> None:
    s = Session(tmp_path, [START, "term"])  # the stub touches STOP, then sends SIGTERM
    result = s.run()
    assert result.returncode == mac_watch35.EXIT["interrupted"], result.stdout + result.stderr
    assert _kills(s) and "DETACHED" not in result.stdout
    assert (s.work / "PULLED").read_text(encoding="utf-8").strip() == "ok"
    assert "RESULT end=interrupted outputs=ok pulled-marker=written" in result.stdout
    assert _last(result) == f"DELETE_POD_NOW {POD}"


def test_a_stop_file_of_an_earlier_session_does_not_count(tmp_path: Path) -> None:
    s = Session(tmp_path, [START, "term"])
    assert s.run().returncode == mac_watch35.EXIT["interrupted"]
    assert (s.folder() / "STOP").exists()  # left by the deliberate stop
    (s.pod / "step").unlink(missing_ok=True)
    (s.pod / "alive").unlink()  # the chain of the first run is gone
    (s.pod / "steps").write_text(f"{START}\ndetach\n", encoding="utf-8")
    n = len(_kills(s))
    result = s.run("--resume")
    assert result.returncode == mac_watch35.EXIT["detached"], result.stdout + result.stderr
    assert len(_kills(s)) == n and not (s.folder() / "STOP").exists()


def test_the_exit_key_is_new_and_documented() -> None:
    codes = list(mac_watch35.EXIT.values())
    assert mac_watch35.EXIT["detached"] == 15 and len(codes) == len(set(codes))
    runbook = (Path(__file__).parent / "TEST_SESSION_RUNBOOK.md").read_text(encoding="utf-8")
    assert "| 15 |" in runbook and "touch <results folder>/STOP" in runbook


class _Raising(LoopPod):
    """A pod whose first log poll is cut by a signal."""

    def __init__(self, name: str) -> None:
        from test_watch_stages35 import Clock

        super().__init__(Clock())
        self.name = name

    def ssh(self, command: str, timeout: float = 120):  # noqa: ANN201
        if "tail -c" in command:
            raise mac_watch35.Interrupted(self.name)
        return super().ssh(command, timeout)


@pytest.mark.parametrize("name", ["SIGTERM", "SIGINT", "SIGHUP"])
@pytest.mark.parametrize("stop", [False, True])
def test_every_signal_detaches_unless_the_stop_file_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, stop: bool
) -> None:
    flag = tmp_path / "STOP"
    flag.touch() if stop else None
    monkeypatch.setattr(mac_watch35, "_stop", [flag])
    pod = _Raising(name)
    end = mac_watch35.watch(pod, mac_watch35.Watch(), 3600, 0.0)
    assert end == ("interrupted" if stop else "detached")


def test_a_signal_before_the_watch_also_detaches(monkeypatch: pytest.MonkeyPatch, capsys) -> None:  # noqa: ANN001
    def boom(_args: object) -> int:
        raise mac_watch35.Interrupted("SIGHUP")

    monkeypatch.setattr(mac_watch35, "run", boom)
    code = mac_watch35.main(["--pod-id", POD, "--commit", "c" * 40, "--examples", "x.json"])
    out = capsys.readouterr().out
    assert code == mac_watch35.EXIT["detached"]
    assert out.splitlines()[-1].startswith(f"KEEP_POD {POD}: DETACHED")


def test_the_attach_command_repeats_the_arguments() -> None:
    args = SimpleNamespace(
        pod_id=POD, commit="c" * 40, stages="verify_session_stages.txt",
        examples=Path("/x y/e.json"),
        ssh_host="203.0.113.7", ssh_port=40022, no_offsite=True, keep_pod_on_fail=True,
    )  # fmt: skip
    words = shlex.split(watch_modes35.attach_command(args))
    assert words[-1] == "--attach" or "--attach" in words
    for pair in (("--pod-id", POD), ("--stages", "verify_session_stages.txt"),
                 ("--examples", "/x y/e.json"),
                 ("--ssh-host", "203.0.113.7"), ("--ssh-port", "40022")):  # fmt: skip
        assert words[words.index(pair[0]) + 1] == pair[1]
    assert "--no-offsite" in words
    assert "--keep-pod-on-fail" in words
