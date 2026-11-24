"""Mac side of the Exp 35 test pod session (task 9.2): copy, launch, watch, pull.

Usage and order: TEST_SESSION_RUNBOOK.md. Calls no RunPod API; the last line is always
``DELETE_POD_NOW <pod id>``. No key is read or printed. Idle = stage timeout + 10 min.
Test hook: MAC_WATCH35_FAKE_CLOCK=1 makes every wait move a virtual clock (no sleep).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
REPO = EXP.parent.parent
PLAN = EXP / "plan.json"

WORK = "/workspace"
INPUTS, REMOTE_REPO, LOG = f"{WORK}/inputs", f"{WORK}/omrs", f"{WORK}/test-session.log"
TARBALL, OWN_TARBALL = f"{WORK}/test-session-out.tgz", f"{WORK}/watcher-out.tgz"
OUT_PARENT, OUT_NAME = f"{WORK}/exp35-test", "out"
PULLED, SESSION_ENV, SESSION = f"{WORK}/PULLED", f"{WORK}/session.env", "exp35"
INPUTS_TGZ, EXAMPLES, STOP_GRACE_MIN = "exp35-inputs.tgz", "classify-examples.json", 30
LAUNCH = f"bash {REMOTE_REPO}/experiments/{EXP.name}/prefreeze/launch35.sh > {LOG} 2>&1"

POLL_S, SSH_POLL_S, STOP_POLL_S = 60, 15, 10
SSH_WAIT_S, IDLE_S, SSH_LOST_S, IDLE_GRACE_S = 15 * 60, 30 * 60, 10 * 60, 10 * 60
SETTLE_S, STOP_WAIT_S, BEAT_S = 10 * 60, 5 * 60, 30 * 60

DONE, STOP = "TEST_SESSION_DONE", "STOP:"
STOP_FAILED, STOP_SENT = "POD_STOP_FAILED", "pod stop sent with:"
_STAGE_START = re.compile(r"== \S+: start \(timeout (\d+)s\)")  # idle = timeout + grace
_SHOWN = re.compile(r"^\[\d\d:\d\d:\d\d\] (==|test pod session|PULLED seen|no .*PULLED)")
EXIT = {"done": 0, "internal": 1, "refused": 2, "stop-failed": 3, "no-ssh": 4, "setup": 5,
        "stop-line": 6, "session-ended": 7, "idle": 8, "wall-cap": 9, "ssh-lost": 10,
        "pull": 11, "interrupted": 12}  # fmt: skip
_SECRET_PARTS = (".env", "secrets", ".config", ".ssh")
_SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)
_SSH_OPTIONS = ("BatchMode=yes", "StrictHostKeyChecking=no", "UserKnownHostsFile=/dev/null",
                "ConnectTimeout=20", "ServerAliveInterval=15", "LogLevel=ERROR")  # fmt: skip

LAUNCH_CMD = (
    "command -v tmux >/dev/null || { echo 'tmux is not on the pod'; exit 1; }; "
    f"if tmux has-session -t {SESSION} 2>/dev/null; then "
    f"echo 'tmux session {SESSION} already exists'; exit 1; fi; "
    f"tmux new-session -d -s {SESSION} {shlex.quote(LAUNCH)}"
)
WHICH_CMD = (
    f"if [ -f {TARBALL} ] && [ -f {TARBALL}.sha256 ]; then echo chain; "
    f"elif [ -d {OUT_PARENT}/{OUT_NAME} ]; then echo out; else echo none; fi"
)
# GNU tar exit 1 means a file changed while it was read (the chain may still write).
PACK_CMD = (
    f"cd {OUT_PARENT} && {{ tar -czf {OWN_TARBALL} {OUT_NAME}; [ $? -le 1 ]; }} "
    f"&& sha256sum {OWN_TARBALL} > {OWN_TARBALL}.sha256"
)


class Interrupted(Exception):
    """SIGTERM, SIGINT or SIGHUP reached the watcher."""


def _interrupt(signum: int, _frame: object) -> None:
    for sig in _SIGNALS:  # raise once: later signals (uv run forwards them) cannot stop the pull
        signal.signal(sig, signal.SIG_IGN)
    raise Interrupted(signal.Signals(signum).name)


_FAKE_CLOCK = os.environ.get("MAC_WATCH35_FAKE_CLOCK") == "1"
_offset = 0.0


def now() -> float:
    return time.monotonic() + _offset


def pause(seconds: float) -> None:
    """Sleep; with MAC_WATCH35_FAKE_CLOCK=1, move the virtual clock instead (tests)."""
    global _offset
    if _FAKE_CLOCK:
        _offset += seconds
    else:
        time.sleep(seconds)


def say(text: str) -> None:
    print(f"[{datetime.now(UTC):%H:%M:%S}] {text}", flush=True)


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def inputs() -> tuple[Path, list[str]]:
    """Return the data root and the files pod_setup35.sh checks (Legal stays out, D1)."""
    sys.path[:0] = [p for p in (str(EXP), str(REPO)) if p not in sys.path]
    import datasets35 as ds

    root, plan = ds.data_root(), json.loads(PLAN.read_text(encoding="utf-8"))
    rels = [r for n in ("financebench", "freshstack", "bioasq") for r in ds.input_hashes(n, plan)]
    manifest = next(r for r in rels if r.endswith("PDFS_MANIFEST.json"))
    names = json.loads((root / manifest).read_text(encoding="utf-8"))["files"]
    rels += ds.pdf_hashes(root, [Path(f"{name}.pdf") for name in names])
    corpus = ds._FS_CORPUS
    rels += [f"{corpus}/{n}" for n in ["download.json", *ds.freshstack_pin(plan)["corpus_files"]]]
    return root, sorted(set(rels))


def unsafe(rel: str, root: Path) -> str | None:
    """Return why *rel* must not go into the tarball, or ``None`` when it may."""
    path = Path(rel)
    if path.is_absolute() or ".." in path.parts:
        return "is not a plain relative path"
    if any(p.startswith(_SECRET_PARTS) for p in path.parts) or path.suffix in (".key", ".pem"):
        return "looks like a secret"
    real, home = (root / path).resolve(), Path.home().resolve()
    private = real.is_relative_to(home / ".config") or real.is_relative_to(home / ".ssh")
    if private or not real.is_relative_to(root):
        return f"resolves to {real}: outside the data root, or under ~/.config or ~/.ssh"
    return None if real.is_file() else "is missing"


@dataclass
class Plan:
    """The checked local side of one session."""

    commit: str
    key: Path
    examples: Path
    repo_url: str = ""
    root: Path = Path()
    folder: Path = Path()
    rels: list[str] = field(default_factory=list)


def prepare(args: argparse.Namespace) -> tuple[list[str], Plan]:
    """Check every local input; return the problems and the plan. Writes nothing."""
    plan = Plan(args.commit, args.ssh_key.expanduser(), args.examples.expanduser())
    problems = []
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):  # it goes unquoted into pod commands
        problems.append("--commit must be the full 40-character commit SHA")
    if not plan.key.is_file():
        problems.append(f"SSH key {plan.key} not found")
    try:
        json.loads(plan.examples.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        problems.append(f"--examples {plan.examples} is not a JSON file ({type(error).__name__})")
    git = ["git", "-C", str(REPO), "remote", "get-url", "origin"]
    origin = subprocess.run(git, capture_output=True, text=True, check=False)  # noqa: S603
    plan.repo_url = args.repo_url or (origin.stdout.strip() if origin.returncode == 0 else "")
    if not plan.repo_url:
        problems.append("no --repo-url, and this checkout has no origin remote")
    try:
        plan.root, plan.rels = inputs()
        day = f"test-session-{datetime.now(UTC):%Y-%m-%d}"
        plan.folder = plan.root / "experiments" / EXP.name / day
    except Exception as error:  # noqa: BLE001 - any failure here is a refusal with its reason
        return [*problems, f"cannot list the inputs: {type(error).__name__}: {error}"], plan
    if plan.folder.exists():
        problems.append(f"results folder {plan.folder} already exists; it is never overwritten")
    problems += [f"input {rel} {why}" for rel in plan.rels if (why := unsafe(rel, plan.root))]
    return problems, plan


def build_inputs(plan: Plan) -> tuple[str, str]:
    """Write the inputs folder (tarball, .sha256, examples); return the two SHA-256 values."""
    folder = plan.folder / "inputs"
    folder.mkdir()
    tgz = folder / INPUTS_TGZ
    with tarfile.open(tgz, "w:gz", compresslevel=6) as tar:
        for rel in plan.rels:
            tar.add((plan.root / rel).resolve(), arcname=rel, recursive=False)
    digest = sha256(tgz)
    (folder / f"{INPUTS_TGZ}.sha256").write_text(f"{digest}  {INPUTS_TGZ}\n", encoding="utf-8")
    shutil.copyfile(plan.examples, folder / EXAMPLES)
    say(f"  {tgz}: {len(plan.rels)} files, {tgz.stat().st_size / 1e6:.1f} MB, SHA-256 {digest}")
    return digest, sha256(folder / EXAMPLES)


def setup_cmds(plan: Plan, tgz_sha: str, examples_sha: str) -> list[str]:
    """Step 5: check the inputs, place the repository, write session.env, start the chain."""
    pairs = f"{tgz_sha} {INPUTS_TGZ} {examples_sha} {EXAMPLES}"
    return [
        f"cd {INPUTS} && printf '%s  %s\\n' {pairs} | sha256sum -c -",
        f"set -e; [ -d {REMOTE_REPO}/.git ] || git clone -q {shlex.quote(plan.repo_url)} "
        f"{REMOTE_REPO}; cd {REMOTE_REPO}; git fetch -q origin; "
        f'git checkout -q --detach {plan.commit}; test "$(git rev-parse HEAD)" = {plan.commit}',
        f"printf 'COMMIT=%s\\nSTOP_GRACE_MIN=%s\\n' {plan.commit} {STOP_GRACE_MIN} > {SESSION_ENV}",
        LAUNCH_CMD,
    ]


def poll_cmd(offset: int) -> str:
    alive = f's=0; tmux has-session -t {SESSION} 2>/dev/null && s=1; echo "ALIVE $s"'
    return f"{alive}; tail -c +{offset + 1} {LOG} 2>/dev/null; true"


def _call(args: list[str], timeout: float) -> subprocess.CompletedProcess[bytes] | None:
    try:
        kw = {"capture_output": True, "stdin": subprocess.DEVNULL, "timeout": timeout}
        return subprocess.run(args, check=False, **kw)  # noqa: S603 - fixed argument lists
    except subprocess.TimeoutExpired:
        return None


def _good(result: subprocess.CompletedProcess[bytes] | None, what: str) -> bool:
    if result is None or result.returncode != 0:
        text = "" if result is None else (result.stdout + result.stderr).decode("utf-8", "replace")
        status = "timed out" if result is None else f"exit {result.returncode}"
        say(f"  {what} failed ({status}) {text.strip()[-400:]}".rstrip())
    return result is not None and result.returncode == 0


class Pod:
    """SSH and scp to the pod as root; the key goes to ssh by path only."""

    def __init__(self, host: str, port: int, key: Path) -> None:
        options = [part for option in _SSH_OPTIONS for part in ("-o", option)]
        self.host, self.port, self.login = host, port, f"root@{host}"
        self.ssh_base = ["ssh", "-i", str(key), "-p", str(port), *options, self.login]
        self.scp_base = ["scp", "-q", "-i", str(key), "-P", str(port), *options]

    def remote(self, path: str) -> str:
        return f"{self.login}:{path}"

    def ssh(self, command: str, timeout: float = 120) -> subprocess.CompletedProcess[bytes] | None:
        return _call([*self.ssh_base, command], timeout)

    def ok(self, command: str, timeout: float = 300) -> bool:
        return _good(self.ssh(command, timeout), "remote step")

    def copy(self, sources: Sequence[str], dest: str, timeout: float = 3600) -> bool:
        return _good(_call([*self.scp_base, *sources, dest], timeout), "scp")


@dataclass
class Watch:
    """What the watcher knows of the chain from its log."""

    offset: int = 0
    partial: str = ""
    alive: bool = True
    done: bool = False
    stop_line: str = ""
    stop_failed: bool = False
    stop_sent: bool = False
    last_growth: float = 0.0
    idle_s: int = IDLE_S

    def scan(self, line: str) -> None:
        started = _STAGE_START.search(line)
        if started:  # a quiet stage may run to its own timeout, plus a grace
            self.idle_s = max(IDLE_S, int(started.group(1)) + IDLE_GRACE_S)
        self.done |= DONE in line
        self.stop_failed |= STOP_FAILED in line
        self.stop_sent |= STOP_SENT in line
        if STOP in line and not self.stop_line:
            self.stop_line = line.strip()
        if any(m in line for m in (DONE, STOP, STOP_FAILED, STOP_SENT)) or _SHOWN.match(line):
            print(f"  pod| {line.rstrip()[:300]}", flush=True)

    def feed(self, text: str) -> None:
        lines = (self.partial + text).split("\n")
        self.partial = lines.pop()
        for line in lines:
            self.scan(line)


def poll(pod: Pod, w: Watch) -> bool | None:
    """Read the session state and the new log bytes: ``None`` when SSH fails, else growth."""
    result = pod.ssh(poll_cmd(w.offset))
    if result is None or result.returncode != 0 or not result.stdout.startswith(b"ALIVE "):
        return None
    head, _, body = result.stdout.partition(b"\n")
    w.alive = head.strip() == b"ALIVE 1"
    w.offset += len(body)
    w.feed(body.decode("utf-8", "replace"))
    return bool(body)


def setup(pod: Pod, plan: Plan, tgz_sha: str, examples_sha: str) -> str | None:
    """Steps 3 to 5; return the EXIT key of a failure, or ``None``."""
    say(f"step 3: wait up to {SSH_WAIT_S // 60} min for SSH on {pod.host}:{pod.port}")
    start = now()
    while (up := pod.ssh("true", timeout=60)) is None or up.returncode != 0:
        if now() - start >= SSH_WAIT_S:
            say(f"no SSH after {SSH_WAIT_S // 60} min")
            return "no-ssh"
        pause(SSH_POLL_S)
    say(f"step 4: copy the inputs to {INPUTS}")
    names = (INPUTS_TGZ, f"{INPUTS_TGZ}.sha256", EXAMPLES)
    files, dest = [str(plan.folder / "inputs" / n) for n in names], pod.remote(f"{INPUTS}/")
    if not pod.ok(f"mkdir -p {INPUTS}") or not (pod.copy(files, dest) or pod.copy(files, dest)):
        return "setup"
    say(f"step 5: check the SHA-256 on the pod; {REMOTE_REPO} at {plan.commit}; launch")
    commands = setup_cmds(plan, tgz_sha, examples_sha)
    return None if all(pod.ok(cmd, timeout=900) for cmd in commands) else "setup"


def watch(pod: Pod, w: Watch, cap_s: float, start: float) -> str:
    """Step 6: poll until an end condition; return its EXIT key."""
    failing_since: float | None = None
    beat = w.last_growth = now()
    try:
        while True:
            grew = poll(pod, w)
            at = now()
            if grew is None:
                failing_since = at if failing_since is None else failing_since
                if at - failing_since >= SSH_LOST_S:
                    say(f"no SSH for {SSH_LOST_S // 60} min")
                    return "ssh-lost"
            else:
                failing_since, w.last_growth = None, at if grew else w.last_growth
                if w.stop_line or w.done:
                    return "stop-line" if w.stop_line else "done"
                if not w.alive:
                    say(f"tmux session {SESSION} ended without {DONE}")
                    return "session-ended"
                if at - w.last_growth >= w.idle_s:
                    say(f"idle: no new log byte for {w.idle_s // 60} min")
                    return "idle"
            if at - start >= cap_s:
                say(f"wall-clock cap of {cap_s / 3600:g} h reached")
                return "wall-cap"
            if at - beat >= BEAT_S:
                beat, quiet = at, int((at - w.last_growth) // 60)
                say(f"still watching: log {w.offset} bytes, last new byte {quiet} min ago")
            pause(POLL_S)
    except Interrupted as stop:
        say(f"{stop} received: ending the session now")
        return "interrupted"


def wait_for(pod: Pod, w: Watch, met: Callable[[], bool], limit: float, step: float) -> bool | None:
    """Poll until *met*: ``True``; ``False`` at the limit; ``None`` when SSH fails."""
    start = now()
    while not met():
        if now() - start >= limit:
            return False
        pause(step)
        if poll(pod, w) is None:
            return None
    return True


def pull(pod: Pod, folder: Path) -> str:
    """Step 7: copy the log and the outputs; return ok, hash-mismatch, pull-failed or none."""
    say(f"step 7: copy the chain log and the outputs into {folder}")
    pod.copy([pod.remote(LOG)], str(folder))
    which = pod.ssh(WHICH_CMD)
    if which is None or which.returncode != 0:
        return "pull-failed"
    kind, remote = which.stdout.decode("utf-8", "replace").strip(), TARBALL
    if kind == "none":
        say("!!! OUTPUTS MISSING: the pod holds no tarball and no output folder")
        return "none"
    if kind == "out":
        say(f"  the chain wrote no tarball: packing {OUT_PARENT}/{OUT_NAME} into {OWN_TARBALL}")
        if not pod.ok(PACK_CMD, timeout=1800):
            return "pull-failed"
        remote = OWN_TARBALL
    tgz, files = folder / Path(remote).name, [pod.remote(remote), pod.remote(f"{remote}.sha256")]
    if not (pod.copy(files, str(folder)) or pod.copy(files, str(folder))):  # one retry
        return "pull-failed"
    want = (folder / f"{tgz.name}.sha256").read_text(encoding="utf-8").split()[:1]
    if want == [found := sha256(tgz)]:
        say(f"  SHA-256 matches: {tgz.name} {found}")
        return "ok"
    # ssh checks every byte in transit, so a second copy cannot fix a mismatch.
    say(f"!!! HASH_MISMATCH: {tgz} is {found}; the pod recorded {' '.join(want)}. Report it.")
    return "hash-mismatch"


def end_session(pod: Pod, w: Watch, reason: str, folder: Path) -> tuple[str, str, str]:
    """Pull, write PULLED, then wait for the pod's own stop; return the three verdicts."""
    if reason == "stop-line" and w.alive and not w.done:
        say(f"STOP: line seen; waiting up to {SETTLE_S // 60} min for {DONE}")
        wait_for(pod, w, lambda: w.done or not w.alive, SETTLE_S, POLL_S)
    outputs = pull(pod, folder)
    marker = "written" if pod.ok(f"printf '%s\\n' {outputs} > {PULLED}") else "not-written"
    say(f"{PULLED}: {marker} ({outputs})")
    if not w.done:
        return outputs, marker, "not-expected"
    seen: bool | None = True
    if not (w.stop_sent or w.stop_failed or not w.alive):
        say(f"waiting up to {STOP_WAIT_S // 60} min for the pod to stop itself")
        met = lambda: w.stop_sent or w.stop_failed or not w.alive  # noqa: E731
        seen = wait_for(pod, w, met, STOP_WAIT_S, STOP_POLL_S)
    if w.stop_failed or w.stop_sent:
        return outputs, marker, "FAILED" if w.stop_failed else "sent"
    return outputs, marker, "ssh-closed" if seen is None else "not-seen"


def dry_run(args: argparse.Namespace, plan: Plan, problems: list[str]) -> int:
    pod = Pod(args.ssh_host, args.ssh_port, plan.key)
    say(f"DRY RUN: no ssh, scp or tmux call, no file written. Key {plan.key} is not read.")
    say(f"step 1: create {plan.folder}")
    say(f"step 2: build {plan.folder / 'inputs' / INPUTS_TGZ} from {plan.root} (no Legal, D1):")
    sizes = {r: (plan.root / r).stat().st_size for r in plan.rels if not unsafe(r, plan.root)}
    for rel in plan.rels:
        say(f"  {sizes.get(rel, 0):>12,}  {rel}")
    say(f"  {len(plan.rels)} files, {sum(sizes.values()) / 1e6:.1f} MB before compression")
    remote = [
        f"3 {shlex.join(pod.ssh_base)} true (every {SSH_POLL_S} s, up to {SSH_WAIT_S // 60} min)",
        f"4 ssh 'mkdir -p {INPUTS}'; {shlex.join([*pod.scp_base, '<3 files>', pod.remote(INPUTS)])}"
        f" (the tarball, its .sha256 and the examples as {EXAMPLES})",
        *(f"5 ssh {shlex.quote(c)}" for c in setup_cmds(plan, "<tgz sha>", "<examples sha>")),
        f"6 every {POLL_S} s: ssh {shlex.quote(poll_cmd(0))}; ends: see the runbook",
        f"7 ssh {shlex.quote(WHICH_CMD)}; on 'out': ssh {shlex.quote(PACK_CMD)}",
        f"7 scp {LOG} and the tarball with its .sha256; check; ssh 'printf <verdict> > {PULLED}'",
    ]
    for step in remote:
        say(f"step {step}")
    for problem in problems:
        say(f"PROBLEM: {problem}")
    say(f"DRY RUN found {len(problems)} problem(s)")
    return EXIT["refused"] if problems else EXIT["done"]


def run(args: argparse.Namespace) -> int:
    """Steps 1 to 8; return the exit code."""
    start = now()
    problems, plan = prepare(args)
    if args.dry_run:
        return dry_run(args, plan, problems)
    if problems:
        say("REFUSED: " + "; ".join(problems))
        return EXIT["refused"]
    for sig in _SIGNALS:
        signal.signal(sig, _interrupt)
    say(f"steps 1 and 2: create {plan.folder}; build the inputs tarball (no Legal RAG Bench, D1)")
    plan.folder.mkdir(parents=True)
    (plan.folder / "watcher.pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    pod = Pod(args.ssh_host, args.ssh_port, plan.key)
    if failed := setup(pod, plan, *build_inputs(plan)):
        return EXIT[failed]
    say(f"step 6: watching {LOG} every {POLL_S} s (cap {args.wall_cap_h:g} h)")
    w = Watch()
    reason = watch(pod, w, args.wall_cap_h * 3600, start)
    outputs, marker, stop = end_session(pod, w, reason, plan.folder)
    if w.stop_failed:
        code = EXIT["stop-failed"]
        say("!!! POD_STOP_FAILED: the pod did not stop itself and the GPU still bills.")
    else:
        code = EXIT[reason] if reason != "done" else EXIT["done" if outputs == "ok" else "pull"]
    result = f"RESULT end={reason} outputs={outputs} pulled-marker={marker} pod-stop={stop}"
    result += f" exit={code} folder={plan.folder}"
    (plan.folder / "watch-summary.txt").write_text(result + "\n", encoding="utf-8")
    print(result, flush=True)
    return code


def main(argv: Sequence[str] | None = None) -> int:
    """Run the session watch; always end with the DELETE_POD_NOW line."""
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for name in ("--pod-id", "--ssh-host", "--commit"):
        parser.add_argument(name, required=True)
    parser.add_argument("--ssh-port", required=True, type=int)
    parser.add_argument("--examples", required=True, type=Path, help="classifier examples JSON")
    parser.add_argument("--ssh-key", type=Path, default=Path("~/.ssh/runpod_omrs_measure"))
    parser.add_argument("--repo-url", help="default: the origin URL of this checkout")
    parser.add_argument("--wall-cap-h", type=float, default=15.5)
    parser.add_argument("--dry-run", action="store_true", help="print every step, run nothing")
    try:
        code = run(parser.parse_args(argv))
    except SystemExit as error:
        if error.code == 0:
            raise
        code = EXIT["refused"]
    except (Interrupted, KeyboardInterrupt) as error:
        say(f"stopped by {error or 'SIGINT'} before the end steps finished")
        code = EXIT["interrupted"]
    except Exception as error:  # noqa: BLE001 - the delete line must still come last
        say(f"INTERNAL ERROR: {type(error).__name__}: {error}")
        code = EXIT["internal"]
    pod_id = argv[argv.index("--pod-id") + 1] if "--pod-id" in argv[:-1] else "UNKNOWN"
    prefix = "[dry-run] a real run ends with: " if "--dry-run" in argv else ""
    print(f"{prefix}DELETE_POD_NOW {pod_id}", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
