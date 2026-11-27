"""Checks on how the chain keeps its outputs when the Mac is away (Exp 35 contingencies).

Final outputs: ``finish`` copies the outputs tarball, the chain log and the ``.sha256`` (last)
to SPARE_DIR before it waits for the Mac, so a pod stop does not lose them.
Seeded pod: a resume that skips a stage from a local tarball unpacks the tarball when the
marker ``<tag>.tgz.unpacked`` is absent (a new pod holds the tarballs only). The runs use the
stub commands of test_pod_test_session_script.py: no test reaches RunPod.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from test_pod_stage_tarballs import _stage_out
from test_pod_test_session_script import _lines, _run
from test_resume_commit35 import Repo, repo  # noqa: F401 - a fixture: an isolated EXP35

RUN = 'a sh -c \'echo x >> "$OUT_DIR/a.count"; echo A > "$OUT_DIR/a.out"\'\n'
FINAL = ("test-session-out.tgz", "test-session.log", "test-session-out.tgz.sha256")


def _log(tmp_path: Path, text: str = "chain log line\n") -> Path:
    path = tmp_path / "work" / "test-session.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _recording_stub(tmp_path: Path, name: str, body: str) -> str:
    """A stub of *name* ahead of the real one; returns the ``PATH`` that holds it."""
    stub = tmp_path / "rec-bin"
    stub.mkdir(exist_ok=True)
    (stub / name).write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
    (stub / name).chmod(0o755)
    return f"{tmp_path / 'bin'}:{stub}:{os.environ['PATH']}"


def test_finish_copies_the_outputs_the_log_and_the_sha256_last_to_the_spare(
    tmp_path: Path,
    repo: Repo,  # noqa: F811 - the imported fixture
) -> None:
    log = _log(tmp_path)
    records = repo.root / "experiments" / "exp" / "output"  # finish copies it with cp -p
    records.mkdir()
    (records / "run-records.jsonl").write_text("{}\n", encoding="utf-8")
    spare = tmp_path / "spare"
    cp = _recording_stub(
        tmp_path, "cp", f'echo "$1" >> "{tmp_path}/cp-calls"\nexec {shutil.which("cp")} "$@"\n'
    )
    result, _ = _run(tmp_path, RUN, SPARE_DIR=str(spare), PATH=cp)
    assert result.returncode == 0, result.stdout
    work = tmp_path / "work"
    for name in FINAL:
        assert (spare / name).read_bytes() == (work / name).read_bytes(), name
    assert (spare / "test-session.log").read_text() == log.read_text()
    names = [Path(x).name for x in _lines(tmp_path / "cp-calls")]
    assert [x for x in names if x in FINAL] == list(FINAL)  # the .sha256 file last
    assert f"== finish: spare copy of the final outputs in {spare}" in result.stdout


def test_the_final_copy_is_made_before_the_wait_for_the_mac(tmp_path: Path) -> None:
    _log(tmp_path)
    spare = tmp_path / "spare"
    path = _recording_stub(
        tmp_path, "sleep", f'ls -A "{spare}" | tr "\\n" " " > "{tmp_path}/at-sleep"\n'
    )
    result, _ = _run(
        tmp_path, RUN, SPARE_DIR=str(spare), STOP_GRACE_MIN="1", PULL_POLL_S="30", PATH=path
    )
    assert result.returncode == 0, result.stdout
    at_sleep = (tmp_path / "at-sleep").read_text().split()
    assert set(FINAL) <= set(at_sleep), at_sleep  # all three were there when the wait began


def test_the_log_path_follows_session_log(tmp_path: Path) -> None:
    other = tmp_path / "elsewhere.log"
    other.write_text("log from SESSION_LOG\n", encoding="utf-8")
    spare = tmp_path / "spare"
    result, _ = _run(tmp_path, RUN, SPARE_DIR=str(spare), SESSION_LOG=str(other))
    assert result.returncode == 0, result.stdout
    assert (spare / "test-session.log").read_text() == "log from SESSION_LOG\n"


def test_an_empty_spare_dir_logs_no_final_copy_line_and_the_run_works(tmp_path: Path) -> None:
    _log(tmp_path)
    result, log = _run(tmp_path, RUN, SPARE_DIR="")
    assert result.returncode == 0, result.stdout
    assert "final outputs" not in result.stdout
    assert (tmp_path / "work" / "test-session-out.tgz.sha256").is_file()
    assert len(_lines(log)) == 1  # the pod stopped


def test_a_failed_final_copy_is_logged_and_the_chain_goes_on(tmp_path: Path) -> None:
    _log(tmp_path)
    blocked = tmp_path / "blocked"
    blocked.write_text("a file, not a folder\n", encoding="utf-8")
    result, log = _run(tmp_path, RUN, SPARE_DIR=str(blocked / "spare"))
    assert result.returncode == 0, result.stdout
    assert "== finish: spare copy of the final outputs FAILED" in result.stdout
    assert (tmp_path / "work" / "test-session-out.tgz").is_file()
    assert len(_lines(log)) == 1  # the pod still stopped


def test_the_dry_run_names_the_final_copy(tmp_path: Path) -> None:
    spare = tmp_path / "spare"
    result, _ = _run(tmp_path, RUN, DRY_RUN="1", SPARE_DIR=str(spare))
    assert result.returncode == 0, result.stdout
    line = next(x for x in result.stdout.splitlines() if "test-session-out.tgz.sha256 to" in x)
    assert "test-session.log" in line and str(spare) in line and "[dry-run]" in line
    assert not spare.exists()


# A seeded pod holds the stage tarballs but not the files they hold.
def _seeded(tmp_path: Path) -> None:
    """Run once, then drop the stage's files and its marker, as on a new pod."""
    _run(tmp_path, RUN)
    out = tmp_path / "smoke-out"
    (out / "a.count").unlink()
    (out / "a.out").unlink()
    (_stage_out(tmp_path) / "01-a.tgz.unpacked").unlink()


def test_a_packed_stage_has_its_unpacked_marker_and_a_plain_resume_unpacks_nothing(
    tmp_path: Path,
) -> None:
    _run(tmp_path, RUN)
    assert (_stage_out(tmp_path) / "01-a.tgz.unpacked").is_file()
    result, _ = _run(tmp_path, RUN, RESUME="1")
    assert "unpacked" not in result.stdout
    assert "== a: SKIPPED (resume, done in 01-a.tgz)\n" in result.stdout


def test_a_resume_unpacks_a_skipped_stage_that_has_no_marker(tmp_path: Path) -> None:
    _seeded(tmp_path)
    result, _ = _run(tmp_path, RUN, RESUME="1")
    assert result.returncode == 0, result.stdout
    assert "== a: unpacked 01-a.tgz (seeded)" in result.stdout
    assert "== a: SKIPPED (resume, done in 01-a.tgz)\n" in result.stdout
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x"]  # unpacked, not run again
    assert (tmp_path / "smoke-out" / "a.out").read_text() == "A\n"
    assert (_stage_out(tmp_path) / "01-a.tgz.unpacked").is_file()
    again, _ = _run(tmp_path, RUN, RESUME="1")
    assert "unpacked" not in again.stdout  # the marker stops a second unpack


def test_an_override_skip_unpacks_a_stage_that_has_no_marker(tmp_path: Path) -> None:
    _seeded(tmp_path)
    (_stage_out(tmp_path) / "01-a.tgz.commit").write_text("b" * 40 + "\n")
    # The sha256 file does not cover the commit file, so the tarball still matches.
    result, _ = _run(tmp_path, RUN, RESUME="1", RESUME_FROM_COMMIT="b" * 40)
    assert "== a: unpacked 01-a.tgz (seeded)" in result.stdout
    assert "RESUME_FROM_COMMIT)" in result.stdout
    assert (tmp_path / "smoke-out" / "a.out").read_text() == "A\n"


def test_a_tarball_that_cannot_be_unpacked_runs_the_stage_again(tmp_path: Path) -> None:
    _seeded(tmp_path)
    tgz = _stage_out(tmp_path) / "01-a.tgz"
    tgz.write_bytes(b"not a tarball")
    digest = hashlib.sha256(tgz.read_bytes()).hexdigest()
    (_stage_out(tmp_path) / "01-a.tgz.sha256").write_text(f"{digest}  01-a.tgz\n")
    result, _ = _run(tmp_path, RUN, RESUME="1")
    assert "== a: unpack of 01-a.tgz FAILED, running it again" in result.stdout
    assert "SKIPPED" not in result.stdout and "resumed: none" in result.stdout
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x"]  # the stage ran once more
    assert (_stage_out(tmp_path) / "01-a.tgz.unpacked").is_file()  # packed again


def test_a_spare_restore_sets_the_unpacked_marker(tmp_path: Path) -> None:
    spare = tmp_path / "spare"
    _run(tmp_path, RUN, SPARE_DIR=str(spare))
    shutil.rmtree(_stage_out(tmp_path))
    first, _ = _run(tmp_path, RUN, RESUME="1", SPARE_DIR=str(spare))
    assert "RESTORED from" in first.stdout
    assert (_stage_out(tmp_path) / "01-a.tgz.unpacked").is_file()
    second, _ = _run(tmp_path, RUN, RESUME="1", SPARE_DIR=str(spare))
    assert "unpacked" not in second.stdout and "RESTORED" not in second.stdout
