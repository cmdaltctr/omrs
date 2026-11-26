"""The watcher sends the GLM-5.3 base URL to the pod and prints it nowhere (owner, 2026-11-26).

Rules under test: the owner's mode-600 file on the Mac goes to the pod's mode-600
``/root/exp35-work/.zai_env`` through ssh standard input, so the value is on no command
line, in no log and in no file of the results folder; the dry run shows the step
without the value; a missing file, a file other users can read, or a value whose
SHA-256 is not the plan pin is a problem before any remote step.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from test_mac_watch35 import ZAI_URL, Session


def _everything(s: Session, result: object) -> str:
    logs = "".join("\n".join(s.log(n)) for n in ("ssh.log", "scp.log", "tmux.log"))
    return logs + result.stdout + result.stderr  # type: ignore[attr-defined]


def test_the_base_url_reaches_the_pod_in_a_mode_600_file_and_nowhere_else(
    tmp_path: Path,
) -> None:
    s = Session(tmp_path, ["done"])
    result = s.run()
    assert result.returncode == 0, result.stdout + result.stderr
    sent = s.work / ".zai_env"
    assert sent.read_text(encoding="utf-8") == f"OMRS_EXP35_ZAI_BASE_URL={ZAI_URL}\n"
    assert stat.S_IMODE(sent.stat().st_mode) == 0o600
    assert ZAI_URL not in _everything(s, result)
    leaks = [p for p in s.folder().rglob("*") if p.is_file() and ZAI_URL.encode() in p.read_bytes()]
    assert leaks == []


def test_the_dry_run_names_the_step_and_not_the_value(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    result = s.run("--dry-run")
    assert result.returncode == 0, result.stdout
    assert "/root/exp35-work/.zai_env" in result.stdout and "0 problem(s)" in result.stdout
    assert ZAI_URL not in result.stdout + result.stderr


@pytest.mark.parametrize("broken", ["missing", "mode", "hash"])
def test_a_bad_base_url_file_is_a_problem_before_any_remote_step(
    tmp_path: Path, broken: str
) -> None:
    s = Session(tmp_path, ["done"])
    if broken == "missing":
        s.zai.unlink()
    elif broken == "mode":
        s.zai.chmod(0o644)
    else:
        s.zai.write_text("https://other.example.invalid/v4\n", encoding="utf-8")
    result = s.run()
    assert result.returncode == 2
    assert "zai-exp35.base_url" in result.stdout
    assert not s.log("ssh.log")
    assert ZAI_URL not in result.stdout + result.stderr
