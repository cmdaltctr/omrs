"""Checks on ``--resume`` of mac_watch35.py: the folder, the pod id, the inputs and the files.

The stubs of test_mac_watch35.py play the pod. No test reaches RunPod or any network host,
and none creates, stops or deletes a pod.
"""

from __future__ import annotations

from pathlib import Path

from test_mac_watch35 import POD, Session, _last, _sha
from test_watch_stages35 import TAG, _stage


# --resume.
def _again(s: Session, steps: list[str]) -> None:
    """Make the fake pod ready for another launch: same disk, a new chain script."""
    (s.pod / "step").unlink(missing_ok=True)
    (s.pod / "steps").write_text("".join(f"{x}\n" for x in steps), encoding="utf-8")


def _inputs_copies(s: Session) -> int:
    return sum("exp35-inputs.tgz" in line for line in s.log("scp.log"))


def test_resume_writes_resume_moves_earlier_files_aside_and_skips_matching_inputs(
    tmp_path: Path,
) -> None:
    s = Session(tmp_path, ["+[00:00:01] == a: start", "done"])
    _stage(s)
    first = s.run()
    assert first.returncode == 0, first.stdout + first.stderr
    folder = s.folder()
    before = _inputs_copies(s)
    old_log = (folder / "test-session.log").read_bytes()
    old_tgz = (folder / "test-session-out.tgz").read_bytes()
    _again(s, ["+[00:00:01] == b: start", "dead"])
    second = s.run("--resume")
    output = second.stdout + second.stderr
    assert second.returncode == 7, output
    assert _inputs_copies(s) == before  # the pod held the same inputs: no copy
    assert "resume" in output and "no copy" in output
    assert (s.work / "session.env").read_text(encoding="utf-8").splitlines()[-1] == "RESUME=1"
    assert (folder / "test-session.log.attempt1").read_bytes() == old_log
    assert (folder / "test-session-out.tgz.attempt1").read_bytes() == old_tgz
    assert (folder / "test-session-out.tgz.sha256.attempt1").is_file()
    assert (folder / "stage-out" / f"{TAG}.tgz").is_file()  # the stage-out folder stays
    assert "== b: start" in (folder / "test-session.log").read_text(encoding="utf-8")
    assert not (folder / "test-session-out.tgz").exists()  # the pod's stale tarball was removed
    assert (folder / "watcher-out.tgz").is_file()
    assert len(s.log("scp.log")) >= 1 and sum("stage-out" in x for x in s.log("scp.log")) == 1
    _again(s, ["dead"])
    assert s.run("--resume").returncode == 7
    assert (folder / "test-session.log.attempt2").is_file()  # never overwritten
    assert (folder / "test-session.log.attempt1").read_bytes() == old_log


def test_resume_copies_the_inputs_again_when_the_pod_copy_does_not_match(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    assert s.run().returncode == 0
    before = _inputs_copies(s)
    (s.work / "inputs/exp35-inputs.tgz").write_bytes(b"damaged on the pod")
    _again(s, ["dead"])
    assert s.run("--resume").returncode == 7
    assert _inputs_copies(s) > before
    assert _sha(s.work / "inputs/exp35-inputs.tgz") == _sha(s.folder() / "inputs/exp35-inputs.tgz")


def test_resume_without_an_earlier_session_folder_is_refused_before_any_step(
    tmp_path: Path,
) -> None:
    s = Session(tmp_path, ["done"])
    result = s.run("--resume")
    assert result.returncode == 2 and "--resume" in result.stdout
    assert not s.log("ssh.log") and not s.log("scp.log")
    assert _last(result) == f"DELETE_POD_NOW {POD}"


def test_resume_runs_only_in_a_folder_that_recorded_the_same_pod_id(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    assert s.run().returncode == 0
    assert (s.folder() / "pod-id.txt").read_text(encoding="utf-8").strip() == POD
    _again(s, ["dead"])
    other = s.run("--resume", "--pod-id", "otherpod9")  # the last --pod-id wins
    assert other.returncode == 2, other.stdout + other.stderr
    assert "REFUSED" in other.stdout and "--resume" in other.stdout and "otherpod9" in other.stdout
    assert not (s.folder() / "test-session.log.attempt1").exists()  # nothing moved aside
    dry = s.run("--dry-run", "--resume", "--pod-id", "otherpod9")
    assert dry.returncode == 2 and "PROBLEM: --resume" in dry.stdout
    assert s.run("--resume").returncode == 7  # the same pod id is accepted


def test_resume_refuses_a_folder_that_recorded_no_pod_id(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    assert s.run().returncode == 0
    (s.folder() / "pod-id.txt").unlink()  # a folder from before the file existed
    again = s.run("--resume")
    assert again.returncode == 2 and "pod-id.txt" in again.stdout


def test_a_fresh_launch_still_refuses_an_existing_folder(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    assert s.run().returncode == 0
    again = s.run()
    assert again.returncode == 2 and "already exists" in again.stdout
