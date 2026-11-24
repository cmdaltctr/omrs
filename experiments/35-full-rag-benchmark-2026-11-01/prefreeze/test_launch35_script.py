"""Checks on launch35.sh, the start of the test pod session over SSH (gap G7).

RunPod puts the create-time environment into process 1 only. The tests stand in a
fake environ file (NUL-separated, as ``/proc/1/environ``) and stub ``runpodctl`` and
``curl``, so no test reaches RunPod or a hosted service.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).parent
LAUNCH = HERE / "launch35.sh"
VALUES = {
    "OPENROUTER_API_KEY": "sk-or-SECRET_OPENROUTER_456",
    "OMRS_EXP35_ZAI_KEY": "zai-SECRET_GLM_789",
    "EXP35_POD_IMAGE": "runpod/base@sha256:" + "4" * 64,
    "RUNPOD_POD_ID": "pod123",
    "RUNPOD_API_KEY": "rpa_SECRET_KEY_VALUE_123",
}
SECRETS = ("OPENROUTER_API_KEY", "OMRS_EXP35_ZAI_KEY", "RUNPOD_API_KEY")
#: The stage writes what the chain's environment holds, so the test can compare.
STAGE = (
    "envcheck sh -c 'for n in OPENROUTER_API_KEY OMRS_EXP35_ZAI_KEY EXP35_POD_IMAGE "
    'RUNPOD_POD_ID RUNPOD_API_KEY; do printenv "$n" > "$OUT_DIR/$n"; done\'\n'
)


def _launch(tmp_path: Path, environ: dict[str, str]) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("runpodctl", "curl"):
        stub = bin_dir / name
        stub.write_text(f'#!/usr/bin/env bash\necho "$*" >> "{tmp_path}/{name}.log"\n')
        stub.chmod(0o755)
    fake = tmp_path / "environ"
    entries = ["PATH=/usr/bin", "HOME=/root", *(f"{k}={v}" for k, v in environ.items())]
    fake.write_bytes(b"\0".join(e.encode() for e in entries) + b"\0")
    stages = tmp_path / "stages.txt"
    stages.write_text(STAGE, encoding="utf-8")
    session_env = tmp_path / "session.env"
    session_env.write_text(
        f"OUT_DIR={tmp_path / 'out'}\nSTAGES_FILE={stages}\nWORK={tmp_path / 'work'}\n",
        encoding="utf-8",
    )
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "PROC1_ENVIRON": str(fake),
        "SESSION_ENV": str(session_env),
    }
    return subprocess.run(
        ["bash", str(LAUNCH)], env=env, capture_output=True, text=True, timeout=60
    )


def test_the_launch_copies_the_pod_values_from_process_1_and_prints_none(
    tmp_path: Path,
) -> None:
    result = _launch(tmp_path, VALUES)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    for name, value in VALUES.items():
        assert (tmp_path / "out" / name).read_text().strip() == value
    assert not any(VALUES[name] in output for name in SECRETS)
    assert (tmp_path / "work" / "test-session-out.tgz").is_file()
    assert (tmp_path / "runpodctl.log").read_text().splitlines() == ["pod stop pod123"]


@pytest.mark.parametrize("missing", ["OPENROUTER_API_KEY", "OMRS_EXP35_ZAI_KEY", "EXP35_POD_IMAGE"])
def test_an_empty_value_fails_the_pre_check_by_name_only(tmp_path: Path, missing: str) -> None:
    result = _launch(tmp_path, {**VALUES, missing: ""})
    output = result.stdout + result.stderr
    assert result.returncode == 2
    assert missing in result.stdout
    assert not any(VALUES[name] in output for name in SECRETS)
    assert not (tmp_path / "out" / "OPENROUTER_API_KEY").exists()
    assert not (tmp_path / "runpodctl.log").exists()
