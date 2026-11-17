"""Checks on pod_test_session.sh, the script of the test pod session (task 9.1a, H-32).

The runs use stub commands only: a stub ``runpodctl`` first on ``PATH`` logs its
arguments and never reaches RunPod, so no test creates, stops or deletes a pod.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
PATH_SCRIPT = HERE / "pod_test_session.sh"
KEY = "rpa_SECRET_KEY_VALUE_123"


def _script() -> str:
    return PATH_SCRIPT.read_text(encoding="utf-8")


def _run(tmp_path: Path, stages: str, **env: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "runpodctl.log"
    stub = bin_dir / "runpodctl"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'tar_state=absent; [ -f "{tmp_path}/work/test-session-out.tgz" ] && tar_state=present\n'
        f'echo "$* tarball=$tar_state" >> "{log}"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    stage_file = tmp_path / "stages.txt"
    stage_file.write_text(stages, encoding="utf-8")
    out = tmp_path / "smoke-out"
    out.mkdir()
    (out / "answer-summary.json").write_text("{}\n", encoding="utf-8")
    full_env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "WORK": str(tmp_path / "work"),
        "OUT_DIR": str(out),
        "STAGES_FILE": str(stage_file),
        "RUNPOD_POD_ID": "pod123",
        "RUNPOD_API_KEY": KEY,
        **env,
    }
    result = subprocess.run(
        ["bash", str(PATH_SCRIPT)], env=full_env, capture_output=True, text=True, timeout=60
    )
    return result, log


def test_trap_is_set_before_the_first_stage() -> None:
    body = _script()[_script().index("main() {") :]
    assert "trap finish EXIT" in body
    assert body.index("trap finish EXIT") < body.index("run_stages")


def test_a_failing_stage_still_writes_the_tarball_and_the_rest_run(tmp_path: Path) -> None:
    result, log = _run(tmp_path, 'first false\nsecond touch "$OUT_DIR/second-ran"\n')
    work = tmp_path / "work"
    assert (work / "test-session-out.tgz").is_file()
    assert (work / "test-session-out.tgz.sha256").is_file()
    assert (tmp_path / "smoke-out" / "second-ran").is_file()
    assert (tmp_path / "smoke-out" / "failed-stages.txt").read_text().split() == ["first"]
    assert result.returncode == 1


def test_the_stop_runs_once_after_the_tarball(tmp_path: Path) -> None:
    result, log = _run(tmp_path, "only true\n")
    assert result.returncode == 0
    assert log.read_text(encoding="utf-8").splitlines() == ["stop pod pod123 tarball=present"]


def test_a_killed_run_still_writes_the_tarball_and_stops(tmp_path: Path) -> None:
    _run(tmp_path, 'killer kill -TERM "$SESSION_PID"; sleep 1\nnever touch "$OUT_DIR/x"\n')
    assert (tmp_path / "work" / "test-session-out.tgz").is_file()
    assert not (tmp_path / "smoke-out" / "x").exists()
    assert log_lines(tmp_path) == ["stop pod pod123 tarball=present"]


def log_lines(tmp_path: Path) -> list[str]:
    return (tmp_path / "runpodctl.log").read_text(encoding="utf-8").splitlines()


def test_missing_key_stops_before_any_stage(tmp_path: Path) -> None:
    result, log = _run(tmp_path, 'first touch "$OUT_DIR/ran"\n', RUNPOD_API_KEY="")
    assert result.returncode == 2
    assert "RUNPOD_API_KEY" in result.stdout
    assert not (tmp_path / "smoke-out" / "ran").exists()
    assert not log.exists()


def test_dry_run_prints_every_command_and_no_key_value(tmp_path: Path) -> None:
    stages = "ingest uv run --no-sync python run_arms.py --stage ingest --prefreeze\nseal true\n"
    result, log = _run(tmp_path, stages, DRY_RUN="1")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "uv run --no-sync python run_arms.py --stage ingest --prefreeze" in output
    assert "[dry-run] true" in output
    assert "tar -czf" in output
    assert "runpodctl stop pod pod123" in output
    assert KEY not in output
    assert not log.exists()
    assert not (tmp_path / "work" / "test-session-out.tgz").exists()
