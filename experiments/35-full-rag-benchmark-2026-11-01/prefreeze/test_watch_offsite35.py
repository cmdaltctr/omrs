"""Checks on the off-site settings and the Mac-side check of mac_watch35.py.

The watcher writes ``OFFSITE_REQUIRED`` and ``R2_PREFIX`` into ``session.env`` (or
``OFFSITE_REQUIRED=0`` with ``--no-offsite``). At the end it reads each ``.sha256`` object of
the stage and final tarballs that the Mac holds from the private R2 bucket (``curl
--aws-sigv4``, the key pair on standard input) and compares it with the local file. The fake
curl of r2_testkit35.py plays R2; the stubs of test_mac_watch35.py play the pod. No test
reaches RunPod, Cloudflare or any network host.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import r2_testkit35 as r2
from test_mac_watch35 import POD, Session, _last
from test_watch_resume35 import _again
from test_watch_stages35 import TAG, _stage

KEY_FILE = Path(".config/omrs/secrets/r2-exp35.env")
KEY_TEXT = (
    f"R2_ACCESS_KEY_ID={r2.KEY_ID}\nR2_SECRET_ACCESS_KEY={r2.SECRET}\nR2_ENDPOINT={r2.ENDPOINT}\n"
)
STEPS = ["+[00:00:01] == a: start", "done"]


def _on(tmp_path: Path, steps: list[str] | None = None, mode: int = 0o600) -> Session:
    """A session with the off-site check on: a key file, the fake curl, a mirror of the pod."""
    s = Session(tmp_path, STEPS if steps is None else steps)
    s.base_args = []
    key = s.home / KEY_FILE
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_text(KEY_TEXT, encoding="utf-8")
    key.chmod(mode)
    (tmp_path / "curl.mirror").write_text(str(s.work), encoding="utf-8")
    return s


def _run(s: Session, *args: str):  # noqa: ANN202
    return s.run(*args, PATH=r2.install(s.tmp))


def _prefix(s: Session) -> str:
    return f"{s.folder().name}/{POD}"


def test_session_env_names_the_requirement_and_the_prefix(tmp_path: Path) -> None:
    s = _on(tmp_path)
    result = _run(s)
    assert result.returncode == 0, result.stdout + result.stderr
    env = (s.work / "session.env").read_text(encoding="utf-8").splitlines()
    assert "OFFSITE_REQUIRED=1" in env
    assert f"R2_PREFIX={_prefix(s)}" in env
    assert not any(x.startswith("OFFSITE_REQUIRED=0") for x in env)


def test_no_offsite_writes_the_flag_off_and_the_summary_says_so(tmp_path: Path) -> None:
    s = Session(tmp_path, STEPS)  # no key file, no fake curl: the check never runs
    result = s.run()
    assert result.returncode == 0, result.stdout + result.stderr
    env = (s.work / "session.env").read_text(encoding="utf-8").splitlines()
    assert "OFFSITE_REQUIRED=0" in env and not any(x.startswith("R2_PREFIX") for x in env)
    assert "off-site: OFF (--no-offsite)" in result.stdout
    assert _last(result) == f"DELETE_POD_NOW {POD}"
    assert not s.log("curl.argv")


def test_every_object_matching_gives_the_verified_line_and_the_delete_path(tmp_path: Path) -> None:
    s = _on(tmp_path)
    _stage(s)
    _stage(s, "02-next")
    result = _run(s)
    assert result.returncode == 0, result.stdout + result.stderr
    line = f"off-site: 2 stage, 1 final verified in r2://{r2.BUCKET}/{_prefix(s)}"
    assert line in result.stdout
    assert "OFFSITE_NOT_VERIFIED" not in result.stdout
    assert _last(result) == f"DELETE_POD_NOW {POD}"
    gets = r2.lines(tmp_path, "curl.calls")
    assert all(x.startswith("GET") for x in gets) and len(gets) == 3
    assert f"GET {r2.BUCKET}/{_prefix(s)}/stage-out/{TAG}.tgz.sha256" in gets
    assert f"GET {r2.BUCKET}/{_prefix(s)}/final/test-session-out.tgz.sha256" in gets


def test_one_object_that_differs_gives_not_verified_and_keeps_the_pod(tmp_path: Path) -> None:
    s = _on(tmp_path)
    _stage(s)
    _stage(s, "02-next")
    (tmp_path / "curl.corrupt").write_text("02-next", encoding="utf-8")
    result = _run(s)
    assert "!!! OFFSITE_NOT_VERIFIED: 02-next.tgz" in result.stdout
    assert TAG not in result.stdout.split("OFFSITE_NOT_VERIFIED")[1].splitlines()[0]
    assert "off-site:" in result.stdout and "verified in" not in result.stdout
    assert _last(result).startswith(f"KEEP_POD {POD}")
    assert "DELETE_POD_NOW" not in result.stdout


def test_a_missing_object_gives_not_verified_and_keeps_the_pod(tmp_path: Path) -> None:
    s = _on(tmp_path)
    _stage(s)
    (tmp_path / "curl.fail-match").write_text("final/", encoding="utf-8")
    result = _run(s)
    assert "!!! OFFSITE_NOT_VERIFIED: test-session-out.tgz" in result.stdout
    assert _last(result).startswith(f"KEEP_POD {POD}")


def test_a_pod_without_a_final_tarball_checks_only_the_stage_tarballs(tmp_path: Path) -> None:
    s = _on(tmp_path, ["+[00:00:01] == a: start (timeout 600s)", "term"])
    _stage(s)
    result = _run(s)
    assert result.returncode == 12, result.stdout + result.stderr
    assert f"off-site: 1 stage, 0 final verified in r2://{r2.BUCKET}/" in result.stdout


def test_the_check_also_runs_when_the_watcher_attaches(tmp_path: Path) -> None:
    s = _on(tmp_path, ["+[00:00:01] == a: start (timeout 600s)", "term"])
    _stage(s)
    assert _run(s).returncode == 12  # the Mac leaves
    _again(s, ["+[00:00:05] == b: start (timeout 600s)", "done"])
    result = _run(s, "--attach")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "off-site: 1 stage, 1 final verified in r2://" in result.stdout
    assert _last(result) == f"DELETE_POD_NOW {POD}"


@pytest.mark.parametrize(("mode", "word"), [(0o644, "mode 600"), (0o640, "mode 600")])
def test_a_key_file_that_others_can_read_is_a_problem(tmp_path: Path, mode: int, word: str) -> None:
    s = _on(tmp_path, mode=mode)
    result = _run(s)
    assert result.returncode == 2
    assert "REFUSED" in result.stdout and str(KEY_FILE) in result.stdout and word in result.stdout
    assert not s.log("ssh.log") and not s.log("scp.log")
    dry = _run(s, "--dry-run")
    assert dry.returncode == 2 and "PROBLEM: R2 key file" in dry.stdout and word in dry.stdout


def test_a_missing_key_file_is_a_problem_unless_no_offsite(tmp_path: Path) -> None:
    s = _on(tmp_path)
    (s.home / KEY_FILE).unlink()
    dry = _run(s, "--dry-run")
    assert dry.returncode == 2
    assert f"PROBLEM: R2 key file {s.home / KEY_FILE} not found" in dry.stdout
    real = _run(s)
    assert real.returncode == 2 and "REFUSED" in real.stdout
    assert not s.log("ssh.log") and not s.log("scp.log")
    assert _run(s, "--no-offsite", "--dry-run").returncode == 0


def test_a_key_file_without_one_name_is_a_problem_and_shows_no_value(tmp_path: Path) -> None:
    s = _on(tmp_path)
    (s.home / KEY_FILE).write_text(f"R2_ACCESS_KEY_ID={r2.KEY_ID}\n", encoding="utf-8")
    (s.home / KEY_FILE).chmod(0o600)
    result = _run(s, "--dry-run")
    assert result.returncode == 2
    assert "R2_SECRET_ACCESS_KEY" in result.stdout and "R2_ENDPOINT" in result.stdout
    assert not any(x in result.stdout + result.stderr for x in (r2.KEY_ID, r2.ENDPOINT))


def test_the_dry_run_shows_the_off_site_values_and_no_secret(tmp_path: Path) -> None:
    s = _on(tmp_path)
    dry = _run(s, "--dry-run")
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert "OFFSITE_REQUIRED=1" in dry.stdout and "R2_PREFIX=test-session-" in dry.stdout
    assert f"/{POD}" in dry.stdout and "off-site: at the end" in dry.stdout
    assert not any(x in dry.stdout + dry.stderr for x in (*r2.SECRETS, r2.ENDPOINT))
    off = _run(s, "--dry-run", "--no-offsite")
    assert "OFFSITE_REQUIRED=0" in off.stdout and "R2_PREFIX" not in off.stdout
    assert not s.log("curl.argv") and not s.log("ssh.log")


def test_the_secret_is_never_in_an_argument_the_output_or_a_file(tmp_path: Path) -> None:
    s = _on(tmp_path)
    _stage(s)
    result = _run(s)
    argv = "\n".join(r2.lines(tmp_path, "curl.argv"))
    seen = result.stdout + result.stderr + argv
    for path in (s.folder()).rglob("*"):
        if path.is_file() and path.suffix not in (".tgz",):
            seen += path.read_text(errors="replace")
    assert not any(x in seen for x in r2.SECRETS)
    assert "--aws-sigv4 aws:amz:auto:s3 -K -" in argv
    assert f'user = "{r2.KEY_ID}:{r2.SECRET}"' in "\n".join(r2.lines(tmp_path, "curl.stdin"))
    assert os.environ.get("R2_SECRET_ACCESS_KEY") is None
