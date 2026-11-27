"""Checks on the per-stage tarballs, resume and keep-the-pod rules of pod_test_session.sh.

Why: /workspace is network storage on many hosts, so the work lives on the container
disk ($WORK). Each finished stage is packed, the Mac pulls it, and the volume keeps a
spare copy. The runs use the same stub commands as test_pod_test_session_script.py:
no test reaches RunPod.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tarfile
from pathlib import Path

import pytest
from test_pod_test_session_script import _lines, _run

POD_KEPT = "POD_KEPT: "
KEPT_TAIL = "; fix, then relaunch with RESUME=1, or delete the pod from the Mac"
TWO = 'alpha touch "$OUT_DIR/a.txt"\nGREETING=hi\nbeta touch "$OUT_DIR/b.txt"\n'


def _stage_out(tmp_path: Path) -> Path:
    return tmp_path / "work" / "stage-out"


def _members(tgz: Path) -> set[str]:
    with tarfile.open(tgz) as tar:
        # macOS bsdtar adds "._name" AppleDouble files for extended attributes; the pod has none.
        return {m.name for m in tar.getmembers() if m.isfile() and "/._" not in f"/{m.name}"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tar_stub(tmp_path: Path) -> str:
    """A ``tar`` that lists the stage-out folder as it starts, then runs the real tar.

    Returns the ``PATH`` that puts it after the folder ``_run`` makes for its own stubs.
    """
    stub = tmp_path / "tar-bin"
    stub.mkdir()
    body = (
        '#!/usr/bin/env bash\nn=$(( $(cat "{t}/tar-n" 2>/dev/null || echo 0) + 1 ))\n'
        'echo "$n" > "{t}/tar-n"\n'
        'ls -A "{t}/work/stage-out" 2>/dev/null | tr "\\n" " " > "{t}/ls-at-tar.$n"\n'
        'exec "{real}" "$@"\n'
    ).format(t=tmp_path, real=shutil.which("tar"))
    (stub / "tar").write_text(body, encoding="utf-8")
    (stub / "tar").chmod(0o755)
    return f"{tmp_path / 'bin'}:{stub}:{os.environ['PATH']}"


def test_work_unset_is_refused_with_a_plain_message(tmp_path: Path) -> None:
    result, log = _run(tmp_path, 'first touch "$OUT_DIR/ran"\n', WORK=None)
    assert result.returncode == 2
    assert "WORK" in result.stdout and "/root/exp35-work" in result.stdout
    assert not (tmp_path / "smoke-out" / "ran").exists()
    assert not log.exists()


def test_a_finished_stage_is_packed_with_its_tag_and_the_sha256_comes_last(tmp_path: Path) -> None:
    stages = TWO.replace(
        "alpha touch",
        'alpha mkdir -p "$OUT_DIR/stores/e" && touch "$OUT_DIR/stores/e/data.lance" && touch',
    )
    result, _ = _run(tmp_path, stages)
    out = _stage_out(tmp_path)
    assert result.returncode == 0, result.stdout
    # Value lines do not count: beta is stage 2.
    assert sorted(p.name for p in out.iterdir()) == [
        "01-alpha.tgz",
        "01-alpha.tgz.commit",
        "01-alpha.tgz.sha256",
        "01-alpha.tgz.unpacked",
        "02-beta.tgz",
        "02-beta.tgz.commit",
        "02-beta.tgz.sha256",
        "02-beta.tgz.unpacked",
    ]
    assert _members(out / "01-alpha.tgz") == {
        "smoke-out/a.txt",
        "smoke-out/stores/e/data.lance",
    }
    assert _members(out / "02-beta.tgz") == {"smoke-out/b.txt"}
    digest = _sha(out / "01-alpha.tgz")
    assert (out / "01-alpha.tgz.sha256").read_text() == f"{digest}  01-alpha.tgz\n"
    assert f"== alpha: packed 01-alpha.tgz {digest}" in result.stdout


def test_the_sha256_file_is_written_after_the_tarball_is_complete(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, TWO, PATH=_tar_stub(tmp_path))
    assert result.returncode == 0, result.stdout
    first = (tmp_path / "ls-at-tar.1").read_text()
    second = (tmp_path / "ls-at-tar.2").read_text()
    assert "01-alpha.tgz.sha256" not in first
    assert "02-beta.tgz.sha256" not in second
    assert not list(_stage_out(tmp_path).glob("*.tmp"))


@pytest.mark.parametrize(
    ("stages", "packed"),
    [
        ('!setup touch "$OUT_DIR/s.txt"\ngood touch "$OUT_DIR/g.txt"\n', ["02-good"]),
        (
            "bg sh -c 'sleep 30 >/dev/null 2>&1 & echo $! >> \"$BACKGROUND_PIDS\"'\n"
            'good touch "$OUT_DIR/g.txt"\n',
            ["02-good"],
        ),
        ('bad sh -c \'touch "$OUT_DIR/x"; exit 3\'\ngood touch "$OUT_DIR/g.txt"\n', ["02-good"]),
        ("legal sh -c 'exit 77'\ngood touch \"$OUT_DIR/g.txt\"\n", ["02-good"]),
        ("quiet true\n", ["01-quiet"]),
    ],
    ids=["bang-stage", "background-stage", "failed-stage", "skipped-stage", "no-file-stage"],
)
def test_only_a_stage_that_ends_ok_and_is_restorable_is_packed(
    tmp_path: Path, stages: str, packed: list[str]
) -> None:
    result, _ = _run(tmp_path, stages)
    names = sorted(p.name for p in _stage_out(tmp_path).glob("*.tgz"))
    assert names == [f"{tag}.tgz" for tag in packed], result.stdout
    assert all((_stage_out(tmp_path) / f"{n}.sha256").is_file() for n in names)


def test_a_stage_that_wrote_no_file_gets_an_empty_tarball(tmp_path: Path) -> None:
    _run(tmp_path, "quiet true\n")
    assert _members(_stage_out(tmp_path) / "01-quiet.tgz") == set()


def test_the_spare_copy_gets_the_tarball_and_the_sha256(tmp_path: Path) -> None:
    spare = tmp_path / "spare"
    result, _ = _run(tmp_path, TWO, SPARE_DIR=str(spare))
    assert result.returncode == 0, result.stdout
    for name in ("01-alpha.tgz", "01-alpha.tgz.sha256", "02-beta.tgz", "02-beta.tgz.sha256"):
        assert (spare / name).read_bytes() == (_stage_out(tmp_path) / name).read_bytes()
    assert "no spare copy" not in result.stdout


def test_an_empty_spare_dir_logs_one_line_and_goes_on(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, TWO + 'gamma touch "$OUT_DIR/c.txt"\n', SPARE_DIR="")
    assert result.returncode == 0
    assert result.stdout.count("no spare copy") == 1
    assert len(list(_stage_out(tmp_path).glob("*.tgz"))) == 3


def test_a_failed_spare_copy_is_logged_and_the_chain_goes_on(tmp_path: Path) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_text("a file, not a folder\n", encoding="utf-8")
    result, _ = _run(tmp_path, TWO, SPARE_DIR=str(blocked / "spare"))
    assert result.returncode == 0
    assert "alpha: spare copy FAILED" in result.stdout
    assert (_stage_out(tmp_path) / "02-beta.tgz.sha256").is_file()


def test_a_fresh_launch_refuses_when_old_stage_tarballs_exist(tmp_path: Path) -> None:
    _run(tmp_path, "a sh -c 'echo x >> \"$OUT_DIR/a.count\"'\n")
    result, log = _run(tmp_path, "a sh -c 'echo x >> \"$OUT_DIR/a.count\"'\n")
    assert result.returncode == 2
    assert "RESUME=1" in result.stdout and "stage-out" in result.stdout
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x"]
    assert len(_lines(log)) == 1  # only the first launch stopped a pod
    assert (_stage_out(tmp_path) / "01-a.tgz").is_file()


COUNT = 'a sh -c \'echo x >> "$OUT_DIR/a.count"; echo A > "$OUT_DIR/a.out"\'\n'


def test_resume_skips_a_stage_with_a_matching_tarball(tmp_path: Path) -> None:
    _run(tmp_path, COUNT + "b sh -c 'echo y >> \"$OUT_DIR/b.count\"'\n")
    result, _ = _run(tmp_path, COUNT + "b sh -c 'echo y >> \"$OUT_DIR/b.count\"'\n", RESUME="1")
    assert result.returncode == 0, result.stdout
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x"]
    assert _lines(tmp_path / "smoke-out" / "b.count") == ["y"]
    assert "== a: SKIPPED (resume, done in 01-a.tgz)" in result.stdout
    assert "failed stages: none; skipped: none; resumed: a b" in result.stdout
    assert (_stage_out(tmp_path) / "01-a.tgz").is_file()  # a resume keeps the folder


def test_resume_without_a_tarball_runs_the_stage_and_logs_no_resumed_stage(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, COUNT, RESUME="1")
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x"]
    assert "failed stages: none; skipped: none; resumed: none" in result.stdout


def test_resume_never_skips_a_bang_stage(tmp_path: Path) -> None:
    stages = "!setup sh -c 'echo x >> \"$OUT_DIR/s.count\"'\n" + COUNT
    _run(tmp_path, stages)
    # Plant a matching tarball for the "!" stage: a resume must still run the stage.
    out = _stage_out(tmp_path)
    shutil.copy(out / "02-a.tgz", out / "01-setup.tgz")
    (out / "01-setup.tgz.sha256").write_text(f"{_sha(out / '01-setup.tgz')}  01-setup.tgz\n")
    result, _ = _run(tmp_path, stages, RESUME="1")
    assert _lines(tmp_path / "smoke-out" / "s.count") == ["x", "x"]
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x"]
    assert "resumed: a" in result.stdout


def _failing_pack_path(tmp_path: Path) -> str:
    """A ``PATH`` whose ``tar`` fails the stage pack (it alone passes --null), not the final one."""
    stub = tmp_path / "tar-bin"
    stub.mkdir()
    real = shutil.which("tar")
    body = f'#!/usr/bin/env bash\ncase "$*" in *--null*) exit 1 ;; esac\nexec {real} "$@"\n'
    (stub / "tar").write_text(body, encoding="utf-8")
    (stub / "tar").chmod(0o755)
    return f"{tmp_path / 'bin'}:{stub}:{os.environ['PATH']}"


def test_a_failed_pack_is_logged_and_counts_as_a_failed_stage(tmp_path: Path) -> None:
    path = _failing_pack_path(tmp_path)
    result, log = _run(tmp_path, TWO, PATH=path)
    assert result.returncode == 1, result.stdout
    assert "== alpha: PACK FAILED" in result.stdout and "== beta: PACK FAILED" in result.stdout
    assert "== finish: failed stages: alpha:pack beta:pack;" in result.stdout
    assert (tmp_path / "smoke-out" / "b.txt").is_file()  # the chain went on
    assert list(_stage_out(tmp_path).glob("*.tgz*")) == []
    assert (tmp_path / "work" / "test-session-out.tgz").is_file()
    assert len(_lines(log)) == 1  # no keep rule: the pod stops


def test_a_failed_pack_keeps_the_pod_with_keep_pod_on_fail(tmp_path: Path) -> None:
    path = _failing_pack_path(tmp_path)
    result, log = _run(tmp_path, TWO, PATH=path, KEEP_POD_ON_FAIL="1")
    assert "POD_KEPT: failed stages: alpha:pack beta:pack; fix" in result.stdout
    assert not log.exists()


def test_resume_restores_from_the_spare_when_only_the_spare_has_it(tmp_path: Path) -> None:
    spare = tmp_path / "spare"
    _run(tmp_path, COUNT, SPARE_DIR=str(spare))
    shutil.rmtree(_stage_out(tmp_path))
    (tmp_path / "smoke-out" / "a.out").unlink()
    result, _ = _run(tmp_path, COUNT, RESUME="1", SPARE_DIR=str(spare))
    assert result.returncode == 0, result.stdout
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x"]  # not run again
    assert (tmp_path / "smoke-out" / "a.out").read_text() == "A\n"  # unpacked again
    assert f"== a: RESTORED from {spare}/01-a.tgz, SKIPPED (resume)" in result.stdout
    assert (_stage_out(tmp_path) / "01-a.tgz.sha256").is_file()
    assert "resumed: a" in result.stdout


def _corrupt(path: Path) -> None:
    path.write_bytes(path.read_bytes() + b"\0")


def test_resume_runs_the_stage_again_when_the_tarball_hash_does_not_match(tmp_path: Path) -> None:
    _run(tmp_path, COUNT)
    _corrupt(_stage_out(tmp_path) / "01-a.tgz")
    result, _ = _run(tmp_path, COUNT, RESUME="1")
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x", "x"]
    assert "== a: tarball hash mismatch, running it again" in result.stdout
    assert "resumed: none" in result.stdout


def test_resume_uses_the_spare_when_only_the_local_tarball_is_damaged(tmp_path: Path) -> None:
    spare = tmp_path / "spare"
    _run(tmp_path, COUNT, SPARE_DIR=str(spare))
    _corrupt(_stage_out(tmp_path) / "01-a.tgz")
    result, _ = _run(tmp_path, COUNT, RESUME="1", SPARE_DIR=str(spare))
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x"]
    assert "RESTORED from" in result.stdout
    assert _sha(_stage_out(tmp_path) / "01-a.tgz") == _sha(spare / "01-a.tgz")


def test_resume_runs_the_stage_again_when_the_spare_hash_does_not_match(tmp_path: Path) -> None:
    spare = tmp_path / "spare"
    _run(tmp_path, COUNT, SPARE_DIR=str(spare))
    shutil.rmtree(_stage_out(tmp_path))
    _corrupt(spare / "01-a.tgz")
    result, _ = _run(tmp_path, COUNT, RESUME="1", SPARE_DIR=str(spare))
    assert _lines(tmp_path / "smoke-out" / "a.count") == ["x", "x"]
    assert "tarball hash mismatch, running it again" in result.stdout


def test_the_finish_line_names_no_resumed_stage_on_a_normal_run(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, "only true\n")
    assert "== finish: failed stages: none; skipped: none; resumed: none" in result.stdout


def test_keep_pod_on_fail_keeps_the_pod_after_a_failed_stage(tmp_path: Path) -> None:
    result, log = _run(
        tmp_path,
        "first false\nsecond true\n",
        KEEP_POD_ON_FAIL="1",
        stub_sleep=True,
        STOP_GRACE_MIN="1",
        PULL_POLL_S="10",
        STUB_PULLED_AFTER="2",
    )
    kept = [x for x in result.stdout.splitlines() if POD_KEPT in x]
    assert len(kept) == 1 and kept[0].endswith(KEPT_TAIL) and "first" in kept[0]
    assert not log.exists() and not (tmp_path / "curl.log").exists()
    assert (tmp_path / "work" / "test-session-out.tgz.sha256").is_file()
    assert (tmp_path / "sleeps").read_text().strip() == "2"  # it still waited for PULLED
    assert result.returncode == 1


def test_keep_pod_on_fail_keeps_the_pod_after_a_signal(tmp_path: Path) -> None:
    result, log = _run(
        tmp_path, 'killer kill -TERM "$SESSION_PID"; sleep 1\n', KEEP_POD_ON_FAIL="1"
    )
    kept = [x for x in result.stdout.splitlines() if POD_KEPT in x]
    assert len(kept) == 1 and kept[0].endswith(KEPT_TAIL) and "signal" in kept[0]
    assert not log.exists()
    assert (tmp_path / "work" / "test-session-out.tgz").is_file()
    assert result.returncode != 3


def test_keep_pod_on_fail_keeps_the_pod_after_a_failed_bang_stage(tmp_path: Path) -> None:
    result, log = _run(tmp_path, "!setup false\n", KEEP_POD_ON_FAIL="1")
    assert POD_KEPT in result.stdout and not log.exists()


@pytest.mark.parametrize("keep", ["1", "0", None], ids=["keep-on", "keep-off", "keep-unset"])
def test_a_run_with_every_stage_ok_always_stops_the_pod(tmp_path: Path, keep: str | None) -> None:
    result, log = _run(tmp_path, "only true\n", KEEP_POD_ON_FAIL=keep)
    assert result.returncode == 0
    assert POD_KEPT not in result.stdout
    assert [x.split(" tarball=")[0] for x in _lines(log)] == ["pod stop pod123"]


@pytest.mark.parametrize("keep", ["0", None], ids=["keep-off", "keep-unset"])
def test_without_keep_pod_on_fail_a_failure_still_stops_the_pod(
    tmp_path: Path, keep: str | None
) -> None:
    result, log = _run(tmp_path, "first false\n", KEEP_POD_ON_FAIL=keep)
    assert result.returncode == 1
    assert POD_KEPT not in result.stdout
    assert [x.split(" tarball=")[0] for x in _lines(log)] == ["pod stop pod123"]


def test_dry_run_prints_the_pack_and_spare_steps_and_runs_nothing(tmp_path: Path) -> None:
    spare = tmp_path / "spare"
    stages = '!setup touch "$OUT_DIR/s"\nalpha touch "$OUT_DIR/a"\n'
    result, log = _run(tmp_path, stages, DRY_RUN="1", SPARE_DIR=str(spare))
    out = result.stdout
    assert result.returncode == 0
    assert "02-alpha.tgz" in out and "01-setup.tgz" not in out
    assert "pack" in out and str(spare) in out
    assert not (tmp_path / "work").exists() and not spare.exists() and not log.exists()


# gpulog-style launcher: a loop appends to a file under OUT_DIR for the whole session.
LOOP = (
    'bg sh -c \'echo x > "$OUT_DIR/bg.log"; '
    '(while :; do echo x >> "$OUT_DIR/bg.log"; sleep 0.1; done) '
    '>/dev/null 2>&1 & echo $! >> "$BACKGROUND_PIDS"\'\n'
)
OWN = "ok sh -c 'sleep 0.5; touch \"$OUT_DIR/g.txt\"'\n"


def test_a_file_a_background_stage_keeps_writing_is_left_out_of_later_tarballs(
    tmp_path: Path,
) -> None:
    result, _ = _run(tmp_path, LOOP + OWN)
    assert result.returncode == 0, result.stdout
    assert "PACK FAILED" not in result.stdout
    assert _members(_stage_out(tmp_path) / "02-ok.tgz") == {"smoke-out/g.txt"}
    assert not (_stage_out(tmp_path) / "01-bg.tgz").exists()


def test_a_fresh_launch_forgets_the_background_files_of_an_earlier_run(tmp_path: Path) -> None:
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "background.files").write_text("smoke-out/g.txt\n", encoding="utf-8")
    _run(tmp_path, OWN)
    assert _members(_stage_out(tmp_path) / "01-ok.tgz") == {"smoke-out/g.txt"}


def test_a_resume_keeps_the_background_files(tmp_path: Path) -> None:
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "background.files").write_text("smoke-out/g.txt\n", encoding="utf-8")
    _run(tmp_path, OWN + 'own touch "$OUT_DIR/h.txt"\n', RESUME="1")
    assert _members(_stage_out(tmp_path) / "01-ok.tgz") == set()
    assert _members(_stage_out(tmp_path) / "02-own.tgz") == {"smoke-out/h.txt"}
