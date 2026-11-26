"""Checks on freeze_layout_stages.txt, the 8B re-run that also tests stop and resume.

test_session_stages.py runs the general checks on the file (parsing, scripts, no key, no
literal volume path). These tests check what the layout test needs: the 8B stages are the
stages of freeze_rerun_stages.txt, the probe stops the chain once, and the resume check
reads the tarball the chain packed for the build stage (ordinal tag from the file).
"""

from __future__ import annotations

import re

from test_session_stages import LAYOUT_FILE, RERUN_FILE, _read

SAME_AS_RERUN = [
    "setup",
    "context",
    "gpulog",
    "vram8-build",
    "vram8-search",
    "check-search",
    "check-tokenizer",
    "collect",
]
ORDER = [
    "setup",
    "context",
    "gpulog",
    "vram8-build",
    "resume-probe",
    "vram8-search",
    "check-search",
    "check-tokenizer",
    "check-resume",
    "collect",
]
PROBE = (
    'test -e "$WORK/resume-probe.ok" || { touch "$WORK/resume-probe.ok"; '
    'echo "resume-probe: stopping the chain on purpose (first run)"; exit 1; }'
)


def _by_name() -> dict[str, object]:
    return {s.name: s for s in _read(LAYOUT_FILE)[0]}


def test_the_stages_run_in_the_order_of_the_two_launches() -> None:
    assert [s.name for s in _read(LAYOUT_FILE)[0]] == ORDER


def test_the_8b_stages_equal_the_stages_of_the_rerun_file() -> None:
    mine, rerun = _by_name(), {s.name: s for s in _read(RERUN_FILE)[0]}
    for name in SAME_AS_RERUN:
        found = (mine[name].fatal, mine[name].timeout, mine[name].command)
        assert found == (rerun[name].fatal, rerun[name].timeout, rerun[name].command), name
    assert _read(LAYOUT_FILE)[1] == _read(RERUN_FILE)[1]


def test_the_probe_fails_once_and_stops_the_chain() -> None:
    probe = _by_name()["resume-probe"]
    assert (probe.fatal, probe.timeout, probe.command) == (True, "1m", PROBE)
    assert [s.name for s in _read(LAYOUT_FILE)[0] if s.fatal] == [
        "setup",
        "context",
        "resume-probe",
    ]


def test_the_resume_check_reads_the_log_line_and_the_tarball_of_the_build_stage() -> None:
    stages = _read(LAYOUT_FILE)[0]
    build = next(s for s in stages if s.name == "vram8-build")
    tag = f"{build.index + 1:02d}-vram8-build"  # the chain counts stage lines from 1
    assert tag == "04-vram8-build"
    check = _by_name()["check-resume"]
    assert check.fatal is False and check.timeout == "2m"
    assert "grep -q '== vram8-build: SKIPPED (resume' \"$WORK/test-session.log\"" in check.command
    assert f'cd "$WORK/stage-out" && sha256sum -c {tag}.tgz.sha256' in check.command
    assert re.findall(r"\d\d-vram8-build", check.command) == [tag]
    after = [s.name for s in stages[build.index + 1 :]]
    assert after.index("check-resume") > after.index("vram8-search")
