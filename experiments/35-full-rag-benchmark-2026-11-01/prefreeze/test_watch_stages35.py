"""Checks on the per-stage pull, --keep-pod-on-fail, --resume and the WORK folder (watcher side).

The chain packs each finished stage into ``$WORK/stage-out/<tag>.tgz`` and writes the
``.sha256`` last. The watcher copies each new tarball to the Mac and checks its SHA-256.
Unit tests use a fake pod and a fake clock. The end-to-end tests use the stubs of
test_mac_watch35.py. No test reaches RunPod or any network host, and none creates,
stops or deletes a pod.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

import mac_watch35
import pytest
import watch_stages35
from test_mac_watch35 import HERE, POD, Session, _last, _sha

TAG = "01-setup"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class StagePod:
    """A fake pod: it lists stage tarballs and copies them into the destination folder."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}  # tarball name -> bytes
        self.recorded: dict[str, str] = {}  # tarball name -> hash in its .sha256 file
        self.listings, self.copies, self.fail, self.wrong, self.down = 0, [], 0, 0, False

    def add(self, name: str, data: bytes = b"stage files") -> str:
        self.files[name], self.recorded[name] = data, _digest(data)
        return self.recorded[name]

    def remote(self, path: str) -> str:
        return f"root@pod:{path}"

    def ssh(self, command: str, timeout: float = 120) -> subprocess.CompletedProcess[bytes] | None:
        assert "stage-out" in command
        self.listings += 1
        if self.down:
            return None
        text = "".join(f"{n}.sha256 {h}\n" for n, h in sorted(self.recorded.items()))
        return subprocess.CompletedProcess([], 0, text.encode(), b"")

    def copy(self, sources: list[str], dest: str, timeout: float = 3600) -> bool:
        names = [s.rsplit("/", 1)[1] for s in sources]
        self.copies.append(names)
        if self.fail:
            self.fail -= 1
            return False
        tgz = names[0]
        wrong, self.wrong = self.wrong > 0, max(self.wrong - 1, 0)
        data = b"corrupt in transit" if wrong else self.files[tgz]
        (Path(dest) / tgz).write_bytes(data)
        (Path(dest) / names[1]).write_text(f"{self.recorded[tgz]}  {tgz}\n", encoding="utf-8")
        return True


def _puller(tmp: Path, pod: StagePod) -> tuple[watch_stages35.StagePull, list[str]]:
    said: list[str] = []
    folder = tmp / "stage-out"
    return watch_stages35.StagePull(pod, mac_watch35.WORK, folder, said.append), said


def test_a_new_stage_tarball_is_copied_and_its_hash_is_checked(tmp_path: Path) -> None:
    pod = StagePod()
    want = pod.add(f"{TAG}.tgz")
    puller, said = _puller(tmp_path, pod)
    puller.pull_new()
    assert (tmp_path / "stage-out" / f"{TAG}.tgz").read_bytes() == b"stage files"
    assert (tmp_path / "stage-out" / f"{TAG}.tgz.sha256").is_file()
    assert f"  stage tarball {TAG}.tgz pulled, SHA-256 {want}" in said
    assert pod.copies == [[f"{TAG}.tgz", f"{TAG}.tgz.sha256"]]


def test_a_wrong_hash_is_copied_once_more_and_then_reported_without_ending_the_watch(
    tmp_path: Path,
) -> None:
    pod = StagePod()
    pod.add(f"{TAG}.tgz")
    pod.add("02-next.tgz")
    pod.wrong = 2  # both copies of the first tarball arrive wrong
    puller, said = _puller(tmp_path, pod)
    puller.pull_new()
    mismatch = [line for line in said if "STAGE_HASH_MISMATCH" in line]
    assert len(mismatch) == 1 and f"{TAG}.tgz" in mismatch[0]
    assert pod.copies[:2] == [[f"{TAG}.tgz", f"{TAG}.tgz.sha256"]] * 2  # one more copy
    assert (tmp_path / "stage-out" / "02-next.tgz").is_file()  # the next one is still pulled
    puller.pull_new()  # a tarball that failed twice is not copied again and again
    assert sum(c[0] == f"{TAG}.tgz" for c in pod.copies) == 2
    assert len([line for line in said if "STAGE_HASH_MISMATCH" in line]) == 1


def test_a_wrong_hash_on_the_first_copy_only_is_fixed_by_the_second(tmp_path: Path) -> None:
    pod = StagePod()
    pod.add(f"{TAG}.tgz")
    pod.wrong = 1
    puller, said = _puller(tmp_path, pod)
    puller.pull_new()
    assert not [line for line in said if "STAGE_HASH_MISMATCH" in line]
    assert any("pulled, SHA-256" in line for line in said) and len(pod.copies) == 2


def test_a_failed_copy_is_tried_again_on_the_next_poll(tmp_path: Path) -> None:
    pod = StagePod()
    pod.add(f"{TAG}.tgz")
    pod.fail = 1
    puller, said = _puller(tmp_path, pod)
    puller.pull_new()
    assert len(pod.copies) == 1 and not any("pulled" in line for line in said)
    puller.pull_new()
    assert len(pod.copies) == 2 and any("pulled, SHA-256" in line for line in said)


def test_a_pulled_tarball_is_not_copied_again_and_each_poll_makes_one_listing(
    tmp_path: Path,
) -> None:
    pod = StagePod()
    pod.add(f"{TAG}.tgz")
    puller, _said = _puller(tmp_path, pod)
    for _ in range(3):
        puller.pull_new()
    assert len(pod.copies) == 1 and pod.listings == 3
    pod.add("02-next.tgz")
    puller.pull_new()
    assert [c[0] for c in pod.copies] == [f"{TAG}.tgz", "02-next.tgz"]


def test_a_repacked_stage_with_a_new_hash_is_pulled_again(tmp_path: Path) -> None:
    pod = StagePod()
    pod.add(f"{TAG}.tgz", b"first")
    puller, _said = _puller(tmp_path, pod)
    puller.pull_new()
    pod.add(f"{TAG}.tgz", b"second")
    puller.pull_new()
    assert (tmp_path / "stage-out" / f"{TAG}.tgz").read_bytes() == b"second"


def test_a_failed_listing_copies_nothing_and_raises_nothing(tmp_path: Path) -> None:
    pod = StagePod()
    pod.add(f"{TAG}.tgz")
    pod.down = True
    puller, _said = _puller(tmp_path, pod)
    puller.pull_new()
    assert pod.copies == [] and puller.summary().startswith("stage tarballs pulled: 0")


def test_a_name_with_a_shell_character_is_never_copied(tmp_path: Path) -> None:
    pod = StagePod()
    pod.add("01-a;rm -rf x.tgz")
    pod.add("02-fine.tgz")
    puller, _said = _puller(tmp_path, pod)
    puller.pull_new()
    assert [c[0] for c in pod.copies] == ["02-fine.tgz"]


def test_the_summary_lists_the_count_and_the_names(tmp_path: Path) -> None:
    pod = StagePod()
    for name in ("02-b.tgz", f"{TAG}.tgz"):
        pod.add(name)
    puller, _said = _puller(tmp_path, pod)
    puller.pull_new()
    assert puller.summary() == f"stage tarballs pulled: 2 ({TAG}.tgz, 02-b.tgz)"


def test_tarballs_from_an_earlier_attempt_are_not_copied_again(tmp_path: Path) -> None:
    pod = StagePod()
    want = pod.add(f"{TAG}.tgz")
    first, _said = _puller(tmp_path, pod)
    first.pull_new()
    second, _said = _puller(tmp_path, pod)  # a new watcher on the same results folder
    second.pull_new()
    assert len(pod.copies) == 1 and second.summary().startswith("stage tarballs pulled: 1")
    (tmp_path / "stage-out" / f"{TAG}.tgz").write_bytes(b"damaged")
    third, _said = _puller(tmp_path, pod)  # a damaged local file is pulled again
    third.pull_new()
    assert (
        len(pod.copies) == 2
        and _digest((tmp_path / "stage-out" / f"{TAG}.tgz").read_bytes()) == want
    )


# The watch loop: a long stage copy must not read as an idle chain or a lost connection.
LOG_START = "[00:00:01] == a: start (timeout 600s)\n"


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def pause(self, seconds: float) -> None:
        self.t += seconds


class LoopPod(StagePod):
    """A pod whose log follows a script; a stage copy takes ``copy_s`` and the chain ends."""

    def __init__(self, clock: Clock, copy_s: float = 0.0, ssh_down_from: float | None = None):
        super().__init__()
        self.clock, self.copy_s, self.ssh_down_from, self.log = clock, copy_s, ssh_down_from, ""
        self.listed_at: list[float] = []
        self.add(f"{TAG}.tgz")

    def ssh(self, command: str, timeout: float = 120) -> subprocess.CompletedProcess[bytes] | None:
        if self.ssh_down_from is not None and self.clock.now() >= self.ssh_down_from:
            self.down = True
        if "stage-out" in command:
            self.listed_at.append(self.clock.now())
            return super().ssh(command, timeout)
        if self.down:
            return None
        offset = int(re.search(r"tail -c \+(\d+)", command)[1]) - 1  # type: ignore[index]
        return subprocess.CompletedProcess([], 0, b"ALIVE 1\n" + self.log[offset:].encode(), b"")

    def copy(self, sources: list[str], dest: str, timeout: float = 3600) -> bool:
        self.clock.pause(self.copy_s)
        self.log += "[00:50:00] TEST_SESSION_DONE: copy it\n"  # the chain ended during the copy
        return super().copy(sources, dest, timeout)


def _watch(
    monkeypatch: pytest.MonkeyPatch, tmp: Path, pod: LoopPod, clock: Clock
) -> tuple[str, mac_watch35.Watch]:
    monkeypatch.setattr(mac_watch35, "now", clock.now)
    monkeypatch.setattr(mac_watch35, "pause", clock.pause)
    puller, _said = _puller(tmp, pod)
    w = mac_watch35.Watch()
    return mac_watch35.watch(pod, w, 15 * 3600, clock.now(), puller), w


def test_a_long_stage_copy_is_not_a_false_idle_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    pod = LoopPod(clock, copy_s=45 * 60)  # longer than the 30 min idle limit
    pod.log = LOG_START
    end, w = _watch(monkeypatch, tmp_path, pod, clock)
    assert end == "done" and w.done
    assert (tmp_path / "stage-out" / f"{TAG}.tgz").is_file()


def test_no_stage_copy_is_tried_while_the_poll_fails_and_ssh_lost_stays_on_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    pod = LoopPod(clock, copy_s=600, ssh_down_from=120)
    pod.log = LOG_START
    pod.recorded.clear()  # nothing to copy before the connection drops
    end, _w = _watch(monkeypatch, tmp_path, pod, clock)
    assert end == "ssh-lost"
    assert pod.copies == [] and all(at < 120 for at in pod.listed_at)  # none once the link is down
    assert 120 + mac_watch35.SSH_LOST_S <= clock.now() < 120 + mac_watch35.SSH_LOST_S + 61


# End to end through the stubs of test_mac_watch35.py.
def _stage(s: Session, tag: str = TAG) -> str:
    folder = s.work / "stage-out"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{tag}.tgz").write_bytes(f"stage {tag}".encode())
    digest = _sha(folder / f"{tag}.tgz")
    (folder / f"{tag}.tgz.sha256").write_text(f"{digest}  {tag}.tgz\n", encoding="utf-8")
    return digest


def test_the_watcher_pulls_each_stage_once_and_lists_them_at_the_end(tmp_path: Path) -> None:
    s = Session(tmp_path, ["+[00:00:01] == a: start", "+[00:00:02] == a: ok", "done"])
    digest = _stage(s)
    result = s.run()
    assert result.returncode == 0, result.stdout + result.stderr
    pulled = s.folder() / "stage-out" / f"{TAG}.tgz"
    assert _sha(pulled) == digest
    assert f"stage tarball {TAG}.tgz pulled, SHA-256 {digest}" in result.stdout
    assert f"stage tarballs pulled: 1 ({TAG}.tgz)" in result.stdout
    copies = [line for line in s.log("scp.log") if "stage-out" in line]
    assert len(copies) == 1  # several polls and the last check before the pull: one copy


def test_a_stage_that_ends_while_the_chain_is_stopped_is_pulled_before_the_final_pull(
    tmp_path: Path,
) -> None:
    s = Session(tmp_path, ["+[00:00:01] == a: start (timeout 600s)"])  # then idle: the stop is sent
    kill_dir = tmp_path / "stage.on-kill"
    kill_dir.mkdir()
    (kill_dir / f"{TAG}.tgz").write_bytes(b"late stage")
    digest = _digest(b"late stage")
    (kill_dir / f"{TAG}.tgz.sha256").write_text(f"{digest}  {TAG}.tgz\n", encoding="utf-8")
    result = s.run()
    assert result.returncode == mac_watch35.EXIT["idle"], result.stdout + result.stderr
    assert (s.folder() / "stage-out" / f"{TAG}.tgz").read_bytes() == b"late stage"
    assert f"stage tarballs pulled: 1 ({TAG}.tgz)" in result.stdout


def test_a_session_without_stage_tarballs_says_so_and_still_ends_normally(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    result = s.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "stage tarballs pulled: 0" in result.stdout


# POD_KEPT and --keep-pod-on-fail.
def test_keep_pod_on_fail_writes_the_flag_and_a_kept_pod_is_a_verdict_not_a_delete(
    tmp_path: Path,
) -> None:
    s = Session(tmp_path, ["done"])
    (s.pod / "keeps").touch()
    result = s.run("--keep-pod-on-fail")
    output = result.stdout + result.stderr
    assert result.returncode == mac_watch35.EXIT["kept"], output
    env = (s.work / "session.env").read_text(encoding="utf-8").splitlines()
    assert env[-1] == "KEEP_POD_ON_FAIL=1"
    assert "POD_KEPT:" in result.stdout and "pod-stop=kept" in result.stdout
    assert _last(result).startswith(f"KEEP_POD {POD}") and "--resume" in _last(result)
    assert "DELETE_POD_NOW" not in output


def test_without_the_flag_session_env_has_no_keep_or_resume_line(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    assert s.run().returncode == 0
    env = (s.work / "session.env").read_text(encoding="utf-8")
    assert "KEEP_POD_ON_FAIL" not in env and "RESUME" not in env


def test_the_kept_exit_key_is_new_and_unique() -> None:
    codes = list(mac_watch35.EXIT.values())
    assert len(codes) == len(set(codes)) and mac_watch35.EXIT["kept"] == 14


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


def test_a_fresh_launch_still_refuses_an_existing_folder(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    assert s.run().returncode == 0
    again = s.run()
    assert again.returncode == 2 and "already exists" in again.stdout


# The WORK folder.
def test_every_pod_path_follows_work() -> None:
    work = mac_watch35.WORK
    assert work == "/root/exp35-work"
    for value in (mac_watch35.INPUTS, mac_watch35.REMOTE_REPO, mac_watch35.LOG, mac_watch35.TARBALL,
                  mac_watch35.OWN_TARBALL, mac_watch35.PULLED, mac_watch35.SESSION_ENV,
                  mac_watch35.OUT_PARENT):  # fmt: skip
        assert value.startswith(f"{work}/") and "/workspace" not in value
    assert (
        f"WORK={work} bash " in mac_watch35.LAUNCH
        and f"> {mac_watch35.LOG} 2>&1" in mac_watch35.LAUNCH
    )


def test_launch35_default_work_is_the_watcher_work() -> None:
    launch = (HERE / "launch35.sh").read_text(encoding="utf-8")
    match = re.search(r'^WORK="\$\{WORK:-([^}]*)\}"', launch, re.MULTILINE)
    assert match is not None and match[1] == mac_watch35.WORK


def test_the_launch_script_sets_the_spare_folder_the_watcher_names() -> None:
    launch = (HERE / "launch35.sh").read_text(encoding="utf-8")
    assert watch_stages35.SPARE_DIR == "/workspace/exp35-stage-out"
    assert watch_stages35.SPARE_DIR in launch


def test_the_dry_run_shows_work_the_spare_folder_the_stage_pull_and_no_problem(
    tmp_path: Path,
) -> None:
    s = Session(tmp_path, ["done"])
    result = s.run("--dry-run", "--keep-pod-on-fail")
    out = result.stdout
    assert result.returncode == 0, out + result.stderr
    assert f"work folder {mac_watch35.WORK}" in out
    assert f"spare copy {watch_stages35.SPARE_DIR}" in out
    assert "per-stage pull" in out and f"{mac_watch35.WORK}/stage-out/*.tgz.sha256" in out
    assert "KEEP_POD_ON_FAIL=1" in out and "0 problem(s)" in out
    assert not s.log("ssh.log") and not s.log("scp.log")


def test_a_resume_dry_run_without_an_earlier_folder_names_the_problem(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    result = s.run("--dry-run", "--resume")
    assert result.returncode == 2 and "PROBLEM: --resume" in result.stdout
