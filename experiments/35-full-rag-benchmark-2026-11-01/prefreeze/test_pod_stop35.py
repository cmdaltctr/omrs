"""Checks on the pod self-stop of pod_test_session.sh: error capture and retry rounds.

Stub ``runpodctl``, ``curl`` and ``sleep`` sit first on ``PATH``, so no test reaches RunPod.
Each stub prints a marker on stderr. The tests read the marker in the session output,
which the Mac keeps, and count the calls per round.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from _timeout_shim import add_timeout_if_missing

HERE = Path(__file__).parent
SCRIPT = HERE / "pod_test_session.sh"
KEY = "rpa_LEAKCHECK_SECRET_9f3c1d"

_RUNPODCTL = """#!/usr/bin/env bash
echo "$1 $2" >> "{t}/ctl.log"
echo "ctl-err-$1-$2 boom" >&2
echo "second stderr line" >&2
if [ "$1 $2" = "pod stop" ]; then
  n=$(( $(cat "{t}/new.n" 2>/dev/null || echo 0) + 1 )); echo "$n" > "{t}/new.n"
  codes=(${{STUB_NEW_RCS:-1}})
  exit "${{codes[$((n - 1))]:-${{codes[${{#codes[@]}}-1]}}}}"
fi
exit 1
"""
_CURL = """#!/usr/bin/env bash
cat > /dev/null
echo "$*" >> "{t}/curl.log"
[ -z "${{STUB_CURL_LEAK:-}}" ] || echo "debug: Authorization: Bearer ${{STUB_CURL_LEAK}}" >&2
echo "curl: (22) The requested URL returned error: 401" >&2
exit 22
"""
_SLEEP = """#!/usr/bin/env bash
echo "$1" >> "{t}/sleep.log"
exit 0
"""


def _run(tmp_path: Path, **env: str) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("runpodctl", _RUNPODCTL), ("curl", _CURL), ("sleep", _SLEEP)):
        path = bin_dir / name
        path.write_text(body.format(t=tmp_path), encoding="utf-8")
        path.chmod(0o755)
    add_timeout_if_missing(bin_dir)
    stages = tmp_path / "stages.txt"
    stages.write_text("only true\n", encoding="utf-8")
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    (out / "answer-summary.json").write_text("{}\n", encoding="utf-8")
    full_env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "WORK": str(tmp_path / "work"),
        "OUT_DIR": str(out),
        "STAGES_FILE": str(stages),
        "RUNPOD_POD_ID": "pod123",
        "RUNPOD_API_KEY": KEY,
        "OPENROUTER_API_KEY": "sk-or-x",
        "OMRS_EXP35_ZAI_KEY": "zai-x",
        "OMRS_EXP35_ZAI_BASE_URL": "https://fake-zai.example.invalid/api",
        "EXP35_POD_IMAGE": "runpod/base@sha256:" + "4" * 64,
        **env,
    }
    return subprocess.run(
        ["bash", str(SCRIPT)], env=full_env, capture_output=True, text=True, timeout=60
    )


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def test_all_methods_failing_runs_three_rounds_and_logs_each_error(tmp_path: Path) -> None:
    result = _run(tmp_path, STOP_RETRY_S="0")
    assert result.returncode == 3
    assert _lines(tmp_path / "ctl.log") == ["pod stop", "stop pod"] * 3
    assert len(_lines(tmp_path / "curl.log")) == 6
    out = result.stdout
    assert out.count("pod stop: runpodctl pod stop exit 1: ctl-err-pod-stop boom") == 3
    assert out.count("pod stop: runpodctl stop pod exit 1: ctl-err-stop-pod boom") == 3
    assert out.count("exit 22: curl: (22) The requested URL returned error: 401") == 6
    assert "second stderr line" not in out
    assert "POD_STOP_FAILED: no stop command worked and the GPU still bills." in out
    assert "pod stop sent with" not in out


def test_a_later_round_that_works_stops_the_retries(tmp_path: Path) -> None:
    result = _run(tmp_path, STOP_RETRY_S="0", STUB_NEW_RCS="1 0")
    assert result.returncode == 0
    assert "pod stop sent with: runpodctl pod stop" in result.stdout
    assert "POD_STOP_FAILED" not in result.stdout
    assert _lines(tmp_path / "ctl.log") == ["pod stop", "stop pod", "pod stop"]
    assert len(_lines(tmp_path / "curl.log")) == 2


def test_the_pause_runs_between_rounds_only(tmp_path: Path) -> None:
    _run(tmp_path, STOP_RETRY_S="7")
    assert _lines(tmp_path / "sleep.log") == ["7", "7"]


def test_a_key_echoed_on_stderr_never_reaches_the_log(tmp_path: Path) -> None:
    result = _run(tmp_path, STOP_RETRY_S="0", STUB_CURL_LEAK=KEY)
    assert "POD_STOP_FAILED" in result.stdout
    assert "Authorization: Bearer [redacted]" in result.stdout
    assert KEY not in result.stdout + result.stderr
