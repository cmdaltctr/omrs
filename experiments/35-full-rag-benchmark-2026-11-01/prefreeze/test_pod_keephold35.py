"""Checks on the keep hold of pod_test_session.sh: a kept pod must not bill for ever.

After a POD_KEPT line the chain waits up to KEEP_HOLD_MIN minutes for the Mac, then stops
the pod (stop only: the /workspace volume and the R2 copies stay). The Mac takes over when
it writes HOLD_RELEASED (the watcher does this before a relaunch) or rewrites session.env.
The runs use the stub commands of test_pod_test_session_script.py plus a stub ``sleep``
that counts its calls and can play the Mac: no test reaches RunPod.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import mac_watch35
import pytest
import watch_stages35
from test_mac_watch35 import Session
from test_pod_test_session_script import _lines, _run

FAILING = "first false\nsecond true\n"
HOLD = (
    "POD_KEPT: holding up to {n} min for the Mac, then the pod stops itself"
    " (the volume and R2 copies stay)"
)
TIMEOUT = "POD_KEPT: no Mac after {n} min: stopping the pod"
TOOK_OVER = "POD_KEPT: the Mac took over"
# The stub counts its calls. It writes the pull verdict after STUB_PULLED_AFTER calls and plays
# the Mac after STUB_RELEASE_AFTER calls: a HOLD_RELEASED file, or a new session.env.
_SLEEP = """#!/usr/bin/env bash
n=$(( $(cat "@T@/sleeps" 2>/dev/null || echo 0) + 1 )); echo "$n" > "@T@/sleeps"
[ "$n" -ge "${STUB_PULLED_AFTER:-999}" ] && echo "${STUB_VERDICT-ok}" > "@T@/work/PULLED"
if [ "$n" -ge "${STUB_RELEASE_AFTER:-999}" ]; then
  case "${STUB_RELEASE:-}" in
    file) : > "@T@/work/HOLD_RELEASED" ;;
    env) touch -t 203001010000 "@T@/work/session.env" ;;
  esac
fi
exit 0
"""


def _hold_run(tmp_path: Path, stages: str = FAILING, **env: str | None):  # noqa: ANN202
    """Run the chain with the counting sleep stub ahead of the real one."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "sleep").write_text(_SLEEP.replace("@T@", str(tmp_path)), encoding="utf-8")
    (bin_dir / "sleep").chmod(0o755)
    env.setdefault("KEEP_POD_ON_FAIL", "1")
    env.setdefault("PULL_POLL_S", "30")
    return _run(tmp_path, stages, **env)


def _sleeps(tmp_path: Path) -> int:
    path = tmp_path / "sleeps"
    return int(path.read_text()) if path.exists() else 0


def _stops(log: Path) -> list[str]:
    return [x.split(" tarball=")[0] for x in _lines(log)]


def test_a_failed_stage_with_keep_pod_on_fail_holds_then_stops_the_pod(tmp_path: Path) -> None:
    result, log = _hold_run(tmp_path, KEEP_HOLD_MIN="1")
    out = result.stdout
    assert HOLD.format(n=1) in out and TIMEOUT.format(n=1) in out
    assert out.index(HOLD.format(n=1)) < out.index(TIMEOUT.format(n=1))
    assert out.index(TIMEOUT.format(n=1)) < out.index("pod stop sent with: runpodctl pod stop")
    assert _sleeps(tmp_path) == 2  # 1 min at 30 s a poll
    assert _stops(log) == ["pod stop pod123"]  # stop only: no terminate, no delete
    assert not (tmp_path / "curl.log").exists()
    assert result.returncode == 1  # a stage failed


def test_an_unverified_pull_holds_then_stops_the_pod(tmp_path: Path) -> None:
    result, log = _hold_run(
        tmp_path,
        "only true\n",
        KEEP_POD_ON_FAIL=None,
        KEEP_HOLD_MIN="1",
        STOP_GRACE_MIN="1",
        STUB_PULLED_AFTER="1",
        STUB_VERDICT="hash-mismatch",
    )
    out = result.stdout
    assert "POD_KEPT: the Mac's copy is not verified (hash-mismatch)" in out
    assert HOLD.format(n=1) in out and TIMEOUT.format(n=1) in out
    assert _sleeps(tmp_path) == 3  # one wait for the Mac, then the 2 polls of the hold
    assert _stops(log) == ["pod stop pod123"]
    assert result.returncode == 0


def test_a_verified_pull_does_not_hold(tmp_path: Path) -> None:
    result, log = _hold_run(
        tmp_path,
        "only true\n",
        KEEP_POD_ON_FAIL=None,
        KEEP_HOLD_MIN="1",
        STOP_GRACE_MIN="1",
        STUB_PULLED_AFTER="1",
    )
    assert "POD_KEPT" not in result.stdout and _sleeps(tmp_path) == 1
    assert _stops(log) == ["pod stop pod123"]


def test_keep_hold_min_zero_keeps_the_pod_with_no_wait_and_no_stop(tmp_path: Path) -> None:
    result, log = _hold_run(tmp_path, KEEP_HOLD_MIN="0")
    assert "POD_KEPT: failed stages: first;" in result.stdout
    assert "holding up to" not in result.stdout and "no Mac after" not in result.stdout
    assert _sleeps(tmp_path) == 0
    assert not log.exists() and not (tmp_path / "curl.log").exists()
    assert result.returncode == 1


def test_the_default_hold_is_120_minutes(tmp_path: Path) -> None:
    result, log = _hold_run(tmp_path, KEEP_HOLD_MIN=None, PULL_POLL_S="60")
    assert HOLD.format(n=120) in result.stdout and TIMEOUT.format(n=120) in result.stdout
    assert _sleeps(tmp_path) == 120
    assert _stops(log) == ["pod stop pod123"]


@pytest.mark.parametrize("kind", ["file", "env"])
def test_a_take_over_during_the_hold_ends_it_with_no_stop(tmp_path: Path, kind: str) -> None:
    result, log = _hold_run(tmp_path, KEEP_HOLD_MIN="10", STUB_RELEASE_AFTER="2", STUB_RELEASE=kind)
    assert HOLD.format(n=10) in result.stdout and TOOK_OVER in result.stdout
    assert "no Mac after" not in result.stdout
    assert _sleeps(tmp_path) == 2  # it left the hold at the poll after the Mac's signal
    assert not log.exists() and not (tmp_path / "curl.log").exists()
    assert not (tmp_path / "work" / "HOLDING").exists()  # the marker goes with the hold
    assert result.returncode == 1


def test_a_stale_release_marker_from_an_earlier_launch_does_not_end_the_next_hold(
    tmp_path: Path,
) -> None:
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "HOLD_RELEASED").write_text("", encoding="utf-8")
    result, log = _hold_run(tmp_path, KEEP_HOLD_MIN="1")
    assert TIMEOUT.format(n=1) in result.stdout and TOOK_OVER not in result.stdout
    assert _stops(log) == ["pod stop pod123"]


def test_the_holding_marker_exists_while_the_chain_holds(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "sleep").write_text(
        f'#!/usr/bin/env bash\nls "{tmp_path}/work" | grep -x HOLDING >> "{tmp_path}/seen"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    (bin_dir / "sleep").chmod(0o755)
    result, _ = _run(tmp_path, FAILING, KEEP_POD_ON_FAIL="1", KEEP_HOLD_MIN="1", PULL_POLL_S="30")
    assert _lines(tmp_path / "seen") == ["HOLDING", "HOLDING"], result.stdout
    assert not (tmp_path / "work" / "HOLDING").exists()


def test_a_clean_run_is_unchanged_by_the_hold(tmp_path: Path) -> None:
    result, log = _hold_run(tmp_path, "only true\n", KEEP_HOLD_MIN="5")
    assert result.returncode == 0
    assert "POD_KEPT" not in result.stdout and "holding up to" not in result.stdout
    assert _sleeps(tmp_path) == 0
    assert _stops(log) == ["pod stop pod123"]


def test_a_failed_stop_after_the_hold_is_exit_3(tmp_path: Path) -> None:
    result, log = _hold_run(
        tmp_path,
        "only true\n",
        KEEP_POD_ON_FAIL=None,
        KEEP_HOLD_MIN="1",
        STOP_GRACE_MIN="1",
        STUB_PULLED_AFTER="1",
        STUB_VERDICT="pull-failed",
        STUB_NEW_RC="1",
        STUB_OLD_RC="1",
        STUB_CURL_RC="1",
    )
    assert "POD_STOP_FAILED" in result.stdout
    assert result.returncode == 3  # the pod no longer stays: the stop failed and it bills


def test_a_bad_keep_hold_min_is_refused(tmp_path: Path) -> None:
    result, log = _hold_run(tmp_path, KEEP_HOLD_MIN="two hours")
    assert result.returncode == 2
    assert "KEEP_HOLD_MIN" in result.stdout and not log.exists()


def test_dry_run_prints_the_hold_and_sends_nothing(tmp_path: Path) -> None:
    result, log = _hold_run(
        tmp_path, "only true\n", DRY_RUN="1", KEEP_HOLD_MIN="1", SESSION_CAP="0s"
    )
    assert "[dry-run] POD_KEPT: hold up to 1 min for the Mac, then stop the pod" in result.stdout
    assert "[dry-run] runpodctl pod stop pod123" in result.stdout
    assert not log.exists() and not (tmp_path / "curl.log").exists()
    assert _sleeps(tmp_path) == 0


# The Mac side. The watcher reads the chain log for POD_KEPT, POD_STOP_FAILED and the
# "pod stop sent with:" line, so the lines of the hold must keep that reading.
def test_the_watcher_reads_the_pod_as_kept_while_it_holds() -> None:
    w = mac_watch35.Watch()
    w.scan("[00:10:00] " + HOLD.format(n=120))
    assert w.kept and not w.stop_sent and not w.stop_failed


def test_the_watcher_reads_the_stop_that_follows_a_hold_timeout() -> None:
    w = mac_watch35.Watch()
    for line in (
        HOLD.format(n=120),
        TIMEOUT.format(n=120),
        "pod stop sent with: runpodctl pod stop",
    ):
        w.scan(f"[02:10:00] {line}")
    assert w.stop_sent and not w.stop_failed


def test_the_watcher_reads_a_failed_stop_after_a_hold_timeout() -> None:
    w = mac_watch35.Watch()
    w.scan("[02:10:00] " + TIMEOUT.format(n=120))
    w.scan("[02:10:05] POD_STOP_FAILED: no stop command worked and the GPU still bills.")
    assert w.stop_failed


# A relaunch starts a new tmux session on the same pod, and the launch refuses while the
# held chain's session lives. So the watcher releases the hold before anything else.
_TMUX = """#!/usr/bin/env bash
echo "$*" >> "@T@/tmux.log"
n=$(( $(cat "@T@/tmux.n" 2>/dev/null || echo 0) + 1 )); echo "$n" > "@T@/tmux.n"
[ "$1" = has-session ] || exit 0
[ -e "@T@/session.stays" ] && exit 0
[ -e "@T@/work/HOLD_RELEASED" ] && [ "$n" -ge 3 ] && exit 1
exit 0
"""


def _release(tmp_path: Path, *, holding: bool, stays: bool = False) -> subprocess.CompletedProcess:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("tmux", _TMUX), ("sleep", "#!/usr/bin/env bash\nexit 0\n")):
        (bin_dir / name).write_text(body.replace("@T@", str(tmp_path)), encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    (tmp_path / "work").mkdir()
    if holding:
        (tmp_path / "work" / "HOLDING").write_text("", encoding="utf-8")
    if stays:
        (tmp_path / "session.stays").write_text("", encoding="utf-8")
    cmd = watch_stages35.release_hold_cmd(str(tmp_path / "work"), "exp35")
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}"}
    return subprocess.run(["bash", "-c", cmd], env=env, capture_output=True, text=True, timeout=30)


def test_the_release_command_signals_a_held_chain_and_waits_for_its_session_to_end(
    tmp_path: Path,
) -> None:
    result = _release(tmp_path, holding=True)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "work" / "HOLD_RELEASED").exists()
    assert int((tmp_path / "tmux.n").read_text()) == 3  # it asked until the session was gone


def test_the_release_command_does_nothing_when_no_chain_holds(tmp_path: Path) -> None:
    result = _release(tmp_path, holding=False)
    assert result.returncode == 0
    assert not (tmp_path / "work" / "HOLD_RELEASED").exists()
    assert not (tmp_path / "tmux.log").exists()  # a live chain that does not hold is left alone


def test_the_release_command_succeeds_when_the_session_does_not_end(tmp_path: Path) -> None:
    result = _release(tmp_path, holding=True, stays=True)
    assert result.returncode == 0  # the launch that follows then refuses, as before


def test_the_setup_releases_the_hold_before_it_checks_out_the_commit(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    result = s.run("--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    text = result.stdout
    assert "HOLD_RELEASED" in text
    # bash reads its script as it runs: the held chain must be gone before git rewrites it.
    assert text.index("HOLD_RELEASED") < text.index("git checkout")
    assert text.index("HOLD_RELEASED") < text.index("tmux new-session")
