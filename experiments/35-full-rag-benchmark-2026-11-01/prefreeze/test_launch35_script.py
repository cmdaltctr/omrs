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
from _timeout_shim import add_timeout_if_missing

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
#: A stand-in GLM-5.3 base URL in the watcher's mode-600 file (ZAI_ENV), never printed.
ZAI_URL = "https://fake-zai.example.invalid/api/LEAKCHECK-77"
#: The stage writes what the chain's environment holds, so the test can compare.
STAGE = (
    "envcheck sh -c 'for n in OPENROUTER_API_KEY OMRS_EXP35_ZAI_KEY OMRS_EXP35_ZAI_BASE_URL "
    "EXP35_POD_IMAGE "
    'RUNPOD_POD_ID RUNPOD_API_KEY; do printenv "$n" > "$OUT_DIR/$n"; done\'\n'
)


def _launch(
    tmp_path: Path, environ: dict[str, str], zai: str = ZAI_URL, stage: str = STAGE
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    add_timeout_if_missing(bin_dir)
    for name in ("runpodctl", "curl"):
        stub = bin_dir / name
        stub.write_text(f'#!/usr/bin/env bash\necho "$*" >> "{tmp_path}/{name}.log"\n')
        stub.chmod(0o755)
    fake = tmp_path / "environ"
    entries = ["PATH=/usr/bin", "HOME=/root", *(f"{k}={v}" for k, v in environ.items())]
    fake.write_bytes(b"\0".join(e.encode() for e in entries) + b"\0")
    stages = tmp_path / "stages.txt"
    stages.write_text(stage, encoding="utf-8")
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
        "ZAI_ENV": str(tmp_path / ".zai_env"),
    }
    (tmp_path / ".zai_env").write_text(f"OMRS_EXP35_ZAI_BASE_URL='{zai}'\n", encoding="utf-8")
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
    assert (tmp_path / "out" / "OMRS_EXP35_ZAI_BASE_URL").read_text().strip() == ZAI_URL
    assert not any(VALUES[name] in output for name in SECRETS) and ZAI_URL not in output
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


def test_an_empty_base_url_fails_the_pre_check_by_name_only(tmp_path: Path) -> None:
    result = _launch(tmp_path, VALUES, zai="")
    assert result.returncode == 2
    assert "OMRS_EXP35_ZAI_BASE_URL" in result.stdout
    assert not (tmp_path / "out" / "OPENROUTER_API_KEY").exists()


def _dry_launch(
    tmp_path: Path, session_lines: str = "", **env: str | None
) -> subprocess.CompletedProcess[str]:
    """Dry run of the whole chain from launch35.sh: it prints each step and writes nothing."""
    stages = tmp_path / "stages.txt"
    stages.write_text("alpha true\n", encoding="utf-8")
    session_env = tmp_path / "session.env"
    session_env.write_text(f"STAGES_FILE={stages}\n{session_lines}", encoding="utf-8")
    base = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp_path),
        "PROC1_ENVIRON": str(tmp_path / "no-environ"),
        "SESSION_ENV": str(session_env),
        "ZAI_ENV": str(tmp_path / ".zai_env"),
        "DRY_RUN": "1",
        **env,
    }
    full = {key: value for key, value in base.items() if value is not None}
    return subprocess.run(
        ["bash", str(LAUNCH)], env=full, capture_output=True, text=True, timeout=60
    )


def test_the_work_folder_defaults_to_the_container_disk(tmp_path: Path) -> None:
    result = _dry_launch(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "work /root/exp35-work, out /root/exp35-work/exp35-test/out" in result.stdout
    assert "/workspace/exp35-test" not in result.stdout


def test_the_session_and_zai_files_default_to_the_work_folder(tmp_path: Path) -> None:
    work = tmp_path / "w"
    work.mkdir()
    (work / ".zai_env").write_text(f"OMRS_EXP35_ZAI_BASE_URL='{ZAI_URL}'\n", encoding="utf-8")
    stages = tmp_path / "stages.txt"
    stages.write_text(STAGE, encoding="utf-8")
    (work / "session.env").write_text(
        f"OUT_DIR={tmp_path / 'out'}\nSTAGES_FILE={stages}\n", encoding="utf-8"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    add_timeout_if_missing(bin_dir)
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(tmp_path), "WORK": str(work)}
    env["PROC1_ENVIRON"] = str(tmp_path / "environ")
    entries = [f"{k}={v}" for k, v in VALUES.items()]
    (tmp_path / "environ").write_bytes(b"\0".join(e.encode() for e in entries) + b"\0")
    for name in ("runpodctl", "curl"):
        (bin_dir / name).write_text("#!/usr/bin/env bash\nexit 0\n")
        (bin_dir / name).chmod(0o755)
    result = subprocess.run(
        ["bash", str(LAUNCH)], env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "out" / "OMRS_EXP35_ZAI_BASE_URL").read_text().strip() == ZAI_URL


@pytest.mark.parametrize(
    ("mount_cmd", "spare", "expected"),
    [
        ("true", None, "/workspace/exp35-stage-out"),
        ("false", None, None),
        ("true", "/elsewhere/spare", "/elsewhere/spare"),
        ("true", "", None),
    ],
    ids=["mounted", "not-mounted", "set-wins", "set-empty-wins"],
)
def test_the_spare_folder_is_set_only_when_workspace_is_a_mount_point(
    tmp_path: Path, mount_cmd: str, spare: str | None, expected: str | None
) -> None:
    result = _dry_launch(tmp_path, MOUNTPOINT_CMD=mount_cmd, SPARE_DIR=spare)
    out = result.stdout
    assert result.returncode == 0, out + result.stderr
    if expected:
        assert expected in out
        assert "no spare copy" not in out
    else:
        assert "exp35-stage-out" not in out and "/elsewhere" not in out
        assert out.count("no spare copy") == 1


R2_VALUES = {
    "R2_ACCESS_KEY_ID": "r2id-SECRET-ACCESS-111",
    "R2_SECRET_ACCESS_KEY": "r2sec-SECRET-VALUE-222",
    "R2_ENDPOINT": "https://acct123abc.fake-r2.invalid",
}


def test_the_launch_copies_the_r2_values_from_process_1_and_prints_none(tmp_path: Path) -> None:
    stage = (
        "envcheck sh -c 'for n in "
        + " ".join(R2_VALUES)
        + '; do printenv "$n" > "$OUT_DIR/$n"; done\'\n'
    )
    result = _launch(tmp_path, {**VALUES, **R2_VALUES}, stage=stage)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    for name, value in R2_VALUES.items():
        assert (tmp_path / "out" / name).read_text().strip() == value
        assert value not in output
