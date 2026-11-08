"""Tests for ``run_sweep.sh`` (PR 195 review fixes, CodeRabbit 2026-11-08).

Run with: uv run --no-sync pytest test_sweep_script.py -q

The script runs from a tmp copy with a fake ``uv`` and ``caffeinate`` first on
PATH. The fake ``uv`` logs its arguments and fails on request. No test starts a
router, a model or a real stage.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "run_sweep.sh"

FAKE_UV = """#!/bin/sh
echo "$@" >> "$FAKE_UV_LOG"
case " $* " in *" $FAKE_UV_FAIL "*) exit 1 ;; esac
exit 0
"""


@pytest.fixture
def sweep(tmp_path):
    folder = tmp_path / "exp"
    folder.mkdir()
    shutil.copy(SCRIPT, folder / "run_sweep.sh")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("uv", FAKE_UV), ("caffeinate", "#!/bin/sh\nexit 0\n")):
        path = bin_dir / name
        path.write_text(body, encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "uv.log"

    def run(fail: str = "--never"):
        env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_UV_LOG": str(log),
            "FAKE_UV_FAIL": fail,
        }
        done = subprocess.run(
            ["bash", "run_sweep.sh"],
            cwd=folder,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        return done, (log.read_text() if log.exists() else "")

    return folder, run


def test_a_failed_stage_stops_the_sweep_with_a_nonzero_exit(sweep):
    _, run = sweep
    done, calls = run(fail="--tokenize")
    assert done.returncode != 0
    assert "--tokenize" in calls
    assert "--extrapolate" not in calls and "--part-c" not in calls


def test_a_clean_sweep_exits_zero(sweep):
    _, run = sweep
    done, calls = run()
    assert done.returncode == 0
    assert "--part-c --stage compare" in calls


@pytest.mark.parametrize("name", [".done-ingest.json", "timing-4b.jsonl", "token-counts.json"])
def test_output_from_a_limited_run_stops_the_sweep_before_any_stage(sweep, name):
    folder, run = sweep
    (folder / "output").mkdir()
    (folder / "output" / name).write_text('{"limit": 1}\n', encoding="utf-8")
    done, calls = run()
    assert done.returncode != 0
    assert calls == ""
    assert name in done.stdout + done.stderr


def test_output_from_a_full_run_passes_the_limit_guard(sweep):
    folder, run = sweep
    (folder / "output").mkdir()
    (folder / "output" / ".done-ingest.json").write_text('{"limit": null}', encoding="utf-8")
    done, _ = run()
    assert done.returncode == 0
