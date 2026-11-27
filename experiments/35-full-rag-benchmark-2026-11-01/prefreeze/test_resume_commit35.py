"""Checks on the commit record of each stage tarball and the resume rule of the chain.

Why: a resume after a code fix must not keep outputs that an older commit made without a
record. The chain writes ``<tag>.tgz.commit`` (the commit the chain runs from) before the
``.sha256``. A resume skips a stage only when that commit equals the current one, or when
the owner names the old commit in ``RESUME_FROM_COMMIT``; each such skip goes into
``resume-record.jsonl``. The runs use the stubs of test_pod_test_session_script.py and a
real temporary git repository that holds copies of the two chain scripts.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import test_pod_test_session_script as session
from test_pod_stage_tarballs import _sha, _stage_out
from test_pod_test_session_script import _lines, _run

HERE = Path(__file__).parent
RUN = 'a sh -c \'echo x >> "$OUT_DIR/a.count"; echo A > "$OUT_DIR/a.out"\'\n'
SECOND = "b sh -c 'echo y >> \"$OUT_DIR/b.count\"'\n"


class Repo:
    """A temporary git repository that holds the chain scripts; each commit moves HEAD."""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path / "repo"
        self.env = {**os.environ, "HOME": str(tmp_path), "GIT_CONFIG_NOSYSTEM": "1"}
        folder = self.root / "experiments" / "exp" / "prefreeze"
        folder.mkdir(parents=True)
        for name in ("pod_test_session.sh", "stage_pack35.sh", "offsite35.sh"):
            shutil.copy(HERE / name, folder / name)
        self.script = folder / "pod_test_session.sh"
        self._git("init", "-q")
        self._git("add", "-A")
        self.head = self.commit()

    def _git(self, *args: str) -> str:
        cmd = ["git", "-C", str(self.root), "-c", "user.name=t", "-c", "user.email=t@e.invalid"]
        cmd += ["-c", "commit.gpgsign=false", *args]
        done = subprocess.run(cmd, env=self.env, check=True, capture_output=True, text=True)
        return done.stdout.strip()

    def commit(self) -> str:
        """Make an empty commit and return the new HEAD."""
        self._git("commit", "-q", "--allow-empty", "-m", "c")
        self.head = self._git("rev-parse", "HEAD")
        return self.head


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repo:
    made = Repo(tmp_path)
    monkeypatch.setattr(session, "PATH_SCRIPT", made.script)
    return made


def _record(tmp_path: Path) -> list[dict[str, str]]:
    path = tmp_path / "smoke-out" / "resume-record.jsonl"
    return [json.loads(x) for x in _lines(path)]


def _logging_stub(tmp_path: Path, name: str, log: str) -> str:
    """A stub of *name* that logs its arguments and the stage-out listing, then runs it."""
    stub = tmp_path / "stub-bin"
    stub.mkdir(exist_ok=True)
    real = shutil.which(name) or shutil.which("shasum")
    extra = "" if shutil.which(name) else " -a 256"
    body = (
        "#!/usr/bin/env bash\n"
        f'echo "$* :: $(ls -A "{tmp_path}/work/stage-out" 2>/dev/null | tr "\\n" " ")" '
        f'>> "{tmp_path}/{log}"\n'
        f'exec "{real}"{extra} "$@"\n'
    )
    (stub / name).write_text(body, encoding="utf-8")
    (stub / name).chmod(0o755)
    return f"{tmp_path / 'bin'}:{stub}:{os.environ['PATH']}"


def test_pack_writes_the_head_commit_before_the_sha256(tmp_path: Path, repo: Repo) -> None:
    path = _logging_stub(tmp_path, "sha256sum", "sha-calls")
    result, _ = _run(tmp_path, RUN + SECOND, PATH=path)
    assert result.returncode == 0, result.stdout
    out = _stage_out(tmp_path)
    for tag in ("01-a", "02-b"):
        assert (out / f"{tag}.tgz.commit").read_text() == f"{repo.head}\n"
    first_pack = next(x for x in _lines(tmp_path / "sha-calls") if "01-a.tgz ::" in x)
    assert "01-a.tgz.commit " in first_pack and "01-a.tgz.sha256 " not in first_pack
    assert not list(out.glob("*.tmp"))


def test_the_spare_copy_carries_the_commit_file_before_the_sha256(
    tmp_path: Path, repo: Repo
) -> None:
    spare = tmp_path / "spare"
    (tmp_path / "cp-bin").mkdir()
    stub = tmp_path / "cp-bin" / "cp"
    stub.write_text(
        f'#!/usr/bin/env bash\necho "$1" >> "{tmp_path}/cp-calls"\n'
        f'exec {shutil.which("cp")} "$@"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    path = f"{tmp_path / 'bin'}:{tmp_path / 'cp-bin'}:{os.environ['PATH']}"
    result, _ = _run(tmp_path, RUN, SPARE_DIR=str(spare), PATH=path)
    assert result.returncode == 0, result.stdout
    assert (spare / "01-a.tgz.commit").read_text() == f"{repo.head}\n"
    names = [Path(x).name for x in _lines(tmp_path / "cp-calls") if "stage-out" in x]
    assert names == ["01-a.tgz", "01-a.tgz.commit", "01-a.tgz.sha256"]


def test_the_dry_run_names_the_commit_file(tmp_path: Path, repo: Repo) -> None:
    result, _ = _run(tmp_path, RUN, DRY_RUN="1", SPARE_DIR=str(tmp_path / "spare"))
    assert result.returncode == 0, result.stdout
    assert result.stdout.count("01-a.tgz.commit") == 2  # the pack line and the spare line


def test_a_tarball_of_the_same_commit_is_skipped_with_the_old_line(
    tmp_path: Path, repo: Repo
) -> None:
    _run(tmp_path, RUN)
    result, _ = _run(tmp_path, RUN, RESUME="1")
    assert result.returncode == 0, result.stdout
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x"]
    assert "== a: SKIPPED (resume, done in 01-a.tgz)\n" in result.stdout
    assert "resumed: a" in result.stdout
    assert not (tmp_path / "smoke-out" / "resume-record.jsonl").exists()


def test_a_tarball_of_another_commit_runs_again_without_the_override(
    tmp_path: Path, repo: Repo
) -> None:
    old = repo.head
    _run(tmp_path, RUN)
    new = repo.commit()
    result, _ = _run(tmp_path, RUN, RESUME="1")
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x", "x"]
    assert f"== a: done at {old[:7]}, this run is {new[:7]}: running it again" in result.stdout
    assert "SKIPPED" not in result.stdout and "resumed: none" in result.stdout
    assert (_stage_out(tmp_path) / "01-a.tgz.commit").read_text() == f"{new}\n"  # packed again
    assert not (tmp_path / "smoke-out" / "resume-record.jsonl").exists()


def test_a_tarball_without_a_commit_file_runs_again(tmp_path: Path, repo: Repo) -> None:
    _run(tmp_path, RUN)
    (_stage_out(tmp_path) / "01-a.tgz.commit").unlink()
    result, _ = _run(tmp_path, RUN, RESUME="1", RESUME_FROM_COMMIT=repo.head)
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x", "x"]
    assert f"== a: done at unknown, this run is {repo.head[:7]}: running it again" in result.stdout
    assert not (tmp_path / "smoke-out" / "resume-record.jsonl").exists()


def test_the_override_skips_the_stage_and_writes_one_json_line_per_skip(
    tmp_path: Path, repo: Repo
) -> None:
    old = repo.head
    _run(tmp_path, RUN + SECOND)
    new = repo.commit()
    result, _ = _run(tmp_path, RUN + SECOND, RESUME="1", RESUME_FROM_COMMIT=old)
    assert result.returncode == 0, result.stdout
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x"]  # not run again
    line = f"== a: SKIPPED (resume, done in 01-a.tgz at {old[:7]}, this run is {new[:7]}; "
    assert line + "RESUME_FROM_COMMIT)" in result.stdout
    assert "resumed: a b" in result.stdout
    out = _stage_out(tmp_path)
    assert _record(tmp_path) == [
        {"stage": "a", "tag": "01-a", "tarball_commit": old, "run_commit": new,
         "sha256": _sha(out / "01-a.tgz")},
        {"stage": "b", "tag": "02-b", "tarball_commit": old, "run_commit": new,
         "sha256": _sha(out / "02-b.tgz")},
    ]  # fmt: skip


def test_the_override_for_another_commit_does_not_skip(tmp_path: Path, repo: Repo) -> None:
    old = repo.head
    _run(tmp_path, RUN)
    new = repo.commit()
    other = repo.commit()
    assert len({old, new, other}) == 3
    result, _ = _run(tmp_path, RUN, RESUME="1", RESUME_FROM_COMMIT=new)
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x", "x"]
    assert f"== a: done at {old[:7]}, this run is {other[:7]}: running it again" in result.stdout
    assert not (tmp_path / "smoke-out" / "resume-record.jsonl").exists()


@pytest.mark.parametrize(
    "bad",
    ["abc1234", "A" * 40, "a" * 39, "g" * 40, "a" * 41, "HEAD"],
    ids=["short", "upper-case", "39-hex", "not-hex", "41-hex", "name"],
)
def test_a_malformed_override_is_refused_before_the_first_stage(
    tmp_path: Path, repo: Repo, bad: str
) -> None:
    result, log = _run(tmp_path, RUN, RESUME="1", RESUME_FROM_COMMIT=bad)
    assert result.returncode == 2
    assert "RESUME_FROM_COMMIT" in result.stdout and "40" in result.stdout
    assert not (tmp_path / "smoke-out" / "a.count").exists() and not log.exists()


def test_a_chain_outside_a_git_repository_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "loose" / "exp" / "prefreeze"
    folder.mkdir(parents=True)
    for name in ("pod_test_session.sh", "stage_pack35.sh", "offsite35.sh"):
        shutil.copy(HERE / name, folder / name)
    monkeypatch.setattr(session, "PATH_SCRIPT", folder / "pod_test_session.sh")
    result, _ = _run(tmp_path, RUN, GIT_CEILING_DIRECTORIES=str(tmp_path))
    assert result.returncode == 2
    assert "commit" in result.stdout and not (tmp_path / "smoke-out" / "a.count").exists()


def _spare_run(tmp_path: Path, repo: Repo) -> tuple[Path, str, str]:
    """Run once at one commit with a spare copy, drop the local stage files, move HEAD on."""
    spare = tmp_path / "spare"
    old = repo.head
    _run(tmp_path, RUN, SPARE_DIR=str(spare))
    shutil.rmtree(_stage_out(tmp_path))
    (tmp_path / "smoke-out" / "a.out").unlink()
    return spare, old, repo.commit()


def test_a_spare_restore_of_the_same_commit_keeps_the_old_line(tmp_path: Path, repo: Repo) -> None:
    spare = tmp_path / "spare"
    _run(tmp_path, RUN, SPARE_DIR=str(spare))
    shutil.rmtree(_stage_out(tmp_path))
    result, _ = _run(tmp_path, RUN, RESUME="1", SPARE_DIR=str(spare))
    assert f"== a: RESTORED from {spare}/01-a.tgz, SKIPPED (resume)" in result.stdout
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x"]
    assert (_stage_out(tmp_path) / "01-a.tgz.commit").read_text() == f"{repo.head}\n"


def test_a_spare_restore_of_another_commit_runs_the_stage_again(tmp_path: Path, repo: Repo) -> None:
    spare, old, new = _spare_run(tmp_path, repo)
    result, _ = _run(tmp_path, RUN, RESUME="1", SPARE_DIR=str(spare))
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x", "x"]
    assert f"== a: done at {old[:7]}, this run is {new[:7]}: running it again" in result.stdout
    assert "RESTORED" not in result.stdout and "tarball hash mismatch" not in result.stdout


def test_a_spare_restore_with_the_override_skips_and_writes_the_record(
    tmp_path: Path, repo: Repo
) -> None:
    spare, old, new = _spare_run(tmp_path, repo)
    result, _ = _run(tmp_path, RUN, RESUME="1", SPARE_DIR=str(spare), RESUME_FROM_COMMIT=old)
    assert result.returncode == 0, result.stdout
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x"]
    assert (tmp_path / "smoke-out" / "a.out").read_text() == "A\n"  # unpacked again
    assert "RESUME_FROM_COMMIT)" in result.stdout and "resumed: a" in result.stdout
    assert [(r["stage"], r["tarball_commit"], r["run_commit"]) for r in _record(tmp_path)] == [
        ("a", old, new)
    ]


def _block_the_record(tmp_path: Path) -> None:
    """Make resume-record.jsonl impossible to write: a folder sits at its path."""
    (tmp_path / "smoke-out" / "resume-record.jsonl").mkdir()


def test_an_override_skip_that_cannot_write_its_record_runs_the_stage_again(
    tmp_path: Path, repo: Repo
) -> None:
    old = repo.head
    _run(tmp_path, RUN)
    new = repo.commit()
    _block_the_record(tmp_path)
    result, _ = _run(tmp_path, RUN, RESUME="1", RESUME_FROM_COMMIT=old)
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x", "x"]  # it ran
    assert "== a: cannot write the resume record, running it again" in result.stdout
    assert "SKIPPED" not in result.stdout and "resumed: none" in result.stdout
    assert (
        _stage_out(tmp_path) / "01-a.tgz.commit"
    ).read_text() == f"{new}\n"  # packed at the run commit


def test_a_spare_override_skip_that_cannot_write_its_record_runs_the_stage_again(
    tmp_path: Path, repo: Repo
) -> None:
    spare, old, new = _spare_run(tmp_path, repo)
    _block_the_record(tmp_path)
    result, _ = _run(tmp_path, RUN, RESUME="1", SPARE_DIR=str(spare), RESUME_FROM_COMMIT=old)
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x", "x"]
    assert "== a: cannot write the resume record, running it again" in result.stdout
    assert "SKIPPED" not in result.stdout
    assert (_stage_out(tmp_path) / "01-a.tgz.commit").read_text() == f"{new}\n"
