"""Checks on ``--attach`` and ``--seed-from`` of mac_watch35.py (the Mac was away).

``--attach``: the Mac comes back while the chain still runs in tmux on the pod. The watcher
joins it: no inputs copy, no ``session.env``, no launch. ``--seed-from``: the pod and its
volume are gone. A new pod gets the stage tarballs from an earlier results folder, and the
chain resumes from them. The stubs of test_mac_watch35.py play the pod. No test reaches
RunPod or any network host, and none creates, stops or deletes a pod.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from test_mac_watch35 import POD, Session, _last, _sha
from test_watch_resume35 import _again
from test_watch_stages35 import TAG, _stage

SHA = "c" * 40
NEW_POD = "newpod42"


def _commit(s: Session, tag: str = TAG, text: str = SHA) -> None:
    (s.work / "stage-out" / f"{tag}.tgz.commit").write_text(f"{text}\n", encoding="utf-8")


def _tmux(s: Session) -> list[str]:
    return s.log("tmux.log")


# --attach.
def _away(tmp_path: Path) -> Session:
    """A first run that the Mac leaves at once: SIGTERM, with the chain still alive."""
    s = Session(tmp_path, ["+[00:00:01] == a: start (timeout 600s)", "term"])
    _stage(s)
    result = s.run()
    assert result.returncode == 12, result.stdout + result.stderr  # interrupted
    assert (s.pod / "alive").exists()  # the chain still runs on the pod
    return s


def test_attach_skips_the_setup_pulls_only_new_stages_and_ends_normally(tmp_path: Path) -> None:
    s = _away(tmp_path)
    folder = s.folder()
    env_before = (s.work / "session.env").read_bytes()
    n_ssh, n_scp, n_tmux = len(s.log("ssh.log")), len(s.log("scp.log")), len(_tmux(s))
    _stage(s, "02-next")  # a stage that ended while the Mac was away
    _again(s, ["+[00:00:05] == b: start (timeout 600s)", "done"])
    result = s.run("--attach")
    assert result.returncode == 0, result.stdout + result.stderr
    ssh, scp, tmux = s.log("ssh.log")[n_ssh:], s.log("scp.log")[n_scp:], _tmux(s)[n_tmux:]
    assert not any("session.env" in x or "new-session" in x for x in ssh + tmux)
    assert not any("sha256sum -c" in x or "git " in x for x in ssh)
    assert not any("exp35-inputs.tgz" in x or "classify-examples" in x for x in scp)
    assert not any(x.startswith("new-session") for x in tmux)
    assert (s.work / "session.env").read_bytes() == env_before
    pulled = [x for x in scp if "stage-out/" in x and ".incoming" in x]
    assert len(pulled) == 1 and "02-next.tgz" in pulled[0]  # 01-setup was pulled before
    assert (folder / "stage-out" / "02-next.tgz").is_file()
    assert "== b: start" in (folder / "test-session.log").read_text(encoding="utf-8")
    assert _last(result) == f"DELETE_POD_NOW {POD}"
    assert "--attach" in result.stdout


def test_attach_is_refused_when_the_tmux_session_is_absent_and_keeps_the_pod(
    tmp_path: Path,
) -> None:
    s = Session(tmp_path, ["done"])
    assert s.run().returncode == 0  # the chain ended: no tmux session
    n_tmux, n_scp = len(_tmux(s)), len(s.log("scp.log"))
    result = s.run("--attach")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED" in result.stdout and "tmux session exp35" in result.stdout
    assert len(_tmux(s)) == n_tmux + 1 and _tmux(s)[-1].startswith("has-session")
    assert len(s.log("scp.log")) == n_scp  # nothing copied
    assert _last(result).startswith(f"KEEP_POD {POD}")  # the pod may hold stage tarballs


def test_attach_with_resume_is_refused_before_any_step(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    assert s.run().returncode == 0
    before = len(s.log("ssh.log")), len(s.log("scp.log"))
    result = s.run("--attach", "--resume")
    assert result.returncode == 2
    assert "--attach and --resume cannot be used together" in result.stdout
    assert (len(s.log("ssh.log")), len(s.log("scp.log"))) == before
    dry = s.run("--dry-run", "--attach", "--resume")
    assert "PROBLEM: --attach and --resume cannot be used together" in dry.stdout


def test_attach_runs_only_in_a_folder_that_recorded_the_same_pod_id(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    assert s.run().returncode == 0
    other = s.run("--attach", "--pod-id", "otherpod9")
    assert other.returncode == 2, other.stdout + other.stderr
    assert "--attach" in other.stdout and "otherpod9" in other.stdout
    dry = s.run("--dry-run", "--attach", "--pod-id", "otherpod9")
    assert dry.returncode == 2 and "PROBLEM: --attach" in dry.stdout
    (s.folder() / "pod-id.txt").unlink()
    missing = s.run("--attach")
    assert missing.returncode == 2 and "pod-id.txt" in missing.stdout


def test_attach_without_an_earlier_folder_is_refused(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    result = s.run("--attach")
    assert result.returncode == 2 and "--attach" in result.stdout
    assert not s.log("ssh.log") and not s.log("scp.log")


def test_the_dry_run_shows_attach(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    assert s.run().returncode == 0
    before = len(s.log("ssh.log"))
    dry = s.run("--dry-run", "--attach")
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert "--attach: join the running chain" in dry.stdout
    assert "git checkout" not in dry.stdout and "tmux new-session" not in dry.stdout
    assert "step 4 " not in dry.stdout and "step 5 " not in dry.stdout
    assert len(s.log("ssh.log")) == before


# --seed-from.
def _old_folder(tmp_path: Path, s: Session) -> Path:
    """Finish one session, then move its results folder away: the old pod is gone."""
    _stage(s)
    _commit(s)
    _stage(s, "02-next")
    _commit(s, "02-next", "d" * 40)
    assert s.run().returncode == 0
    old = tmp_path / "old-session"
    shutil.move(str(s.folder()), str(old))
    shutil.rmtree(s.work / "stage-out")  # the new pod holds none
    return old


def test_seed_from_copies_the_tarballs_to_the_pod_and_the_new_folder_and_resumes(
    tmp_path: Path,
) -> None:
    s = Session(tmp_path, ["done"])
    old = _old_folder(tmp_path, s)
    _again(s, ["done"])
    n_scp, n_ssh = len(s.log("scp.log")), len(s.log("ssh.log"))
    result = s.run("--pod-id", NEW_POD, "--seed-from", str(old))
    assert result.returncode == 0, result.stdout + result.stderr
    new = s.folder()
    for tag in (TAG, "02-next"):
        for name in (f"{tag}.tgz", f"{tag}.tgz.commit", f"{tag}.tgz.sha256"):
            assert (s.work / "stage-out" / name).read_bytes() == (
                old / "stage-out" / name
            ).read_bytes()
            assert (new / "stage-out" / name).read_bytes() == (
                old / "stage-out" / name
            ).read_bytes()
    assert (new / "pod-id.txt").read_text(encoding="utf-8").strip() == NEW_POD
    env = (s.work / "session.env").read_text(encoding="utf-8").splitlines()
    assert "RESUME=1" in env and not any(x.startswith("RESUME_FROM_COMMIT") for x in env)
    record = (new / "seed-from.txt").read_text(encoding="utf-8")
    assert str(old) in record
    assert f"{TAG}.tgz {_sha(old / 'stage-out' / f'{TAG}.tgz')} {SHA}" in record
    assert f"02-next.tgz {_sha(old / 'stage-out' / '02-next.tgz')} {'d' * 40}" in record
    scp = s.log("scp.log")[n_scp:]
    inputs = next(i for i, x in enumerate(scp) if "exp35-inputs.tgz" in x)
    seeded = [i for i, x in enumerate(scp) if "01-setup.tgz" in x and ".incoming" not in x]
    assert seeded and seeded[0] > inputs  # after the inputs copy
    ssh = s.log("ssh.log")[n_ssh:]
    check = next(i for i, x in enumerate(ssh) if "stage-out" in x and "sha256sum -c" in x)
    launch = next(i for i, x in enumerate(ssh) if "session.env" in x)
    assert check < launch  # the pod checks the tarballs before the launch
    assert not [x for x in scp if "01-setup.tgz" in x and ".incoming" in x]  # not pulled again
    assert "seed" in result.stdout


def test_a_seed_tarball_with_a_wrong_hash_is_refused_and_nothing_is_launched(
    tmp_path: Path,
) -> None:
    s = Session(tmp_path, ["done"])
    old = _old_folder(tmp_path, s)
    tgz = old / "stage-out" / f"{TAG}.tgz"
    tgz.write_bytes(tgz.read_bytes() + b"\0")
    _again(s, ["done"])
    n = len(s.log("ssh.log")), len(s.log("scp.log")), len(_tmux(s))
    result = s.run("--pod-id", NEW_POD, "--seed-from", str(old))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "PROBLEM" in result.stdout or "REFUSED" in result.stdout
    assert f"{TAG}.tgz" in result.stdout and "SHA-256" in result.stdout
    assert (len(s.log("ssh.log")), len(s.log("scp.log")), len(_tmux(s))) == n
    assert not list((s.root / "experiments").rglob("seed-from.txt"))


@pytest.mark.parametrize("flag", ["--resume", "--attach"])
def test_seed_from_with_resume_or_attach_is_refused(tmp_path: Path, flag: str) -> None:
    s = Session(tmp_path, ["done"])
    old = _old_folder(tmp_path, s)
    result = s.run("--seed-from", str(old), flag)
    assert result.returncode == 2
    assert "--seed-from cannot be used with --resume or --attach" in result.stdout


def test_seed_from_needs_an_absolute_folder_that_holds_stage_tarballs(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    relative = s.run("--seed-from", "old-session")
    assert (
        relative.returncode == 2
        and "--seed-from old-session must be an absolute path" in relative.stdout
    )
    empty = tmp_path / "empty"
    (empty / "stage-out").mkdir(parents=True)
    none = s.run("--dry-run", "--seed-from", str(empty))
    assert (
        none.returncode == 2
        and f"PROBLEM: --seed-from {empty} holds no stage tarballs" in none.stdout
    )
    nothing = s.run("--seed-from", str(tmp_path / "missing"))
    assert nothing.returncode == 2 and "has no stage-out folder" in nothing.stdout
    assert not s.log("ssh.log") and not s.log("scp.log")


def test_the_dry_run_shows_the_seed_and_touches_nothing(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    old = _old_folder(tmp_path, s)
    before = len(s.log("ssh.log")), len(s.log("scp.log")), len(_tmux(s))
    dry = s.run("--dry-run", "--pod-id", NEW_POD, "--seed-from", str(old))
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert f"--seed-from: copy 2 stage tarballs from {old}" in dry.stdout
    assert "RESUME=1" in dry.stdout
    assert (len(s.log("ssh.log")), len(s.log("scp.log")), len(_tmux(s))) == before
    assert not list((s.root / "experiments").rglob("seed-from.txt"))
