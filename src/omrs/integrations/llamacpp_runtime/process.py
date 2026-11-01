"""Process work of a managed runtime: start, checks and stop (design D4, D5).

This is the only module that starts or stops a ``llama-server`` process.
Every launch is an argument list with no shell. The child starts in a new
session, reads standard input from ``/dev/null`` and writes its output
straight to ``server.log``, so it has no pipe to the starter and survives the
starter's exit. Python opens descriptors as non-inheritable (PEP 446), and
``close_fds`` is on, so the child never holds a lock descriptor.

A recorded pid is trusted only when ``ps -o command= -p <pid>`` still shows
the recorded program path. That reads one pid; it never lists processes. A
pid that fails the check is never signalled.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Literal

from . import rules
from .spec import DeclaredFile, RuntimeSpec

#: Seconds to wait for ``GET /health`` to return 200 after a start.
HEALTH_TIMEOUT_SECONDS = 180.0
#: Seconds between two health checks.
HEALTH_POLL_SECONDS = 0.5
#: Seconds between SIGTERM and SIGKILL when a server stops.
STOP_GRACE_SECONDS = 10.0
#: ``server.log`` is emptied in place when it passes this size.
LOG_CAP_BYTES = 5 * 1024 * 1024
#: The output file in each runtime folder.
LOG_FILE = "server.log"
#: The fixed part of llama-server's bind error line (``server.cpp``).
BIND_ERROR_MARK = "couldn't bind HTTP server socket"
#: The ``GET /props`` field that holds the build (``b11941-<commit>``).
#: Confirmed on the official b11941 macOS arm64 binary (task 6.4, 2026-11-01):
#: ``"build_info": "b11941-19ff817fb"``.
PROPS_BUILD_FIELD = "build_info"

_BUILD_IN_VERSION = re.compile(r"build[:\s]+(\d+)")
_BUILD_IN_PROPS = re.compile(r"^b?(\d+)")
_TOOL_TIMEOUT = 30.0

HealthOutcome = Literal["ok", "exited", "timeout"]


class StartRefused(Exception):
    """A check or start failed with one fixed reason (``rules.REASONS``).

    Attributes:
        reason: The fixed reason.
        detail: A file name for ``file-changed``, else ``""``.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


# ── Checks ──────────────────────────────────────────────────────────────


def read_build(binary: str, env: Mapping[str, str]) -> int | None:
    """Return the build number that ``<binary> --version`` reports, or ``None``."""
    try:
        run = subprocess.run(  # noqa: S603 - fixed argv, program rule already applied
            [binary, "--version"],
            capture_output=True,
            text=True,
            env=dict(env),
            timeout=_TOOL_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    found = _BUILD_IN_VERSION.search(f"{run.stdout}\n{run.stderr}")
    return int(found.group(1)) if found else None


def props_build(url_base: str, timeout: float = 5.0) -> int | None:
    """Return the build an external server reports in ``GET /props``."""
    status, body = http_get_json(f"{url_base.rstrip('/')}/props", timeout)
    value = body.get(PROPS_BUILD_FIELD) if status == 200 and isinstance(body, dict) else None
    found = _BUILD_IN_PROPS.match(str(value)) if value is not None else None
    return int(found.group(1)) if found else None


def changed_file(files: Sequence[DeclaredFile]) -> str | None:
    """Return the name of the first declared file whose SHA-256 differs, else ``None``.

    A missing or unreadable file counts as changed.
    """
    for declared in files:
        digest = hashlib.sha256()
        try:
            with open(declared.path, "rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    digest.update(chunk)
        except OSError:
            return Path(declared.path).name
        if digest.hexdigest() != declared.sha256.lower():
            return Path(declared.path).name
    return None


# ── One recorded pid ────────────────────────────────────────────────────


def _ps(pid: int, column: str) -> str:
    try:
        run = subprocess.run(  # noqa: S603 - fixed argv, one pid
            ["ps", "-ww", "-o", f"{column}=", "-p", str(pid)],  # noqa: S607 - system ps
            capture_output=True,
            text=True,
            timeout=_TOOL_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return run.stdout.strip() if run.returncode == 0 else ""


def owns(pid: int, binary: str) -> bool:
    """Return whether *pid* runs and its command line holds *binary*.

    A zombie shows no arguments, so it fails the check as a gone process does.
    """
    if pid <= 0 or not binary:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # pragma: no cover - another user's pid: not ours
        return False
    return binary in _ps(pid, "command")


def rss_bytes(pid: int) -> int | None:
    """Return the resident memory of *pid* in bytes (``ps -o rss=`` times 1024)."""
    text = _ps(pid, "rss")
    return int(text) * 1024 if text.isdigit() else None


# ── Ports and health ────────────────────────────────────────────────────


def free_port() -> int:
    """Return a loopback port that was free a moment ago."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def port_in_use(port: int) -> bool:
    """Return whether something accepts connections on 127.0.0.1:*port*."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def http_get_json(url: str, timeout: float) -> tuple[int, object]:
    """GET *url*; return ``(status, parsed JSON or {})``, ``(0, {})`` when unreachable."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as answer:  # noqa: S310 - loopback
            status, raw = int(answer.status), answer.read()
    except urllib.error.HTTPError as error:
        status, raw = int(error.code), b""
    except (OSError, ValueError):
        return 0, {}
    try:
        return status, json.loads(raw or b"{}")
    except ValueError:
        return status, {}


def wait_healthy(port: int, alive: Callable[[], bool]) -> HealthOutcome:
    """Poll ``GET /health`` until 200, the process ends or the time runs out.

    A 503 answer means the model is still loading. The timeout and the poll
    interval are read from this module at call time.
    """
    deadline = time.monotonic() + HEALTH_TIMEOUT_SECONDS
    url = f"http://127.0.0.1:{port}/health"
    while True:
        if not alive():
            return "exited"
        if http_get_json(url, timeout=2.0)[0] == 200:
            return "ok"
        if time.monotonic() >= deadline:
            return "timeout"
        time.sleep(HEALTH_POLL_SECONDS)


# ── Start, stop and log ─────────────────────────────────────────────────


def launch(argv: Sequence[str], env: Mapping[str, str], log_path: Path) -> subprocess.Popen[bytes]:
    """Start *argv* detached, with its output in *log_path* (emptied first).

    The log is opened with ``O_APPEND``, so emptying it in place later sends
    the child's next line to the new end of the file. A daemon thread reaps
    the child, so a stopped server never stays a zombie.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    fd = os.open(log_path, flags, 0o600)
    try:
        proc = subprocess.Popen(  # noqa: S603 - argument list, no shell, rules applied
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=fd,
            stderr=fd,
            env=dict(env),
            start_new_session=True,
            close_fds=True,
        )
    finally:
        os.close(fd)
    threading.Thread(target=proc.wait, name=f"reap-{proc.pid}", daemon=True).start()
    return proc


def log_has_bind_error(log_path: Path) -> bool:
    """Return whether the end of *log_path* holds llama-server's bind error."""
    try:
        with open(log_path, "rb") as handle:
            handle.seek(max(0, log_path.stat().st_size - 8192))
            tail = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return False
    return BIND_ERROR_MARK in tail


def cap_log(log_path: Path) -> bool:
    """Empty *log_path* in place when it passes ``LOG_CAP_BYTES``; return whether it did."""
    try:
        if log_path.stat().st_size <= LOG_CAP_BYTES:
            return False
        os.truncate(log_path, 0)
    except OSError:
        return False
    return True


def _signal_group(pid: int, sig: int) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        if os.getpgid(pid) == pid:
            os.killpg(pid, sig)  # the server leads its own session, so pgid == pid
        else:  # pragma: no cover - a group signal would reach another group
            os.kill(pid, sig)


def stop(pid: int, binary: str) -> bool:
    """Stop the server *pid* when it is still ours: SIGTERM, grace, then SIGKILL.

    Returns:
        ``True`` when a signal went to the server, ``False`` when the pid
        was gone or ran another command (never signalled).
    """
    if not owns(pid, binary):
        return False
    _signal_group(pid, signal.SIGTERM)
    deadline = time.monotonic() + STOP_GRACE_SECONDS
    while time.monotonic() < deadline:
        if not owns(pid, binary):
            return True
        time.sleep(0.05)
    _signal_group(pid, signal.SIGKILL)
    deadline = time.monotonic() + 5.0
    while owns(pid, binary) and time.monotonic() < deadline:
        time.sleep(0.05)
    return True


# ── The start sequence ──────────────────────────────────────────────────

#: A free-port runtime retries a bind failure this many times (4 tries in all).
BIND_RETRIES = 3


def _check(spec: RuntimeSpec) -> rules.ModelKind:
    """Apply the checks before a start, in design order; return the model kind."""
    if not rules.check_binary(spec.binary):
        raise StartRefused("binary-invalid")
    kind: rules.ModelKind = "file"
    if spec.role != "ocr":
        flag = "-hf" if "-hf" in spec.argv else "-m"
        model = spec.argv[spec.argv.index(flag) + 1] if flag in spec.argv else ""
        if rules.model_kind(model) is None:
            raise StartRefused("model-invalid")
        kind = "hf" if flag == "-hf" else "file"
    return kind


def start_server(
    spec: RuntimeSpec,
    folder: Path,
    environ: Mapping[str, str],
    on_launched: Callable[[int, int], None],
) -> tuple[int, int]:
    """Check and start one server for *spec*; return ``(pid, port)`` once healthy.

    Args:
        spec: The managed runtime to start.
        folder: Its runtime folder (``server.log`` goes there).
        environ: The OMRS process environment; the child gets the minimal
            subset of :func:`rules.child_environment`.
        on_launched: Called with ``(pid, port)`` right after each launch, so
            the caller records a ``starting`` server before the health wait.

    Raises:
        StartRefused: With ``binary-invalid``, ``model-invalid``,
            ``wrong-build``, ``file-changed``, ``port-in-use``, ``exited``,
            ``timeout`` or ``bind-failed``. Nothing runs after a refusal.
    """
    kind = _check(spec)
    env = rules.child_environment(environ, kind)
    if spec.build is not None and read_build(spec.binary, env) != spec.build:
        raise StartRefused("wrong-build")
    changed = changed_file(spec.files)
    if changed is not None:
        raise StartRefused("file-changed", changed)
    log_path = folder / LOG_FILE
    tries = 0
    while True:
        fixed = spec.port_policy == "fixed"
        port = (spec.port or 0) if fixed else free_port()
        if fixed and port_in_use(port):
            raise StartRefused("port-in-use")
        proc = launch(spec.launch_argv(port), env, log_path)
        on_launched(proc.pid, port)
        outcome = wait_healthy(port, lambda child=proc: child.poll() is None)
        if outcome == "ok":
            return proc.pid, port
        if outcome == "timeout":
            stop(proc.pid, spec.binary)
            raise StartRefused("timeout")
        if not log_has_bind_error(log_path):
            raise StartRefused("exited")
        if fixed:  # a fixed port cannot move
            raise StartRefused("port-in-use")
        tries += 1
        if tries > BIND_RETRIES:
            raise StartRefused("bind-failed")
