"""Checks on the off-site copy of the chain (offsite35.sh, hooked into pod_test_session.sh).

Why: a lost pod or a lost Mac must not lose results. After each stage and at the end, the
chain uploads to a private Cloudflare R2 bucket with ``curl --aws-sigv4``. The secret goes
to curl on standard input (``-K -``), never in an argument or the log. The runs use the fake
curl of r2_testkit35.py and the stubs of test_pod_test_session_script.py.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import r2_testkit35 as r2
from test_pod_test_session_script import _lines, _run

PREFIX = "test-session-2026-11-27/pod999"
STAGES = 'a touch "$OUT_DIR/a.txt"\nb touch "$OUT_DIR/b.txt"\n'
ON = {"OFFSITE_REQUIRED": "1", "R2_PREFIX": PREFIX, "OFFSITE_BACKOFF": "0 0"}


def _go(tmp_path: Path, stages: str = STAGES, **env: str | None):  # noqa: ANN202
    """Run the chain with the fake curl and the R2 values."""
    return _run(tmp_path, stages, PATH=r2.install(tmp_path), **{**r2.R2, **ON, **env})


def _put_ok(tmp_path: Path) -> list[str]:
    return [x.split("/", 1)[1] for x in r2.lines(tmp_path, "curl.ok") if x.startswith("PUT")]


def _stage_calls(tmp_path: Path, tag: str) -> list[str]:
    return [x.rsplit("/", 1)[1] for x in _put_ok(tmp_path) if f"/stage-out/{tag}" in x]


def test_a_stage_is_uploaded_as_tgz_then_commit_then_sha256_last(tmp_path: Path) -> None:
    result, _ = _go(tmp_path)
    assert result.returncode == 0, result.stdout
    assert _stage_calls(tmp_path, "01-a") == ["01-a.tgz", "01-a.tgz.commit", "01-a.tgz.sha256"]
    assert _stage_calls(tmp_path, "02-b") == ["02-b.tgz", "02-b.tgz.commit", "02-b.tgz.sha256"]
    sent = r2.bucket(tmp_path, *PREFIX.split("/"), "stage-out", "01-a.tgz.sha256")
    local = tmp_path / "work" / "stage-out" / "01-a.tgz.sha256"
    assert sent.read_bytes() == local.read_bytes()
    line = f"== a: off-site copy in r2://{r2.BUCKET}/{PREFIX}/stage-out/01-a.tgz"
    assert line in result.stdout


def test_a_put_is_retried_up_to_three_times_and_then_works(tmp_path: Path) -> None:
    (tmp_path / "curl.fail").write_text("2\n", encoding="utf-8")  # the probe fails twice
    result, _ = _go(tmp_path)
    assert result.returncode == 0, result.stdout
    puts = [x for x in r2.lines(tmp_path, "curl.calls") if x.startswith("PUT")]
    assert puts[:3] == [f"PUT {r2.BUCKET}/{PREFIX}/probe.txt"] * 3  # two failures, one success
    assert "off-site copy FAILED" not in result.stdout


def test_three_failures_of_a_put_end_the_retries(tmp_path: Path) -> None:
    (tmp_path / "curl.fail-match").write_text("01-a.tgz", encoding="utf-8")
    result, _ = _go(tmp_path, OFFSITE_REQUIRED="0")
    first = [x for x in r2.lines(tmp_path, "curl.calls") if "stage-out/01-a.tgz" in x]
    assert first.count(f"PUT {r2.BUCKET}/{PREFIX}/stage-out/01-a.tgz") == 3 + 3  # try + retry
    assert result.returncode == 0  # not fatal
    failed = (tmp_path / "smoke-out" / "offsite-failed.txt").read_text().split()
    assert failed == [f"{PREFIX}/stage-out/01-a.tgz{x}" for x in ("", ".commit", ".sha256")]
    assert "== a: off-site copy FAILED (kept for a retry at the end)" in result.stdout


def test_a_failed_upload_goes_to_the_pending_list_and_is_retried_in_finish(
    tmp_path: Path,
) -> None:
    (tmp_path / "curl.fail").write_text("5\n", encoding="utf-8")  # more than the first 3 tries
    result, _ = _go(tmp_path, OFFSITE_REQUIRED="0")
    assert result.returncode == 0, result.stdout
    out = result.stdout
    assert "== a: off-site copy FAILED (kept for a retry at the end)" in out
    assert "== finish: off-site retry: 3 of 3 pending copies done" in out
    assert out.index("off-site retry") < out.index("off-site copy of the final outputs")
    assert _stage_calls(tmp_path, "01-a")[-3:] == ["01-a.tgz", "01-a.tgz.commit", "01-a.tgz.sha256"]
    assert "== finish: off-site copies failed: 0" in out
    assert not (tmp_path / "work" / "offsite.pending").read_text()


def test_a_stage_whose_tarball_failed_never_uploads_its_sha256_before_the_tarball(
    tmp_path: Path,
) -> None:
    (tmp_path / "curl.fail").write_text("3\n", encoding="utf-8")  # the 3 tries of 01-a.tgz
    result, _ = _go(tmp_path, OFFSITE_REQUIRED="0")
    assert "== a: off-site copy FAILED (kept for a retry at the end)" in result.stdout
    assert _stage_calls(tmp_path, "01-a") == ["01-a.tgz", "01-a.tgz.commit", "01-a.tgz.sha256"]


def test_the_final_outputs_go_up_before_the_wait_for_the_mac(tmp_path: Path) -> None:
    seen = tmp_path / "at-sleep"
    sleeper = tmp_path / "sleep-bin"
    sleeper.mkdir()
    final = r2.bucket(tmp_path, *PREFIX.split("/"), "final")
    (sleeper / "sleep").write_text(
        f'#!/usr/bin/env bash\nls -A "{final}" | tr "\\n" " " > "{seen}"\n', encoding="utf-8"
    )
    (sleeper / "sleep").chmod(0o755)
    path = f"{sleeper}:{r2.install(tmp_path)}"
    log = tmp_path / "work" / "test-session.log"
    log.parent.mkdir(parents=True)
    log.write_text("chain log\n", encoding="utf-8")
    result, _ = _run(
        tmp_path, STAGES, PATH=path, STOP_GRACE_MIN="1", PULL_POLL_S="30", **{**r2.R2, **ON}
    )
    assert result.returncode == 0, result.stdout
    assert set(seen.read_text().split()) == {
        "test-session-out.tgz",
        "test-session.log",
        "test-session-out.tgz.sha256",
    }
    assert (final / "test-session.log").read_text() == "chain log\n"
    finals = [x.rsplit("/", 1)[1] for x in _put_ok(tmp_path) if "/final/" in x]
    assert finals == ["test-session-out.tgz", "test-session.log", "test-session-out.tgz.sha256"]
    assert f"== finish: off-site copy of the final outputs in r2://{r2.BUCKET}/{PREFIX}/final/" in (
        result.stdout
    )
    assert "== finish: off-site copies failed: 0" in result.stdout


def test_a_failed_final_upload_is_counted_and_not_fatal(tmp_path: Path) -> None:
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "test-session.log").write_text("chain log\n", encoding="utf-8")
    (tmp_path / "curl.fail-match").write_text("/final/", encoding="utf-8")
    result, log = _go(tmp_path, OFFSITE_REQUIRED="0")
    assert result.returncode == 0, result.stdout
    assert "== finish: off-site copy of the final outputs FAILED" in result.stdout
    assert "== finish: off-site copies failed: 3" in result.stdout
    assert len(_lines(log)) == 1  # the pod still stops
    assert not [x for x in _put_ok(tmp_path) if "final/test-session-out.tgz.sha256" in x]


@pytest.mark.parametrize(
    "missing", ["R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_ENDPOINT", "R2_PREFIX"]
)
def test_a_required_offsite_with_a_missing_value_is_refused_before_the_first_stage(
    tmp_path: Path, missing: str
) -> None:
    result, log = _go(tmp_path, **{missing: ""})
    assert result.returncode == 2
    assert missing in result.stdout and "OFFSITE_REQUIRED" in result.stdout
    assert not (tmp_path / "smoke-out" / "a.txt").exists() and not log.exists()
    assert not any(s in result.stdout + result.stderr for s in r2.SECRETS)


def test_a_required_offsite_with_a_failed_probe_is_refused(tmp_path: Path) -> None:
    (tmp_path / "curl.fail-match").write_text("probe.txt", encoding="utf-8")
    result, log = _go(tmp_path)
    assert result.returncode == 2
    assert "off-site probe upload failed" in result.stdout
    assert not (tmp_path / "smoke-out" / "a.txt").exists() and not log.exists()


def test_the_probe_holds_the_commit_and_the_date(tmp_path: Path) -> None:
    result, _ = _go(tmp_path)
    assert result.returncode == 0, result.stdout
    probe = r2.bucket(tmp_path, *PREFIX.split("/"), "probe.txt").read_text().split()
    assert len(probe[0]) == 40 and len(probe[1]) == 10


def test_without_r2_values_and_not_required_one_line_is_logged_and_the_run_works(
    tmp_path: Path,
) -> None:
    result, log = _run(tmp_path, STAGES, PATH=r2.install(tmp_path))
    assert result.returncode == 0, result.stdout
    assert result.stdout.count("no off-site copy: R2 is not configured") == 1
    assert not r2.lines(tmp_path, "curl.calls") and len(_lines(log)) == 1
    assert (tmp_path / "work" / "stage-out" / "02-b.tgz.sha256").is_file()


def test_r2_values_without_the_requirement_still_upload(tmp_path: Path) -> None:
    result, _ = _go(tmp_path, OFFSITE_REQUIRED=None)
    assert result.returncode == 0 and _stage_calls(tmp_path, "01-a")
    assert "no off-site copy" not in result.stdout


def test_a_prefix_is_needed_before_any_upload_even_when_not_required(tmp_path: Path) -> None:
    result, _ = _go(tmp_path, OFFSITE_REQUIRED="0", R2_PREFIX=None)
    assert result.returncode == 0
    assert "no off-site copy: R2 is not configured" in result.stdout
    assert not r2.lines(tmp_path, "curl.calls")


def test_the_secret_is_in_the_config_on_stdin_only(tmp_path: Path) -> None:
    result, _ = _go(tmp_path)
    assert result.returncode == 0, result.stdout
    argv = "\n".join(r2.lines(tmp_path, "curl.argv"))
    everything = argv + result.stdout + result.stderr
    for work_file in (tmp_path / "work").rglob("*"):
        if work_file.is_file() and work_file.suffix not in (".tgz", ".sha256"):
            everything += work_file.read_text(errors="replace")
    assert not any(s in everything for s in r2.SECRETS)
    assert "--aws-sigv4 aws:amz:auto:s3 -K -" in argv
    assert f'user = "{r2.KEY_ID}:{r2.SECRET}"' in "\n".join(r2.lines(tmp_path, "curl.stdin"))


def test_the_dry_run_prints_each_upload_with_its_key_and_no_secret(tmp_path: Path) -> None:
    stages = '!setup touch "$OUT_DIR/s"\nalpha touch "$OUT_DIR/a"\n'
    result, _ = _go(tmp_path, stages, DRY_RUN="1")
    out = result.stdout
    assert result.returncode == 0, out
    assert f"r2://{r2.BUCKET}/{PREFIX}/stage-out/: 02-alpha.tgz, 02-alpha.tgz.commit" in out
    assert "02-alpha.tgz.commit" in out and "02-alpha.tgz.sha256" in out
    assert f"r2://{r2.BUCKET}/{PREFIX}/final/" in out and "probe.txt" in out
    assert not any(s in out for s in (*r2.SECRETS, r2.ENDPOINT))
    assert not r2.lines(tmp_path, "curl.calls") and not (tmp_path / "work").exists()


def test_a_stage_that_a_resume_skips_is_not_uploaded_again(tmp_path: Path) -> None:
    _go(tmp_path)
    first = len(_put_ok(tmp_path))
    result, _ = _go(tmp_path, RESUME="1")
    assert result.returncode == 0, result.stdout
    assert "== a: SKIPPED (resume, done in 01-a.tgz)" in result.stdout
    assert [x for x in _put_ok(tmp_path) if "/stage-out/" in x] == [
        x for x in _put_ok(tmp_path)[:first] if "/stage-out/" in x
    ]


# Each curl try is bounded, so a stalled connection ends and uses the retry path.
def test_each_try_has_a_connect_timeout_and_a_total_time_limit(tmp_path: Path) -> None:
    result, _ = _go(tmp_path)
    assert result.returncode == 0, result.stdout
    puts = [x for x in r2.lines(tmp_path, "curl.argv") if "-T " in x]
    assert puts and all("--connect-timeout 30 " in x and "--max-time 7200 " in x for x in puts)


def test_the_limits_can_be_set_and_a_stalled_try_is_retried(tmp_path: Path) -> None:
    (tmp_path / "curl.hang").write_text("2\n", encoding="utf-8")  # two tries stall
    result, _ = _go(tmp_path, OFFSITE_CONNECT_TIMEOUT="2", OFFSITE_MAX_TIME="1")
    assert result.returncode == 0, result.stdout
    argv = r2.lines(tmp_path, "curl.argv")
    assert all("--connect-timeout 2 " in x and "--max-time 1 " in x for x in argv if "-T " in x)
    probe = [x for x in r2.lines(tmp_path, "curl.calls") if x.endswith("/probe.txt")]
    assert len(probe) == 3 and r2.bucket(tmp_path, *PREFIX.split("/"), "probe.txt").is_file()


# A stage that a resume skips, or that --seed-from supplies, reaches the active prefix too.
def _resume_at(tmp_path: Path, prefix: str, **env: str | None):  # noqa: ANN202
    return _go(tmp_path, RESUME="1", R2_PREFIX=prefix, **env)


def _objects(tmp_path: Path, prefix: str, tag: str) -> list[str]:
    folder = tmp_path / "bucket" / r2.BUCKET / prefix / "stage-out"
    return sorted(p.name for p in folder.glob(f"{tag}.*")) if folder.is_dir() else []


def test_a_skipped_stage_is_uploaded_to_a_new_prefix_in_order(tmp_path: Path) -> None:
    _go(tmp_path)  # prefix one
    (tmp_path / "curl.ok").unlink()
    result, _ = _resume_at(tmp_path, "test-session-2026-11-27-seed1/pod555")
    assert result.returncode == 0, result.stdout
    assert "== a: SKIPPED (resume, done in 01-a.tgz)" in result.stdout
    assert _stage_calls(tmp_path, "01-a") == ["01-a.tgz", "01-a.tgz.commit", "01-a.tgz.sha256"]
    assert (
        "== a: off-site copy in r2://omrs-exp35-results/test-session-2026-11-27-seed1/pod555/"
        in (result.stdout)
    )
    want = (tmp_path / "work" / "stage-out" / "01-a.tgz.sha256").read_bytes()
    sent = tmp_path / "bucket" / r2.BUCKET / "test-session-2026-11-27-seed1/pod555/stage-out"
    assert (sent / "01-a.tgz.sha256").read_bytes() == want  # what the Mac check compares


def test_a_skipped_stage_with_the_same_prefix_and_hash_is_not_uploaded_twice(
    tmp_path: Path,
) -> None:
    _go(tmp_path)
    (tmp_path / "curl.ok").unlink()
    _resume_at(tmp_path, PREFIX)
    assert not [x for x in _put_ok(tmp_path) if "/stage-out/" in x]


def test_an_override_skip_is_uploaded_to_the_new_prefix(tmp_path: Path) -> None:
    _go(tmp_path)
    (tmp_path / "work" / "stage-out" / "01-a.tgz.commit").write_text("b" * 40 + "\n")
    (tmp_path / "curl.ok").unlink()
    result, _ = _resume_at(tmp_path, "other/pod2", RESUME_FROM_COMMIT="b" * 40)
    assert "RESUME_FROM_COMMIT)" in result.stdout
    assert _objects(tmp_path, "other/pod2", "01-a") == [
        "01-a.tgz", "01-a.tgz.commit", "01-a.tgz.sha256"
    ]  # fmt: skip


def test_a_seeded_stage_and_a_spare_restore_are_uploaded_to_the_new_prefix(
    tmp_path: Path,
) -> None:
    spare = tmp_path / "spare"
    _run(tmp_path, STAGES, SPARE_DIR=str(spare))  # no R2: the earlier pod
    for name in ("01-a", "02-b"):
        (tmp_path / "work" / "stage-out" / f"{name}.tgz.unpacked").unlink()  # a seeded pod
    shutil.rmtree(tmp_path / "work" / "stage-out" / "x", ignore_errors=True)
    (tmp_path / "work" / "stage-out" / "02-b.tgz").unlink()  # restored from the spare
    (tmp_path / "work" / "stage-out" / "02-b.tgz.sha256").unlink()
    result, _ = _resume_at(tmp_path, "seeded/pod3", SPARE_DIR=str(spare))
    assert result.returncode == 0, result.stdout
    assert "== a: unpacked 01-a.tgz (seeded)" in result.stdout and "RESTORED from" in result.stdout
    for tag in ("01-a", "02-b"):
        assert _objects(tmp_path, "seeded/pod3", tag) == [
            f"{tag}.tgz", f"{tag}.tgz.commit", f"{tag}.tgz.sha256"
        ]  # fmt: skip


# The final copy is complete or it is reported as failed.
def test_a_failed_log_snapshot_withholds_the_final_sha256_and_counts_as_a_failure(
    tmp_path: Path,
) -> None:
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "test-session.log").write_text("chain log\n", encoding="utf-8")
    (tmp_path / "work" / "offsite-final").write_text("a file, not a folder\n", encoding="utf-8")
    result, _ = _go(tmp_path, OFFSITE_REQUIRED="0")
    assert result.returncode == 0, result.stdout
    assert "== finish: off-site copy of the final outputs FAILED" in result.stdout
    assert "off-site copy of the final outputs in" not in result.stdout
    assert not [x for x in _put_ok(tmp_path) if "/final/test-session-out.tgz.sha256" in x]
    assert "== finish: off-site copies failed: 2" in result.stdout  # the log and the .sha256
    pending = (tmp_path / "work" / "offsite.pending").read_text()
    assert f"{PREFIX}/final/test-session.log" in pending
    assert f"{PREFIX}/final/test-session-out.tgz.sha256" in pending


# A failed pending copy blocks every later one: no .sha256 file goes up before its tarball.
def test_the_retry_stops_at_the_first_failure_and_keeps_every_later_entry(tmp_path: Path) -> None:
    (tmp_path / "curl.fail-match").write_text("stage-out/01-a.tgz", encoding="utf-8")
    (tmp_path / "curl.fail").write_text("3\n", encoding="utf-8")  # the 3 tries of 02-b.tgz
    result, _ = _go(tmp_path, OFFSITE_REQUIRED="0")
    assert result.returncode == 0, result.stdout
    assert "== finish: off-site retry: 0 of 6 pending copies done" in result.stdout
    assert not [x for x in _put_ok(tmp_path) if "/stage-out/02-b" in x]
    assert (tmp_path / "smoke-out" / "offsite-failed.txt").read_text().count("\n") == 6
