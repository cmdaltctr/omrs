"""Checks on ``--resume`` of mac_watch35.py: the folder, the pod id, the inputs and the files.

The stubs of test_mac_watch35.py play the pod. No test reaches RunPod or any network host,
and none creates, stops or deletes a pod.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from test_mac_watch35 import POD, Session, _last, _sha
from test_watch_stages35 import TAG, StagePod, _puller, _stage


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


# --resume-from-commit and the commit file of each stage tarball.
SHA = "a" * 40


def _env_lines(s: Session) -> list[str]:
    return (s.work / "session.env").read_text(encoding="utf-8").splitlines()


def test_resume_from_commit_writes_the_value_into_session_env(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    assert s.run().returncode == 0
    _again(s, ["dead"])
    result = s.run("--resume", "--resume-from-commit", SHA)
    assert result.returncode == 7, result.stdout + result.stderr
    assert _env_lines(s)[-2:] == ["RESUME=1", f"RESUME_FROM_COMMIT={SHA}"]
    _again(s, ["dead"])
    assert s.run("--resume").returncode == 7  # the next launch without the flag drops it
    assert not any(x.startswith("RESUME_FROM_COMMIT") for x in _env_lines(s))


def test_resume_from_commit_without_resume_is_refused_before_any_step(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    result = s.run("--resume-from-commit", SHA)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED" in result.stdout and "--resume-from-commit needs --resume" in result.stdout
    assert not s.log("ssh.log") and not s.log("scp.log")
    assert _last(result) == f"DELETE_POD_NOW {POD}"
    dry = s.run("--dry-run", "--resume-from-commit", SHA)
    assert dry.returncode == 2 and "PROBLEM: --resume-from-commit needs --resume" in dry.stdout


@pytest.mark.parametrize(
    "bad", ["abc1234", "A" * 40, "z" * 40, "a" * 41], ids=["short", "upper", "not-hex", "long"]
)
def test_a_malformed_resume_from_commit_is_refused_before_any_step(
    tmp_path: Path, bad: str
) -> None:
    s = Session(tmp_path, ["done"])
    assert s.run().returncode == 0
    before = len(s.log("ssh.log")), len(s.log("scp.log"))
    result = s.run("--resume", "--resume-from-commit", bad)
    assert result.returncode == 2, result.stdout + result.stderr
    assert (
        "REFUSED" in result.stdout and "--resume-from-commit must be the full 40" in result.stdout
    )
    assert (len(s.log("ssh.log")), len(s.log("scp.log"))) == before
    assert not (s.folder() / "test-session.log.attempt1").exists()  # nothing moved aside


def test_the_dry_run_shows_the_resume_from_commit_value(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    assert s.run().returncode == 0
    dry = s.run("--dry-run", "--resume", "--resume-from-commit", SHA)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert f"RESUME_FROM_COMMIT={SHA}" in dry.stdout
    assert f"RESUME_FROM_COMMIT={SHA}" not in "\n".join(_env_lines(s))  # a dry run writes nothing


class CommitPod(StagePod):
    """A fake pod whose listing says which tarballs have a ``.commit`` file."""

    def __init__(self) -> None:
        super().__init__()
        self.commits: dict[str, str] = {}  # tarball name -> commit

    def ssh(self, command: str, timeout: float = 120) -> subprocess.CompletedProcess[bytes] | None:
        assert "stage-out" in command and ".commit" in command
        text = "".join(
            f"{n}.sha256 {h} {'commit' if n in self.commits else ''}\n"
            for n, h in sorted(self.recorded.items())
        )
        return subprocess.CompletedProcess([], 0, text.encode(), b"")

    def copy(self, sources: list[str], dest: str, timeout: float = 3600) -> bool:
        names = [x.rsplit("/", 1)[1] for x in sources]
        done = super().copy([sources[0], sources[-1]], dest, timeout)
        self.copies[-1] = names
        if done and len(names) == 3:
            (Path(dest) / names[1]).write_text(f"{self.commits[names[0]]}\n", encoding="utf-8")
        return done


def test_the_pull_copies_the_commit_file_with_the_tarball(tmp_path: Path) -> None:
    pod = CommitPod()
    pod.add(f"{TAG}.tgz")
    pod.commits[f"{TAG}.tgz"] = SHA
    pod.add("02-next.tgz")  # an older chain, or a failed pack: no .commit file
    puller, said = _puller(tmp_path, pod)
    puller.pull_new()
    folder = tmp_path / "stage-out"
    assert (folder / f"{TAG}.tgz.commit").read_text(encoding="utf-8") == f"{SHA}\n"
    assert pod.copies == [
        [f"{TAG}.tgz", f"{TAG}.tgz.commit", f"{TAG}.tgz.sha256"],
        ["02-next.tgz", "02-next.tgz.sha256"],
    ]
    assert (folder / "02-next.tgz").is_file() and not (folder / "02-next.tgz.commit").exists()
    assert not any("STAGE_HASH_MISMATCH" in x for x in said) and not puller.unresolved()


def test_the_watcher_pulls_the_commit_file_of_a_finished_stage(tmp_path: Path) -> None:
    s = Session(tmp_path, ["+[00:00:01] == a: start", "done"])
    _stage(s)
    (s.work / "stage-out" / f"{TAG}.tgz.commit").write_text(f"{SHA}\n", encoding="utf-8")
    result = s.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert (s.folder() / "stage-out" / f"{TAG}.tgz.commit").read_text(
        encoding="utf-8"
    ) == f"{SHA}\n"
