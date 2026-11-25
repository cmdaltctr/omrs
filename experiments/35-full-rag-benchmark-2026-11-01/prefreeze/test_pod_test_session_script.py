"""Checks on pod_test_session.sh, the script of the test pod session (task 9.1a, H-32).

The runs use stub commands only: a stub ``runpodctl`` and a stub ``curl`` first on
``PATH`` log their arguments and never reach RunPod, so no test creates, stops or
deletes a pod. Gaps G5, G7 to G9, G15, G22 and G23 of the 2026-11-23 session plan.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import time
from pathlib import Path

import pytest
from _timeout_shim import add_timeout_if_missing

HERE = Path(__file__).parent
PATH_SCRIPT = HERE / "pod_test_session.sh"
KEY = "rpa_SECRET_KEY_VALUE_123"
HOSTED = {
    "OPENROUTER_API_KEY": "sk-or-SECRET_OPENROUTER_456",
    "OMRS_EXP35_ZAI_KEY": "zai-SECRET_GLM_789",
    "EXP35_POD_IMAGE": "runpod/base@sha256:" + "4" * 64,
}

_RUNPODCTL = """#!/usr/bin/env bash
tar_state=absent; [ -f "{t}/work/test-session-out.tgz" ] && tar_state=present
echo "$* tarball=$tar_state" >> "{t}/runpodctl.log"
pulled=no; [ -e "{t}/work/PULLED" ] && pulled=yes
echo "$pulled" > "{t}/pulled-at-stop"
case "$1 $2" in
  "pod stop") exit "${{STUB_NEW_RC:-0}}" ;;
  "stop pod") exit "${{STUB_OLD_RC:-0}}" ;;
esac
"""
_CURL = """#!/usr/bin/env bash
stdin="$(cat)"
key=no; case "$stdin" in *"{key}"*) key=yes ;; esac
echo "$* key-on-stdin=$key" >> "{t}/curl.log"
exit "${{STUB_CURL_RC:-0}}"
"""
_SLEEP = """#!/usr/bin/env bash
n=$(( $(cat "{t}/sleeps" 2>/dev/null || echo 0) + 1 )); echo "$n" > "{t}/sleeps"
[ "$n" -ge "${{STUB_PULLED_AFTER:-999}}" ] && touch "{t}/work/PULLED"
exit 0
"""
_RUNNER = """#!/usr/bin/env bash
echo "$*" >> "{t}/runner.log"
n=$(wc -l < "{t}/runner.log")
codes=(${{STUB_RUNNER_CODES:-0}})
exit "${{codes[$((n - 1))]:-0}}"
"""

_TAR = """#!/usr/bin/env bash
pid="$(cat "{t}/smoke-out/bg.pid")" state=gone
for _ in 1 2 3 4 5 6 7 8 9 10; do kill -0 "$pid" 2>/dev/null || break; /bin/sleep 0.2; done
kill -0 "$pid" 2>/dev/null && state=alive
echo "$state" > "$STUB_TAR"
exec "$REAL_TAR" "$@"
"""


def _script() -> str:
    return PATH_SCRIPT.read_text(encoding="utf-8")


def _stub(bin_dir: Path, name: str, body: str, tmp_path: Path) -> None:
    path = bin_dir / name
    path.write_text(body.format(t=tmp_path, key=KEY), encoding="utf-8")
    path.chmod(0o755)


def _run(
    tmp_path: Path,
    stages: str,
    *,
    make_out: bool = True,
    stub_sleep: bool = False,
    **env: str,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("runpodctl", _RUNPODCTL), ("curl", _CURL), ("run_arms.py", _RUNNER)):
        _stub(bin_dir, name, body, tmp_path)
    add_timeout_if_missing(bin_dir)
    if stub_sleep:
        _stub(bin_dir, "sleep", _SLEEP, tmp_path)
    if "STUB_TAR" in env:
        _stub(bin_dir, "tar", _TAR, tmp_path)
    stage_file = tmp_path / "stages.txt"
    stage_file.write_text(stages, encoding="utf-8")
    out = tmp_path / "smoke-out"
    if make_out:
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
        **HOSTED,
        **env,
    }
    result = subprocess.run(
        ["bash", str(PATH_SCRIPT)], env=full_env, capture_output=True, text=True, timeout=60
    )
    return result, tmp_path / "runpodctl.log"


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def _listed(tmp_path: Path, name: str) -> list[str]:
    return (tmp_path / "smoke-out" / name).read_text(encoding="utf-8").split()


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
    assert _listed(tmp_path, "failed-stages.txt") == ["first"]
    assert result.returncode == 1


def test_the_stop_runs_once_after_the_tarball(tmp_path: Path) -> None:
    result, log = _run(tmp_path, "only true\n")
    assert result.returncode == 0
    assert _lines(log) == ["pod stop pod123 tarball=present"]


def test_a_killed_run_still_writes_the_tarball_and_stops(tmp_path: Path) -> None:
    _run(tmp_path, 'killer kill -TERM "$SESSION_PID"; sleep 1\nnever touch "$OUT_DIR/x"\n')
    assert (tmp_path / "work" / "test-session-out.tgz").is_file()
    assert not (tmp_path / "smoke-out" / "x").exists()
    assert _lines(tmp_path / "runpodctl.log") == ["pod stop pod123 tarball=present"]


def test_the_tarball_leaves_out_the_index_stores_and_keeps_every_record(tmp_path: Path) -> None:
    """P2 (2026-11-24): the stores made the tarball 278 MB; the copy took 35 min."""
    out = tmp_path / "smoke-out"
    keep = [
        "environment.json",
        "s/environment.json",
        "s/freshstack/rebuild.json",
        "s/freshstack/e4b-c1024/ingest.jsonl",
        "s/freshstack/e4b-c1024/index-fingerprint.json",
        "r/freshstack/answer/e4b-c512-roff-hoff/run1/answer-summary.json",
        "fsfull/router.log",
        "fsfull/summary.txt",
    ]
    drop = [
        "stores/e4b-c1024/lancedb/chunks.lance/data/0.lance",
        "s/stores/e8b-c512/lancedb/chunks.lance/_versions/1.manifest",
        "fsfull/stores/e8b-c512/lancedb/chunks.lance/_indices/x.json",
    ]
    for rel in keep + drop:
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_text("x\n", encoding="utf-8")
    result, _ = _run(tmp_path, "only true\n", make_out=False)
    assert result.returncode == 0, result.stdout + result.stderr
    with tarfile.open(tmp_path / "work" / "test-session-out.tgz") as tar:
        names = {m.name for m in tar.getmembers() if m.isfile()}
    assert {f"smoke-out/{rel}" for rel in keep} <= names
    assert {"smoke-out/failed-stages.txt", "smoke-out/skipped-stages.txt"} <= names
    assert [n for n in names if "/stores/" in n or "lancedb" in n] == []


def test_missing_key_stops_before_any_stage(tmp_path: Path) -> None:
    result, log = _run(tmp_path, 'first touch "$OUT_DIR/ran"\n', RUNPOD_API_KEY="")
    assert result.returncode == 2
    assert "RUNPOD_API_KEY" in result.stdout
    assert not (tmp_path / "smoke-out" / "ran").exists()
    assert not log.exists()


@pytest.mark.parametrize("name", sorted(HOSTED))
def test_a_missing_hosted_value_stops_before_any_stage_and_prints_no_value(
    tmp_path: Path, name: str
) -> None:
    result, log = _run(tmp_path, 'first touch "$OUT_DIR/ran"\n', **{name: ""})
    output = result.stdout + result.stderr
    assert result.returncode == 2
    assert name in result.stdout
    assert not (tmp_path / "smoke-out" / "ran").exists()
    assert not log.exists()
    assert not any(value in output for value in (KEY, *HOSTED.values()))


def test_dry_run_prints_every_command_and_no_key_value(tmp_path: Path) -> None:
    stages = "ingest uv run --no-sync python run_arms.py --stage ingest --prefreeze\nseal true\n"
    result, log = _run(tmp_path, stages, DRY_RUN="1")
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "uv run --no-sync python run_arms.py --stage ingest --prefreeze" in output
    assert "[dry-run] true" in output
    assert "tar -czf" in output
    assert "runpodctl pod stop pod123" in output
    assert not any(value in output for value in (KEY, *HOSTED.values()))
    assert not log.exists()
    assert not (tmp_path / "work" / "test-session-out.tgz").exists()


def test_a_failed_bang_stage_stops_the_chain(tmp_path: Path) -> None:
    result, log = _run(tmp_path, '!setup false\nlater touch "$OUT_DIR/later-ran"\n')
    assert result.returncode == 1
    assert "chain STOPPED" in result.stdout
    assert not (tmp_path / "smoke-out" / "later-ran").exists()
    assert _listed(tmp_path, "failed-stages.txt") == ["setup"]
    assert (tmp_path / "work" / "test-session-out.tgz").is_file()
    assert _lines(log) == ["pod stop pod123 tarball=present"]


def test_a_passing_bang_stage_lets_the_chain_go_on(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, '!setup true\nlater touch "$OUT_DIR/later-ran"\n')
    assert result.returncode == 0
    assert (tmp_path / "smoke-out" / "later-ran").is_file()


def test_a_stage_over_its_timeout_is_stopped_and_the_rest_run(tmp_path: Path) -> None:
    started = time.monotonic()
    result, _ = _run(tmp_path, 'slow@1s sleep 20\nafter touch "$OUT_DIR/after"\n')
    assert time.monotonic() - started < 15
    assert result.returncode == 1
    assert _listed(tmp_path, "failed-stages.txt") == ["slow:timeout"]
    assert (tmp_path / "smoke-out" / "after").is_file()


def test_the_session_cap_bounds_a_stage_and_skips_the_rest(tmp_path: Path) -> None:
    started = time.monotonic()
    result, log = _run(
        tmp_path, 'first sleep 20\nsecond touch "$OUT_DIR/second"\n', SESSION_CAP="2s"
    )
    assert time.monotonic() - started < 15
    assert result.returncode == 1
    assert _listed(tmp_path, "failed-stages.txt") == ["first:timeout", "second:cap"]
    assert not (tmp_path / "smoke-out" / "second").exists()
    assert (tmp_path / "work" / "test-session-out.tgz").is_file()
    assert _lines(log) == ["pod stop pod123 tarball=present"]


@pytest.mark.parametrize(
    "stages",
    ["bad@5x true\n", "ok true\nnocommand\n", "FS_QIDS=TODO\nok true\n"],
    ids=["bad-timeout", "no-command", "todo-value"],
)
def test_a_bad_stages_file_refuses_before_any_stage(tmp_path: Path, stages: str) -> None:
    result, log = _run(tmp_path, 'first touch "$OUT_DIR/ran"\n' + stages)
    assert result.returncode == 2
    assert "STOP: stages file line" in result.stdout
    assert not (tmp_path / "smoke-out" / "ran").exists()
    assert not log.exists()


def test_a_definition_line_is_exported_literally_to_later_stages(tmp_path: Path) -> None:
    stages = (
        "GREETING=hello world\nLITERAL=$HOME/x\n"
        'use sh -c \'printf "%s|%s" "$GREETING" "$LITERAL" > "$OUT_DIR/seen"\'\n'
    )
    result, _ = _run(tmp_path, stages)
    assert result.returncode == 0
    assert (tmp_path / "smoke-out" / "seen").read_text() == "hello world|$HOME/x"


def test_exit_77_marks_a_stage_skipped_not_failed(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, "legal sh -c 'exit 77'\nnext true\n")
    assert result.returncode == 0
    assert "legal: SKIPPED" in result.stdout
    assert _listed(tmp_path, "skipped-stages.txt") == ["legal"]
    assert _listed(tmp_path, "failed-stages.txt") == []


def test_the_out_dir_is_created_before_the_first_stage(tmp_path: Path) -> None:
    result, _ = _run(
        tmp_path, "context sh -c 'echo {} > \"$OUT_DIR/context35.json\"'\n", make_out=False
    )
    assert result.returncode == 0
    assert (tmp_path / "smoke-out" / "context35.json").is_file()
    assert _listed(tmp_path, "failed-stages.txt") == []


ARGS = "--stage answer --answer-concurrency 16 --rate-limit-attempts 6"
CALL = f"run_arms.py {ARGS}"
HALVED = f"--resume {ARGS}".replace(" 16", " 8")


@pytest.mark.parametrize(
    ("codes", "calls", "rc", "failed"),
    [
        ("5 0", [ARGS, HALVED], 0, []),
        ("6 0", [ARGS, f"--resume {ARGS}"], 0, []),
        ("4 0", [ARGS, f"--resume {ARGS}"], 0, []),
        ("5 5", [ARGS, HALVED], 1, ["a"]),
        ("2", [ARGS], 1, ["a"]),
    ],
    ids=["rate-limit-halves", "open-items", "judge-start", "twice-stops", "setup-error"],
)
def test_a_runner_stage_repeats_once_on_exit_4_5_or_6(
    tmp_path: Path, codes: str, calls: list[str], rc: int, failed: list[str]
) -> None:
    result, _ = _run(tmp_path, f"a {CALL}\n", STUB_RUNNER_CODES=codes)
    assert _lines(tmp_path / "runner.log") == calls
    assert result.returncode == rc
    assert _listed(tmp_path, "failed-stages.txt") == failed


def test_a_line_with_two_runner_calls_or_none_does_not_repeat(tmp_path: Path) -> None:
    stages = f"two {CALL} && {CALL}\nnone sh -c 'echo x >> \"$OUT_DIR/n\"; exit 5'\n"
    result, _ = _run(tmp_path, stages, STUB_RUNNER_CODES="5 0 0")
    assert _lines(tmp_path / "runner.log") == [ARGS]
    assert _lines(tmp_path / "smoke-out" / "n") == ["x"]
    assert _listed(tmp_path, "failed-stages.txt") == ["two", "none"]


@pytest.mark.parametrize(
    ("new_rc", "old_rc", "ctl_calls", "curl_calls", "said"),
    [
        ("0", "0", ["pod stop pod123"], [], "runpodctl pod stop"),
        ("1", "0", ["pod stop pod123", "stop pod pod123"], [], "runpodctl stop pod"),
        ("1", "1", ["pod stop pod123", "stop pod pod123"], ["v2/pods/pod123/action"], "REST"),
    ],
    ids=["new-syntax", "old-syntax", "rest"],
)
def test_the_stop_tries_new_then_old_runpodctl_then_rest(
    tmp_path: Path, new_rc: str, old_rc: str, ctl_calls: list, curl_calls: list, said: str
) -> None:
    result, log = _run(tmp_path, "only true\n", STUB_NEW_RC=new_rc, STUB_OLD_RC=old_rc)
    assert result.returncode == 0
    assert [line.rsplit(" tarball=", 1)[0] for line in _lines(log)] == ctl_calls
    curl = _lines(tmp_path / "curl.log")
    assert len(curl) == len(curl_calls)
    for line, part in zip(curl, curl_calls, strict=True):
        assert part in line and line.endswith("key-on-stdin=yes") and KEY not in line
    assert f"pod stop sent with: {said}" in result.stdout


def test_a_failed_stop_is_loud_and_exits_3(tmp_path: Path) -> None:
    result, _ = _run(tmp_path, "only true\n", STUB_NEW_RC="1", STUB_OLD_RC="1", STUB_CURL_RC="22")
    assert result.returncode == 3
    assert "POD_STOP_FAILED" in result.stdout
    curl = _lines(tmp_path / "curl.log")
    assert ["v2/pods/pod123/action" in curl[0], "v1/pods/pod123/stop" in curl[1]] == [True, True]
    assert KEY not in result.stdout + result.stderr + "".join(curl)


@pytest.mark.parametrize(
    ("grace", "pulled_after", "stale", "sleeps", "pulled_at_stop"),
    [("1", "2", False, 2, "yes"), ("1", "999", True, 6, "no"), ("0", "1", False, 0, "no")],
    ids=["pulled-in-time", "never-pulled", "no-grace"],
)
def test_the_stop_waits_for_the_pulled_marker_up_to_the_grace(
    tmp_path: Path, grace: str, pulled_after: str, stale: bool, sleeps: int, pulled_at_stop: str
) -> None:
    if stale:
        (tmp_path / "work").mkdir()
        (tmp_path / "work" / "PULLED").touch()
    result, log = _run(
        tmp_path,
        "only true\n",
        stub_sleep=True,
        STOP_GRACE_MIN=grace,
        PULL_POLL_S="10",
        STUB_PULLED_AFTER=pulled_after,
    )
    assert result.returncode == 0
    counted = tmp_path / "sleeps"
    assert (int(counted.read_text()) if counted.exists() else 0) == sleeps
    assert (tmp_path / "pulled-at-stop").read_text().strip() == pulled_at_stop
    assert len(_lines(log)) == 1


def test_a_background_process_of_a_stage_is_stopped_before_the_tarball(tmp_path: Path) -> None:
    stages = (
        'bg sh -c \'sleep 30 >/dev/null 2>&1 & echo $! >> "$BACKGROUND_PIDS"; '
        'echo $! > "$OUT_DIR/bg.pid"\'\n'
    )
    # The tar stub notes whether the process still runs 2 s after tar starts.
    seen = tmp_path / "bg-at-tar"
    tar = shutil.which("tar")
    result, _ = _run(tmp_path, stages, STUB_TAR=f"{seen}", REAL_TAR=f"{tar}")
    assert result.returncode == 0
    assert seen.read_text().strip() == "gone"
    pid = int((tmp_path / "smoke-out" / "bg.pid").read_text())
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        os.kill(pid, 9)
        pytest.fail(f"background process {pid} still ran after the session")


def test_a_timed_out_stage_leaves_no_process_of_its_group(tmp_path: Path) -> None:
    # The 2026-11-24 t-fb grandchild: it outlived SIGTERM and ran into the next stage.
    stages = (
        "slow@1s (trap '' TERM; exec sleep 40) >/dev/null 2>&1 & "
        'echo $! > "$OUT_DIR/grandchild.pid"; wait\n'
        'after touch "$OUT_DIR/after"\n'
    )
    result, _ = _run(tmp_path, stages)
    assert result.returncode == 1
    assert _listed(tmp_path, "failed-stages.txt") == ["slow:timeout"]
    pid = int((tmp_path / "smoke-out" / "grandchild.pid").read_text())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    os.kill(pid, 9)
    pytest.fail(f"process {pid} of the timed-out stage still ran after the session")


def test_a_timed_out_stage_leaves_a_python_stack_in_the_log(tmp_path: Path) -> None:
    # py-spy cannot attach in the pod, so a hung stage must print its own stack.
    hang = "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(40)"
    result, _ = _run(tmp_path, f'slow@1s python3 -c "{hang}" & wait\n')
    assert result.returncode == 1
    assert "most recent call first" in result.stdout + result.stderr


def test_a_timed_out_foreground_python_stage_leaves_its_stack_in_the_log(tmp_path: Path) -> None:
    # A plain stage that ends at SIGTERM prints nothing, so the first signal must be SIGABRT.
    result, _ = _run(tmp_path, 'slow@1s python3 -c "import time; time.sleep(40)"\n')
    assert result.returncode == 1
    assert "most recent call first" in result.stdout + result.stderr
