#!/usr/bin/env python3
"""Offline smoke test for the dots-mocr engine on llama.cpp (tasks 2.6 and 2b.6; run in 3.1, 3.2).

SEPARATE from the main OMRS pytest suite: it needs the provisioned engine
environment, the downloaded model and the llama.cpp build. It follows the
script of the PyTorch engine (removed at cut-over), with these differences:

- Without a flag the script prints its plan and does nothing else. It
  creates no file, starts no process and makes no network call.
- ``--provision`` runs the provision command first (about 4.4 GB of
  download, with operator approval and licence acceptance), then does
  everything ``--run`` does.
- ``--run`` skips provisioning and probes the capabilities, then sends one
  page-listed parse request per ``--case`` to one worker process.
- The script starts the engine's runtime the way OMRS does. The host's
  ``RuntimeManager`` runs the ``llama-server`` that ``pyproject.toml``
  declares, with a scratch ``OMRS_STATE_DIR`` (never the real state folder).
  The worker gets the address in ``OMRS_OCR_RUNTIME_URL``. The script leaves
  the runtime at the end, and the server stops with the last client. This
  needs the OMRS environment: run it with ``uv run --no-sync python``.
- The worker runs under ``sandbox-exec``. It only calls the server on
  127.0.0.1, so the profile allows loopback connections and nothing else.
- Peak memory has two parts. ``/usr/bin/time -l`` reports the footprint of
  the worker process. The kernel's lifetime peak footprint of the
  ``llama-server`` process (Experiment 41's method) is read after every
  response. Metal memory counts in both, as it is unified memory.
- After the runtime is left, ``ps`` must show no process that runs from the
  engine's llama.cpp folder. A leftover process fails the run.

Usage::

    python3 ocr-workers/engines/dots-mocr/smoke_test.py          # plan only
    uv run --no-sync python ocr-workers/engines/dots-mocr/smoke_test.py \\
        --case eq01=/path/eq01.pdf:2 --case eq01=/path/eq01.pdf:3 --run

Evidence (capability JSON, per-page Markdown, ``run.json``, worker standard
error) goes to ``smoke_evidence/``.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ENGINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = ENGINE_DIR.parents[2]
ENGINE_NAME = "dots-mocr"
BACKEND_ID = "dots_mocr_llamacpp"
VENV_PYTHON = ENGINE_DIR / ".venv" / "bin" / "python"
EVIDENCE_DIR = ENGINE_DIR / "smoke_evidence"
PROTOCOL_VERSION = "1.1"
MODEL_CACHE_ENV = "OMRS_OCR_MODEL_CACHE"
#: The variable in which the host gives a worker the address of its runtime.
RUNTIME_URL_ENV = "OMRS_OCR_RUNTIME_URL"
STATE_DIR_ENV = "OMRS_STATE_DIR"
SANDBOX_EXEC = "/usr/bin/sandbox-exec"

#: Seconds to wait for the llama-server to leave after the worker exits.
CLEAN_EXIT_WAIT_SECONDS = 10.0

#: Deny every network operation, then allow outbound connections to localhost
#: only. The worker is a client of the host's llama-server and listens for
#: nothing. A connection to any other address, or a bind, fails at once with
#: ``Operation not permitted``.
SANDBOX_PROFILE = (
    '(version 1)(allow default)(deny network*)(allow network-outbound (remote ip "localhost:*"))'
)

_PEAK_RE = re.compile(r"^\s*(\d+)\s+peak memory footprint", re.MULTILINE)
_BUILD_RE = re.compile(r"\bb(\d{4,})\b")
#: Index of ``ri_lifetime_max_phys_footprint`` in ``rusage_info_v4``, as u64 words.
_PEAK_INDEX = 2 + 28

Case = tuple[str, Path, int]


def parse_case(text: str) -> Case:
    """Parse ``name=path.pdf:page`` into its three parts.

    Raises:
        argparse.ArgumentTypeError: The text is not in that form.
    """
    name, _, rest = text.partition("=")
    path, _, page = rest.rpartition(":")
    if not name or not path or not page.isdigit():
        raise argparse.ArgumentTypeError(f"case {text!r} is not name=path.pdf:page")
    return name, Path(path).expanduser().resolve(), int(page)


def provision_argv() -> list[str]:
    """Return the provision command as an argument list."""
    return [
        sys.executable,
        str(REPO_ROOT / "ocr-workers" / "provision.py"),
        ENGINE_NAME,
        "--accept-model-licence",
    ]


def cache_dir() -> Path:
    """Return the engine's cache root (design D8): the variable, else ``.model-cache``."""
    root = os.environ.get(MODEL_CACHE_ENV, "").strip()
    if root:
        return Path(root).expanduser() / ENGINE_NAME
    return ENGINE_DIR / ".model-cache"


def llama_dir() -> Path:
    """Return the folder that holds the unpacked llama.cpp release."""
    return cache_dir() / "llama.cpp"


def sandbox_available() -> bool:
    """Return True on macOS when ``sandbox-exec`` exists."""
    return sys.platform == "darwin" and Path(SANDBOX_EXEC).is_file()


def engine_ready() -> bool:
    """Return True when the engine's virtual environment exists."""
    return VENV_PYTHON.is_file()


def probe_argv() -> list[str]:
    """Return the capability probe command."""
    return [str(VENV_PYTHON), "-m", "omrs_ocr_worker_core", "--capabilities"]


def worker_command() -> list[str]:
    """Return the sandboxed, timed worker command."""
    return [
        SANDBOX_EXEC,
        "-p",
        SANDBOX_PROFILE,
        "/usr/bin/time",
        "-l",
        str(VENV_PYTHON),
        "-m",
        "omrs_ocr_worker_core",
    ]


def plan_lines(cases: list[Case]) -> list[str]:
    """Return the numbered plan. It only builds text."""
    step = iter(range(1, 10))
    lines = ["plan:"]
    note = "(only with --provision; downloads about 4.4 GB)"
    lines.append(f"  {next(step)}. provision {note}:")
    lines.append("       python3 ocr-workers/provision.py dots-mocr --accept-model-licence")
    lines.append(f"  {next(step)}. capability probe: {' '.join(probe_argv())}")
    lines.append(f"       backend_id must be {BACKEND_ID!r}")
    lines.append(f"  {next(step)}. start the runtime with the host's RuntimeManager:")
    lines.append(
        "       it runs the llama-server the engine declares, with a scratch OMRS_STATE_DIR"
    )
    lines.append(f"  {next(step)}. offline parse, one worker, network blocked except loopback;")
    lines.append(f"       the worker gets the runtime address in {RUNTIME_URL_ENV}:")
    lines.append(f"       {' '.join(worker_command())}")
    if cases:
        for name, pdf, page in cases:
            lines.append(f"       case {name}: {pdf} page {page}")
    else:
        lines.append("       case: none given (--run needs at least one --case name=path.pdf:page)")
    lines.append(f"  {next(step)}. peak memory: /usr/bin/time -l (worker) plus the kernel's")
    lines.append("       lifetime peak footprint of the llama-server (read after each response)")
    lines.append(f"  {next(step)}. leave the runtime (the server stops with the last client)")
    lines.append(f"  {next(step)}. clean exit: no process may run from {llama_dir()}")
    lines.append(f"  {next(step)}. evidence written to {EVIDENCE_DIR}:")
    files = ["capabilities.json", "run.json", "worker-stderr.log"]
    files += [f"{name}-p{page:03d}.md" for name, _, page in cases]
    lines.extend(f"       {name}" for name in files)
    return lines


def parse_time_peak(text: str) -> int | None:
    """Return the ``peak memory footprint`` bytes from ``/usr/bin/time -l`` output."""
    found = _PEAK_RE.search(text)
    return int(found.group(1)) if found else None


def peak_footprint(pid: int) -> int | None:
    """Return the lifetime peak physical footprint of *pid* in bytes (macOS), or None.

    The kernel keeps this high-water mark and it includes Metal memory
    (Experiment 41 ``run_ocr.py``).
    """
    try:
        buf = (ctypes.c_uint64 * 48)()
        lib = ctypes.CDLL("/usr/lib/libproc.dylib")
        ok = lib.proc_pid_rusage(pid, 4, ctypes.byref(buf)) == 0
    except (OSError, AttributeError):
        return None
    return int(buf[_PEAK_INDEX]) if ok else None


class RuntimeSession:
    """The engine's llama-server, run by the host's runtime manager (design D2).

    The session reads the runtime block of the engine's ``pyproject.toml``
    with the host's rules and joins the runtime like an OMRS process does.
    """

    def __init__(self, state: Path) -> None:
        """Hold the state folder; start nothing."""
        self._state = state
        self._manager: Any = None
        self._spec: Any = None
        self.url = ""

    def start(self) -> str:
        """Start the server through the manager and return its address.

        Raises:
            RuntimeError: The host refuses the start (wrong build, a changed
                file, a server that does not become healthy). The text says why.
            ValueError: The engine's runtime block breaks a rule.
            SystemExit: OMRS is not importable; run the script with ``uv run``.
        """
        try:
            from omrs.integrations.llamacpp_runtime.manager import RuntimeManager
            from omrs.integrations.ocr_worker.manifest import declared_runtime
            from omrs.integrations.ocr_worker.routes import RouteCommand
            from omrs.integrations.ocr_worker.runtime import runtime_spec
        except ImportError as exc:
            raise SystemExit(
                f"error: cannot import OMRS ({exc}); run this script with "
                "`uv run --no-sync python ocr-workers/engines/dots-mocr/smoke_test.py`"
            ) from exc
        declared = declared_runtime(ENGINE_DIR, cache_dir())
        if declared is None:
            raise ValueError(f"{ENGINE_NAME} declares no runtime in its pyproject.toml")
        route = RouteCommand(command=(), cwd=str(ENGINE_DIR), runtime=declared)
        self._spec = runtime_spec(route, declared)
        self._manager = RuntimeManager(self._state, exit_hook=False)
        self.url = self._manager.lease(self._spec).join()
        return self.url

    def pid(self) -> int | None:
        """Return the pid the manager recorded for the server, or None."""
        if self._spec is None:
            return None
        from omrs.integrations.llamacpp_runtime.state import read_server_record, runtime_dir

        record = read_server_record(runtime_dir(self._state, self._spec.id))
        return record.pid if record is not None else None

    def leave(self) -> None:
        """Leave the runtime. The server stops when this was the last client."""
        if self._manager is not None:
            self._manager.close()


def worker_env(url: str) -> dict[str, str]:
    """Return the worker's environment: this process's, plus the runtime address."""
    return {**os.environ, RUNTIME_URL_ENV: url}


def list_processes() -> list[str]:
    """Return one ``"<pid> <command line>"`` string for every process."""
    done = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["/bin/ps", "-axww", "-o", "pid=,command="],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return done.stdout.splitlines()


def leftover_processes(folder: Path, lines: list[str]) -> list[str]:
    """Return the process lines whose command line runs from *folder*."""
    return [line for line in lines if f"{folder}/" in line]


def check_clean_exit() -> tuple[bool, list[str]]:
    """Wait for the server to leave, then report whether none remains."""
    deadline = time.monotonic() + CLEAN_EXIT_WAIT_SECONDS
    while True:
        left = leftover_processes(llama_dir(), list_processes())
        if not left or time.monotonic() >= deadline:
            return not left, left
        time.sleep(0.5)


def _ask(worker: subprocess.Popen[str], request: dict[str, Any]) -> tuple[str, float]:
    """Send one request line; return the response line and the seconds taken."""
    assert worker.stdin is not None and worker.stdout is not None  # noqa: S101
    started = time.perf_counter()
    try:
        worker.stdin.write(json.dumps(request, sort_keys=True) + "\n")
        worker.stdin.flush()
        line = worker.stdout.readline()
    except OSError:
        line = ""
    return line, time.perf_counter() - started


def run_worker(cases: list[Case], session: RuntimeSession) -> dict[str, Any]:
    """Run every case in one sandboxed worker and save the Markdown.

    Args:
        cases: The pages to parse.
        session: The started runtime; its address goes to the worker.

    Returns:
        ``results`` (one dict per case), the worker ``stderr`` text and the
        ``peak`` memory block.
    """
    # Standard error goes to a file: a full pipe would block the worker.
    stderr_path = EVIDENCE_DIR / "worker-stderr.log"
    results: list[dict[str, Any]] = []
    server_peak = 0
    with stderr_path.open("w", encoding="utf-8") as stderr_file:
        worker = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            worker_command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            text=True,
            encoding="utf-8",
            cwd=ENGINE_DIR,
            env=worker_env(session.url),
        )
        try:
            for name, pdf, page in cases:
                request = {
                    "id": f"smoke-{name}-p{page}",
                    "pages": [page],
                    "pdf_path": str(pdf),
                    "protocol_version": PROTOCOL_VERSION,
                    "type": "parse",
                }
                line, seconds = _ask(worker, request)
                try:
                    response = json.loads(line) if line.strip() else {}
                except ValueError:
                    response = {}
                pages = response.get("pages_markdown") or []
                text = pages[0] if len(pages) == 1 else ""
                ok = response.get("ok") is True and response.get("id") == request["id"]
                (EVIDENCE_DIR / f"{name}-p{page:03d}.md").write_text(text, encoding="utf-8")
                pid = session.pid()
                server_peak = max(server_peak, (peak_footprint(pid) if pid else 0) or 0)
                results.append(
                    {
                        "case": name,
                        "page": page,
                        "ok": ok,
                        "seconds": round(seconds, 1),
                        "chars": len(text.strip()),
                    }
                )
                print(f"{name} p{page}: ok={ok} seconds={seconds:.1f} chars={len(text.strip())}")
                if not ok:
                    print(f"error: response {line[:600]!r}", file=sys.stderr)
        finally:
            if worker.stdin is not None:
                worker.stdin.close()
            try:
                worker.wait(timeout=120)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait()
    stderr = stderr_path.read_text(encoding="utf-8")
    worker_peak = parse_time_peak(stderr)
    peak = {
        "worker_bytes": worker_peak,
        "server_bytes": server_peak or None,
        "total_bytes": (worker_peak or 0) + server_peak or None,
        "method": (
            "worker: /usr/bin/time -l 'peak memory footprint' of the worker process; "
            "server: proc_pid_rusage lifetime max physical footprint of the llama-server "
            "pid in the runtime's server.json, read after each response; total is their sum"
        ),
    }
    return {"results": results, "stderr": stderr, "peak": peak}


def run(cases: list[Case]) -> int:
    """Probe, parse every case in one sandboxed worker, and save evidence."""
    probe = subprocess.run(  # noqa: S603 - fixed argv, no shell
        probe_argv(),
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        cwd=ENGINE_DIR,
    )
    if probe.returncode != 0 or not probe.stdout.strip():
        print(f"error: capability probe failed: {probe.stderr[-2000:]}", file=sys.stderr)
        return 1
    capabilities = json.loads(probe.stdout.splitlines()[0])
    if capabilities.get("backend_id") != BACKEND_ID:
        print(f"error: probe backend_id {capabilities.get('backend_id')!r}", file=sys.stderr)
        return 1
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "capabilities.json").write_text(
        json.dumps(capabilities, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"capabilities: {json.dumps(capabilities, sort_keys=True)}")

    state = Path(tempfile.mkdtemp(prefix="omrs-smoke-state-"))
    os.environ[STATE_DIR_ENV] = str(state)
    session = RuntimeSession(state)
    try:
        try:
            session.start()
        except (RuntimeError, ValueError, OSError) as exc:
            print(f"error: the runtime did not start: {exc}", file=sys.stderr)
            return 1
        print(f"runtime: {session.url} (state folder {state})")
        outcome = run_worker(cases, session)
    finally:
        session.leave()
    results: list[dict[str, Any]] = outcome["results"]
    clean, left = check_clean_exit()
    revision = str((capabilities.get("pipeline") or {}).get("revision", ""))
    build = _BUILD_RE.search(revision)
    summary = {
        "cases": results,
        "network": "denied by sandbox-exec except loopback (127.0.0.1 and ::1)",
        "sandbox_profile": SANDBOX_PROFILE,
        "pipeline_revision": revision or None,
        "llama_cpp_build": int(build.group(1)) if build else None,
        "peak_memory": outcome["peak"],
        "state_dir": str(state),
        "clean_exit": clean,
        "leftover_processes": left,
        "note": "the first case's seconds include the model load by the llama-server",
    }
    (EVIDENCE_DIR / "run.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"peak memory bytes: {json.dumps(outcome['peak'].get('total_bytes'))}")
    print(f"clean exit: {clean}")
    failed = [r for r in results if not r["ok"] or r["chars"] == 0]
    if failed or not clean:
        for item in failed:
            print(f"error: {item['case']} p{item['page']} ok={item['ok']} chars={item['chars']}")
        for line in left:
            print(f"error: process left running: {line}", file=sys.stderr)
        print("worker stderr tail:", outcome["stderr"][-3000:], file=sys.stderr)
        return 1
    print("OCR PASSED")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point. No flag means plan only."""
    parser = argparse.ArgumentParser(description="Offline smoke test for dots-mocr on llama.cpp.")
    parser.add_argument(
        "--case", action="append", type=parse_case, default=[], help="name=path.pdf:page"
    )
    parser.add_argument("--provision", action="store_true", help="provision first, then run")
    parser.add_argument("--run", action="store_true", help="run on the provisioned engine")
    args = parser.parse_args(argv)
    cases: list[Case] = args.case
    execute = args.run or args.provision
    if execute and not cases:
        parser.error("--run and --provision need at least one --case name=path.pdf:page")
    if not execute:
        print("\n".join(plan_lines(cases)))
        print("plan only: nothing ran, no file was written.")
        return 0
    if not sandbox_available():
        print(
            "error: the offline check needs macOS sandbox-exec; run it on macOS",
            file=sys.stderr,
        )
        return 1
    missing = [str(pdf) for _, pdf, _ in cases if not pdf.is_file()]
    if missing:
        print(f"error: missing PDF {missing}", file=sys.stderr)
        return 2
    if args.provision:
        print("provisioning: this downloads about 4.4 GB", flush=True)
        done = subprocess.run(provision_argv(), check=False, cwd=REPO_ROOT)  # noqa: S603
        if done.returncode != 0:
            print(f"error: provisioning exited {done.returncode}", file=sys.stderr)
            return 1
    if not engine_ready():
        print("error: engine not provisioned (use --provision)", file=sys.stderr)
        return 1
    return run(cases)


if __name__ == "__main__":
    raise SystemExit(main())
