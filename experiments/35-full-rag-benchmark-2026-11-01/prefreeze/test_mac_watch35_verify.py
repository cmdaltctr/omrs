"""Checks on the fix check variant of mac_watch35.py: ``--stages`` and ``--extra-input``.

The same stubs as test_mac_watch35.py play the pod (see that file). No test reaches
RunPod or any network host.
"""

from __future__ import annotations

from pathlib import Path

import mac_watch35
import pytest
from test_mac_watch35 import HERE, KEY_BODY, POD, Session, _last, _sha

VERIFY = "verify_session_stages.txt"
REMOTE = f"/workspace/omrs/experiments/{HERE.parent.name}/prefreeze"


def _answers(tmp: Path) -> Path:
    extra = tmp / "fb-answers.tgz"
    extra.write_bytes(b"not really a tarball, only bytes to copy\n")
    return extra


def _folders(s: Session, prefix: str) -> list[Path]:
    return sorted((s.root / "experiments" / HERE.parent.name).glob(f"{prefix}-*"))


def test_a_verify_session_ships_the_extra_input_and_names_its_stages_file(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    extra = _answers(tmp_path)
    result = s.run("--stages", VERIFY, "--extra-input", str(extra))
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert _last(result) == f"DELETE_POD_NOW {POD}"
    (folder,) = _folders(s, "verify-session")
    assert _folders(s, "test-session") == []
    assert (folder / "test-session-out.tgz").is_file()
    sent = s.pod / "workspace/inputs/fb-answers.tgz"
    assert sent.read_bytes() == extra.read_bytes()
    assert (folder / "inputs/fb-answers.tgz").read_bytes() == extra.read_bytes()  # as sent
    checks = [line for line in s.log("ssh.log") if "sha256sum -c" in line]
    assert len(checks) == 1 and f"{_sha(extra)} fb-answers.tgz" in checks[0]
    env = (s.pod / "workspace/session.env").read_text(encoding="utf-8").splitlines()
    remote = REMOTE.replace("/workspace", str(s.pod / "workspace"))
    assert env == [f"COMMIT={s.commit}", "STOP_GRACE_MIN=120", f"STAGES_FILE={remote}/{VERIFY}"]
    assert KEY_BODY not in output


def test_the_default_session_names_the_test_session_stages_and_ships_no_extra(
    tmp_path: Path,
) -> None:
    s = Session(tmp_path, ["done"])
    result = s.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert len(_folders(s, "test-session")) == 1
    env = (s.pod / "workspace/session.env").read_text(encoding="utf-8").splitlines()
    assert env[-1].endswith("/prefreeze/test_session_stages.txt")
    names = sorted(p.name for p in (s.pod / "workspace/inputs").iterdir())
    assert names == ["classify-examples.json", "exp35-inputs.tgz", "exp35-inputs.tgz.sha256"]


def test_an_unknown_stages_file_or_a_missing_extra_input_is_refused_before_ssh(
    tmp_path: Path,
) -> None:
    s = Session(tmp_path, ["done"])
    for args, word in (
        (["--stages", "no_such_stages.txt"], "no_such_stages.txt"),
        (["--stages", "../plan.json"], "../plan.json"),
        (["--stages", "launch35.sh"], "launch35.sh"),  # in prefreeze/, but not a stages file
        (["--extra-input", str(tmp_path / "absent.tgz")], "absent.tgz"),
    ):
        result = s.run(*args)
        assert result.returncode == 2, args
        assert "REFUSED" in result.stdout and word in result.stdout, args
        assert _last(result) == f"DELETE_POD_NOW {POD}"
    assert not s.log("ssh.log") and not s.log("scp.log")
    assert not (s.root / "experiments" / HERE.parent.name).exists()


@pytest.mark.parametrize(
    "name", ["exp35-inputs.tgz", "exp35-inputs.tgz.sha256", "classify-examples.json"]
)
@pytest.mark.parametrize("dry_run", [False, True])
def test_an_extra_input_named_like_a_generated_input_is_refused_before_any_work(
    tmp_path: Path, name: str, dry_run: bool
) -> None:
    """A clash would overwrite the generated tarball, its hash file or the examples."""
    s = Session(tmp_path, ["done"])
    clash = tmp_path / "elsewhere" / name
    clash.parent.mkdir()
    clash.write_bytes(b"would replace a generated input\n")
    result = s.run("--extra-input", str(clash), *(["--dry-run"] if dry_run else []))
    assert result.returncode == 2, result.stdout + result.stderr
    assert name in result.stdout and "generated input" in result.stdout
    assert not s.log("ssh.log") and not s.log("scp.log")
    assert not (s.root / "experiments" / HERE.parent.name).exists()
    assert _last(result).endswith(f"DELETE_POD_NOW {POD}")


def test_the_dry_run_names_the_stages_file_and_the_extra_input(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    extra = _answers(tmp_path)
    result = s.run("--dry-run", "--stages", VERIFY, "--extra-input", str(extra))
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"STAGES_FILE={REMOTE}/{VERIFY}" in result.stdout
    assert f"{extra} as fb-answers.tgz" in result.stdout
    assert "verify-session-" in result.stdout
    assert not s.log("ssh.log") and not s.log("scp.log")


def test_launch_reads_the_stages_file_from_session_env_before_its_default() -> None:
    launch = (HERE / "launch35.sh").read_text(encoding="utf-8")
    sourced = launch.index('. "$SESSION_ENV"')
    default = launch.index('STAGES_FILE="${STAGES_FILE:-$HERE/test_session_stages.txt}"')
    assert sourced < default
    assert (HERE / VERIFY).is_file() and mac_watch35.SESSION_ENV == "/workspace/session.env"
