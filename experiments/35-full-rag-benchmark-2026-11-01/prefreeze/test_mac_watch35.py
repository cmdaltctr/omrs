"""Checks on mac_watch35.py, the Mac side of the test pod session (task 9.2).

Stub ``ssh``, ``scp`` and ``tmux`` come first on ``PATH``. The ssh stub runs the
remote command on this machine with ``/workspace`` moved into the test folder. The
tmux stub plays the chain: each ``has-session`` call moves it one step through a
scenario, and once the scenario is used up it stops the "pod" after ``PULLED``.
``MAC_WATCH35_FAKE_CLOCK=1`` makes every wait virtual, so the 30-minute idle rule runs
in seconds. No test reaches RunPod or any network host, and no test creates, stops or
deletes a pod.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import mac_watch35
import pytest
from watch_inputs35 import unsafe

HERE = Path(__file__).parent
WATCH = HERE / "mac_watch35.py"
PLAN = json.loads((HERE.parent / "plan.json").read_text(encoding="utf-8"))
POD = "pod123abc"
KEY_BODY = "SECRET_SSH_KEY_BODY_42"
FB = "benchmarks/financebench"
FS = "benchmarks/freshstack/corpus-oct-2024/langchain"
INPUTS = sorted(
    [
        "benchmarks/bioasq/question-answer-passages/test-00000-of-00001.parquet",
        "benchmarks/bioasq/text-corpus/test-00000-of-00001.parquet",
        f"{FB}/PDFS_MANIFEST.json",
        f"{FB}/financebench_merged.jsonl",
        f"{FB}/pdfs/DOC_A.pdf",
        f"{FB}/pdfs/DOC_B.pdf",
        f"{FS}/download.json",
        *(f"{FS}/{name}" for name in PLAN["pins"]["datasets"]["freshstack"]["corpus_files"]),
        "experiments/22-raw-query-qwen4b-baseline-2026-09-07/ground-truth.json",
    ]
)
DECOYS = (
    ".env",
    "secrets/runpod.key",
    ".config/omrs/omrs.jsonc",
    f"{FB}/.cache/lock",
    "benchmarks/bioasq/README.md",
)

_SSH = r"""#!/usr/bin/env bash
T="@T@"
while [ $# -gt 0 ]; do
  case "$1" in -i|-p|-o) shift 2 ;; -*) shift ;; *) break ;; esac
done
shift
cmd="$*"
printf '%s\n' "$cmd" >> "$T/ssh.log"
n=$(( $(cat "$T/ssh.count" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$T/ssh.count"
[ "$n" -le "${STUB_SSH_DOWN:-0}" ] && exit 255
[ -e "$T/ssh.dead" ] && exit 255
export WATCHER_PID="$PPID"
exec bash -c "${cmd//\/workspace/$T/pod/workspace}"
"""
_SCP = r"""#!/usr/bin/env bash
T="@T@"
printf '%s\n' "$*" >> "$T/scp.log"
echo "scp $*" >> "$T/order.log"
[ -e "$T/ssh.dead" ] && exit 1
case "$*" in
  *test-session-out.tgz*) [ -e "$T/scp.fail-once" ] && rm "$T/scp.fail-once" && exit 1
    [ -e "$T/scp.term" ] && rm "$T/scp.term" && kill -TERM "$PPID" ;;
  *watcher-out.tgz*) [ -e "$T/scp.term" ] && rm "$T/scp.term" && kill -TERM "$PPID" ;;
esac
args=()
while [ $# -gt 0 ]; do
  case "$1" in -i|-P|-o) shift 2 ;; -*) shift ;; *) args+=("$1"); shift ;; esac
done
map() { case "$1" in *@*:*) printf '%s' "$T/pod${1#*:}" ;; *) printf '%s' "$1" ;; esac; }
n=${#args[@]}
dst="$(map "${args[$((n - 1))]}")"
i=0
while [ "$i" -lt $((n - 1)) ]; do cp "$(map "${args[$i]}")" "$dst" || exit 1; i=$((i + 1)); done
"""
_TMUX = r"""#!/usr/bin/env bash
T="@T@"; P="$T/pod"; W="$P/workspace"; LOG="$W/test-session.log"
printf '%s\n' "$*" >> "$T/tmux.log"
case "$1" in
  kill-session) echo kill >> "$T/order.log"; [ -e "$T/tmux.kill-fails" ] && exit 1; exit 0 ;;
  new-session) for a in "$@"; do last="$a"; done
    printf '%s\n' "$last" > "$P/tmux-cmd"; : > "$LOG"; touch "$P/alive"; exit 0 ;;
  has-session) [ -e "$P/alive" ] || exit 1 ;;
  *) exit 0 ;;
esac
n=$(( $(cat "$P/step" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$P/step"
step="$(sed -n "${n}p" "$P/steps")"
pack() {
  tar -czf "$W/test-session-out.tgz" -C "$W/exp35-test" out
  sha256sum "$W/test-session-out.tgz" > "$W/test-session-out.tgz.sha256"
}
case "$step" in
  +*) printf '%s\n' "${step#+}" >> "$LOG" ;;
  done) pack; echo "[00:09:00] TEST_SESSION_DONE: copy the tarball" >> "$LOG" ;;
  badsha) pack; printf '%064d  %s\n' 0 "$W/test-session-out.tgz" > "$W/test-session-out.tgz.sha256"
    echo "[00:09:00] TEST_SESSION_DONE: copy the tarball" >> "$LOG" ;;
  dead) rm -f "$P/alive" ;;
  term) kill -TERM "$WATCHER_PID" ;;
  ssh-off) touch "$T/ssh.dead" ;;
  '') if [ -e "$W/PULLED" ]; then
        if [ -e "$P/stop-fails" ]; then echo "[00:10:00] POD_STOP_FAILED: no stop worked" >> "$LOG"
        else echo "[00:10:00] pod stop sent with: runpodctl pod stop" >> "$LOG"; fi
        rm -f "$P/alive"
      fi ;;
esac
[ -e "$P/alive" ]
"""


class Session:
    """One test folder: data root, fake pod, origin repository and stubs."""

    def __init__(self, tmp: Path, steps: list[str] | None = None) -> None:
        self.tmp = tmp
        self.root = tmp / "data"
        self.pod = tmp / "pod"
        self.home = tmp / "home"
        self.home.mkdir()
        self.key = tmp / "id_test"
        self.key.write_text(f"-----BEGIN OPENSSH PRIVATE KEY-----\n{KEY_BODY}\n", encoding="utf-8")
        self.examples = tmp / "examples.json"
        self.examples.write_text('{"claim": ["an example"]}\n', encoding="utf-8")
        for rel in INPUTS:
            self._write(self.root / rel, f"data of {rel}\n")
        files = {"DOC_A": {"sha256": "a" * 64}, "DOC_B": {"sha256": "b" * 64}}
        self._write(self.root / FB / "PDFS_MANIFEST.json", json.dumps({"files": files}))
        for rel in DECOYS:
            self._write(self.root / rel, "OPENROUTER_API_KEY=sk-or-DECOY_SECRET_77\n")
        self._write(self.pod / "workspace/exp35-test/out/answer-summary.json", "{}\n")
        self._write(self.pod / "steps", "".join(f"{s}\n" for s in steps or []))
        self.url, self.commit = self._origin()
        bin_dir = tmp / "bin"
        for name, body in (("ssh", _SSH), ("scp", _SCP), ("tmux", _TMUX)):
            self._write(bin_dir / name, body.replace("@T@", str(tmp)))
            (bin_dir / name).chmod(0o755)

    @staticmethod
    def _write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _env(self, **extra: str) -> dict[str, str]:
        return {
            "PATH": f"{self.tmp / 'bin'}:{os.environ['PATH']}",
            "HOME": str(self.home),
            "EXP35_DATA_DIR": str(self.root),
            "MAC_WATCH35_FAKE_CLOCK": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            **extra,
        }

    def _origin(self) -> tuple[Path, str]:
        repo = self.tmp / "origin"
        repo.mkdir()
        git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        git += ["-c", "commit.gpgsign=false"]
        env = self._env()
        subprocess.run([*git, "init", "-q"], check=True, env=env)
        (repo / "README").write_text("x\n", encoding="utf-8")
        subprocess.run([*git, "add", "README"], check=True, env=env)
        subprocess.run([*git, "commit", "-q", "-m", "init"], check=True, env=env)
        head = subprocess.run(
            [*git, "rev-parse", "HEAD"], check=True, env=env, capture_output=True, text=True
        )
        return repo, head.stdout.strip()

    def run(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        cmd = [sys.executable, str(WATCH), "--pod-id", POD, "--ssh-host", "203.0.113.7"]
        cmd += ["--ssh-port", "40022", "--commit", self.commit, "--examples", str(self.examples)]
        cmd += ["--ssh-key", str(self.key), "--repo-url", str(self.url), *args]
        return subprocess.run(
            cmd, env=self._env(**env), capture_output=True, text=True, timeout=120, cwd=self.tmp
        )

    def folder(self) -> Path:
        found = list((self.root / "experiments" / HERE.parent.name).glob("test-session-*"))
        assert len(found) == 1, found
        return found[0]

    def log(self, name: str) -> list[str]:
        path = self.tmp / name
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    def polls(self) -> int:
        return sum("ALIVE" in line for line in self.log("ssh.log"))


def _last(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout.rstrip("\n").splitlines()[-1]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_done_session_is_pulled_checked_marked_and_ends_with_the_delete_line(
    tmp_path: Path,
) -> None:
    steps = ["+[00:00:01] == setup: start (timeout 3600s)", "+[00:00:02] == setup: ok", "done"]
    s = Session(tmp_path, steps)
    result = s.run(STUB_SSH_DOWN="3")
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert _last(result) == f"DELETE_POD_NOW {POD}"
    folder = s.folder()
    assert _sha(folder / "test-session-out.tgz") == _sha(s.pod / "workspace/test-session-out.tgz")
    assert "TEST_SESSION_DONE" in (folder / "test-session.log").read_text(encoding="utf-8")
    assert (s.pod / "workspace/PULLED").read_text(encoding="utf-8").strip() == "ok"
    assert "end=done outputs=ok pulled-marker=written pod-stop=sent" in result.stdout
    inputs = s.pod / "workspace/inputs"
    assert sorted(p.name for p in inputs.iterdir()) == [
        "classify-examples.json",
        "exp35-inputs.tgz",
        "exp35-inputs.tgz.sha256",
    ]
    assert (inputs / "classify-examples.json").read_bytes() == s.examples.read_bytes()
    session_env = (s.pod / "workspace/session.env").read_text(encoding="utf-8")
    stages = (
        f"{s.pod}/workspace/omrs/experiments/{HERE.parent.name}/prefreeze/test_session_stages.txt"
    )
    assert session_env == f"COMMIT={s.commit}\nSTOP_GRACE_MIN=120\nSTAGES_FILE={stages}\n"
    clone = s.pod / "workspace/omrs"
    head = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True)
    assert head.stdout.decode().strip() == s.commit
    workspace = str(s.pod / "workspace")
    launch = mac_watch35.LAUNCH.replace("/workspace", workspace)
    assert (s.pod / "tmux-cmd").read_text(encoding="utf-8").strip() == launch
    assert KEY_BODY not in output


# End condition (the end word in RESULT) -> (scenario, extra arguments, exit code).
REFUSED = "+[00:00:01] STOP: environment variable RUNPOD_API_KEY is not set"
ENDS = {
    "stop-line": ([REFUSED, "dead"], [], 6),
    "session-ended": (["+[00:00:01] == setup: start", "dead"], [], 7),
    "idle": (["+[00:00:01] == setup: start"], [], 8),
    "wall-cap": (["+[00:00:01] == a: start"] * 30, ["--wall-cap-h", "0.1"], 9),
    "interrupted": (["+[00:00:01] == a: start", "term"], [], 12),
}


@pytest.mark.parametrize("end", sorted(ENDS))
def test_each_early_end_packs_and_pulls_the_outputs_marks_and_prints_delete(
    tmp_path: Path, end: str
) -> None:
    steps, args, code = ENDS[end]
    s = Session(tmp_path, steps)
    result = s.run(*args)
    assert result.returncode == code, result.stdout + result.stderr
    assert _last(result) == f"DELETE_POD_NOW {POD}"
    assert f"RESULT end={end} outputs=ok pulled-marker=written" in result.stdout
    folder = s.folder()
    assert (folder / "test-session.log").is_file()
    assert _sha(folder / "watcher-out.tgz") == _sha(s.pod / "workspace/watcher-out.tgz")
    with tarfile.open(folder / "watcher-out.tgz") as tar:
        assert "out/answer-summary.json" in tar.getnames()
    assert (s.pod / "workspace/PULLED").read_text(encoding="utf-8").strip() == "ok"


def test_a_second_signal_during_the_end_steps_does_not_stop_the_pull(tmp_path: Path) -> None:
    s = Session(tmp_path, ["+[00:00:01] == a: start", "term"])
    (tmp_path / "scp.term").touch()  # the second SIGTERM comes while the tarball is copied
    result = s.run()
    assert result.returncode == 12
    assert "RESULT end=interrupted outputs=ok pulled-marker=written" in result.stdout
    assert not (tmp_path / "scp.term").exists()
    pid = int((s.folder() / "watcher.pid").read_text(encoding="utf-8"))
    assert pid > 0 and _last(result) == f"DELETE_POD_NOW {POD}"


def test_idle_ends_after_the_stage_timeout_and_ten_minutes_of_quiet(tmp_path: Path) -> None:
    s = Session(tmp_path, ["+[00:00:01] == idle: start (timeout 1800s)"])
    result = s.run()
    assert result.returncode == 8
    assert "no new log byte for 40 min" in result.stdout
    # The stage allows 30 min plus a 10 min grace; polls come every 60 s, so poll 41 is first.
    assert s.polls() == 41


def test_a_quiet_stage_is_idle_only_after_its_own_timeout_and_ten_minutes(tmp_path: Path) -> None:
    """A silent long stage (the 6 h FreshStack build) must not end the session early."""
    s = Session(tmp_path, ["+[00:00:01] == fsfull: start (timeout 7200s)"])
    result = s.run()
    assert result.returncode == 8
    assert "no new log byte for 130 min" in result.stdout
    # The stage allows 120 min plus a 10 min grace, so poll 131 is the first idle one.
    assert s.polls() == 131


def test_pod_stop_failed_is_exit_3_after_the_pull(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    (s.pod / "stop-fails").touch()
    result = s.run()
    assert result.returncode == 3
    assert _last(result) == f"DELETE_POD_NOW {POD}"
    assert "end=done outputs=ok pulled-marker=written pod-stop=FAILED" in result.stdout
    assert "POD_STOP_FAILED" in result.stdout
    assert (s.folder() / "test-session-out.tgz").is_file()


def test_a_stop_line_waits_for_the_chain_tarball_before_the_pull(tmp_path: Path) -> None:
    steps = [
        "+pod_setup35: STOP: nvidia-smi lists: none. Delete this pod.",
        "+[00:00:02] == chain STOPPED: setup is marked with ! and failed",
        "done",
    ]
    s = Session(tmp_path, steps)
    result = s.run()
    assert result.returncode == 6
    assert "RESULT end=stop-line outputs=ok pulled-marker=written pod-stop=sent" in result.stdout
    assert (s.folder() / "test-session-out.tgz").is_file()
    assert not (s.folder() / "watcher-out.tgz").exists()
    assert _last(result) == f"DELETE_POD_NOW {POD}"


def test_lost_ssh_ends_the_watch_and_still_prints_delete(tmp_path: Path) -> None:
    s = Session(tmp_path, ["+[00:00:01] == a: start", "ssh-off"])
    result = s.run()
    assert result.returncode == 10
    assert "RESULT end=ssh-lost outputs=pull-failed pulled-marker=not-written" in result.stdout
    assert not (s.pod / "workspace/PULLED").exists()
    assert _last(result) == f"DELETE_POD_NOW {POD}"


def test_a_hash_mismatch_on_pull_is_loud_and_still_prints_delete(tmp_path: Path) -> None:
    s = Session(tmp_path, ["badsha"])
    result = s.run()
    assert result.returncode == 11
    assert "HASH_MISMATCH" in result.stdout
    assert "end=done outputs=hash-mismatch" in result.stdout
    assert (s.pod / "workspace/PULLED").read_text(encoding="utf-8").strip() == "hash-mismatch"
    pulls = [line for line in s.log("scp.log") if "test-session-out.tgz.sha256" in line]
    assert len(pulls) == 1  # ssh checks bytes in transit; a second copy cannot fix it
    assert (s.folder() / "test-session-out.tgz").is_file()
    assert _last(result) == f"DELETE_POD_NOW {POD}"


def test_a_failed_tarball_copy_is_tried_once_more(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    (tmp_path / "scp.fail-once").touch()
    result = s.run()
    assert result.returncode == 0, result.stdout
    pulls = [line for line in s.log("scp.log") if "test-session-out.tgz.sha256" in line]
    assert len(pulls) == 2
    assert "end=done outputs=ok" in result.stdout


def test_the_inputs_tarball_holds_only_the_setup_paths_and_no_secret(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    result = s.run()
    assert result.returncode == 0, result.stdout + result.stderr
    tgz = s.folder() / "inputs/exp35-inputs.tgz"
    with tarfile.open(tgz) as tar:
        names = sorted(tar.getnames())
        for rel in INPUTS:
            member = tar.extractfile(rel)
            assert member is not None and member.read() == (s.root / rel).read_bytes()
    assert names == INPUTS
    hidden = (".env", "secrets", ".config", ".ssh", ".cache")
    assert not [n for n in names if any(p.startswith(hidden) for p in Path(n).parts)]
    record = (tgz.parent / "exp35-inputs.tgz.sha256").read_text(encoding="utf-8")
    assert record == f"{_sha(tgz)}  exp35-inputs.tgz\n"
    assert _sha(s.pod / "workspace/inputs/exp35-inputs.tgz") == _sha(tgz)


def test_a_first_signal_during_the_pull_does_not_stop_the_pull(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    (tmp_path / "scp.term").touch()  # the first SIGTERM comes while the tarball is copied
    result = s.run()
    assert "RESULT end=done outputs=ok pulled-marker=written" in result.stdout, result.stdout
    assert result.returncode == 0 and not (tmp_path / "scp.term").exists()


def test_an_input_that_links_to_a_secret_inside_the_data_root_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "root"
    (root / FB).mkdir(parents=True)
    (root / ".env").write_text("KEY=value\n", encoding="utf-8")
    (root / FB / "notes.jsonl").write_text("{}\n", encoding="utf-8")
    (root / FB / "financebench_merged.jsonl").symlink_to(root / ".env")
    assert "secret" in (unsafe(f"{FB}/financebench_merged.jsonl", root) or "")
    assert unsafe(f"{FB}/notes.jsonl", root) is None


def test_an_input_that_links_outside_the_data_root_is_refused(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    outside = s.home / ".config/omrs/DOC_B.pdf"
    outside.parent.mkdir(parents=True)
    outside.write_text("secret settings\n", encoding="utf-8")
    pdf = s.root / FB / "pdfs/DOC_B.pdf"
    pdf.unlink()
    pdf.symlink_to(outside)
    result = s.run()
    assert result.returncode == 2
    assert "DOC_B.pdf" in result.stdout
    assert not s.log("ssh.log") and not s.log("scp.log")
    assert not (s.root / "experiments" / HERE.parent.name).exists()
    assert _last(result) == f"DELETE_POD_NOW {POD}"


def _tree(root: Path) -> dict[str, tuple[int, int]]:
    return {str(p): (p.lstat().st_mtime_ns, p.lstat().st_size) for p in root.rglob("*")}


def test_dry_run_lists_every_input_and_touches_nothing(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    before = _tree(tmp_path)
    result = s.run("--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _tree(tmp_path) == before
    assert not s.log("ssh.log") and not s.log("scp.log") and not s.log("tmux.log")
    for rel in INPUTS:
        assert rel in result.stdout
    assert f"{len(INPUTS)} files" in result.stdout
    assert "tmux new-session -d -s exp35" in result.stdout
    assert _last(result) == f"[dry-run] a real run ends with: DELETE_POD_NOW {POD}"
    assert not any(line.startswith("DELETE_POD_NOW") for line in result.stdout.splitlines())
    assert KEY_BODY not in result.stdout + result.stderr


def test_no_ssh_within_15_minutes_is_exit_4_with_nothing_copied(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    result = s.run(STUB_SSH_DOWN="1000")
    assert result.returncode == 4
    assert len(s.log("ssh.log")) == 61  # 'true' every 15 s for 15 min, first try included
    assert not s.log("scp.log")
    assert _last(result) == f"DELETE_POD_NOW {POD}"


def test_a_failed_pod_setup_step_is_exit_5_with_no_launch(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    s.commit = "f" * 40  # not in the origin repository, so the checkout on the pod fails
    result = s.run()
    assert result.returncode == 5
    assert "remote step failed" in result.stdout
    assert not (s.pod / "tmux-cmd").exists() and s.polls() == 0
    assert _last(result) == f"DELETE_POD_NOW {POD}"


def test_an_existing_results_folder_is_refused_before_any_remote_step(tmp_path: Path) -> None:
    s = Session(tmp_path, ["done"])
    today = datetime.now(UTC)
    for day in (today, today + timedelta(days=1)):
        old = s.root / "experiments" / HERE.parent.name / f"test-session-{day:%Y-%m-%d}"
        old.mkdir(parents=True)
        (old / "keep.txt").write_text("earlier session\n", encoding="utf-8")
    result = s.run()
    assert result.returncode == 2
    assert "already exists" in result.stdout
    assert not s.log("ssh.log")
    found = sorted((s.root / "experiments" / HERE.parent.name).rglob("*"))
    assert [p.name for p in found if p.is_file()] == ["keep.txt", "keep.txt"]
    assert _last(result) == f"DELETE_POD_NOW {POD}"


def test_the_watcher_matches_the_chain_launch_and_setup_contract() -> None:
    chain = (HERE / "pod_test_session.sh").read_text(encoding="utf-8")
    launch = (HERE / "launch35.sh").read_text(encoding="utf-8")
    setup = (HERE / "pod_setup35.sh").read_text(encoding="utf-8")
    stages = (HERE / "test_session_stages.txt").read_text(encoding="utf-8")
    for marker in (mac_watch35.DONE, mac_watch35.STOP, mac_watch35.STOP_FAILED):
        assert marker in chain
    assert 'log "pod stop sent with: $how"' in chain
    assert mac_watch35.STOP not in "[00:00:00] == chain STOPPED: setup is marked with ! and failed"
    assert 'TARBALL="$WORK/test-session-out.tgz"' in chain and 'PULLED="$WORK/PULLED"' in chain
    assert mac_watch35.TARBALL == "/workspace/test-session-out.tgz"
    header = mac_watch35.LAUNCH.replace("/workspace/omrs", "<repo>")
    assert f"tmux new-session -d -s exp35 '{header}'" in launch
    assert 'SESSION_ENV="${SESSION_ENV:-/workspace/session.env}"' in launch
    assert 'OUT_DIR="${OUT_DIR:-$WORK/exp35-test/out}"' in launch
    assert f'INPUTS_TGZ="{mac_watch35.INPUTS_TGZ}"' in setup
    assert f"--inputs {mac_watch35.INPUTS} " in stages
    assert f"{mac_watch35.INPUTS}/{mac_watch35.EXAMPLES}" in stages
    assert '--commit "$COMMIT"' in stages
