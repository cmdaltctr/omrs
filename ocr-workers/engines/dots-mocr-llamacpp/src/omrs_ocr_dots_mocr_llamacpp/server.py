"""Start, use and stop the pinned ``llama-server`` (design D2, D5, D8).

The worker owns the server:

- it starts on the first parse, on a free loopback port, and the worker
  reuses it until it ends;
- it stops on SIGTERM and on normal exit;
- a server left by a killed worker is stopped by the next worker. A pid
  file records the pid and the binary path. The next start stops that pid
  only when it is alive and its command line holds the engine's own
  binary path.

The server log is capped (default 1 MB) and rotated once.
"""

from __future__ import annotations

import atexit
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
from pathlib import Path
from types import FrameType
from typing import IO

from . import pins
from .paths import llama_dir

HOST = "127.0.0.1"
LOG_CAP_BYTES = 1_000_000
BINARY_NAME = "llama-server"

_BUILD_RE = re.compile(r"build\s+(\d+)")


class ServerError(Exception):
    """The server cannot start or is not healthy.

    Attributes:
        code: Stable machine-readable error code.
        message: Human-readable description.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ── Pure helpers ───────────────────────────────────────────────────────────


def free_port() -> int:
    """Return a free loopback port (bind to port 0, read the port, release it)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def server_command(binary: Path, model: Path, projector: Path, port: int) -> list[str]:
    """Return the ``llama-server`` command line of Experiment 41 arm D4 (design D5)."""
    return [
        str(binary),
        "-m",
        str(model),
        "--mmproj",
        str(projector),
        "--host",
        HOST,
        "--port",
        str(port),
        *pins.SERVER_FLAGS,
    ]


def find_binary() -> Path:
    """Return the unpacked ``llama-server`` of the pinned release.

    Raises:
        ServerError: If provisioning has not unpacked it.
    """
    binary = llama_dir() / BINARY_NAME
    if not binary.is_file():
        raise ServerError(
            "server_binary_missing",
            f"no llama-server at {binary}; run "
            "`python3 ocr-workers/provision.py dots-mocr-llamacpp --accept-model-licence`",
        )
    return binary


def binary_build(binary: Path) -> int:
    """Return the build number that ``<binary> --version`` reports.

    Raises:
        ServerError: If the binary is missing, cannot run, or prints no build.
    """
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [str(binary), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ServerError("server_binary_missing", f"no llama-server at {binary}") from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ServerError(
            "server_binary_blocked",
            f"cannot run {binary}: {exc}. On macOS, if the system blocked the file, run "
            f"`xattr -d com.apple.quarantine {binary}`",
        ) from exc
    match = _BUILD_RE.search(result.stdout + result.stderr)
    if match is None:
        raise ServerError("server_build", f"{binary} --version printed no build number")
    return int(match.group(1))


def check_build(binary: Path) -> None:
    """Refuse a binary whose build is not the pinned one (design D3).

    Raises:
        ServerError: If the reported build differs from :data:`pins.LLAMA_BUILD`.
    """
    found = binary_build(binary)
    if found != pins.LLAMA_BUILD:
        raise ServerError(
            "server_build",
            f"llama-server at {binary} is build {found}; the engine needs build "
            f"{pins.LLAMA_BUILD}. Run the provisioning command again.",
        )


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _command_line(pid: int) -> str:
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["ps", "-ww", "-o", "command=", "-p", str(pid)],  # noqa: S607 - ps is on every PATH
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def _wait_gone(pid: int, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not _alive(pid):
            return True
        time.sleep(0.05)
    return not _alive(pid)


def stop_stale(pid_path: Path, binary: Path, stop_timeout: float) -> None:
    """Stop a server that an earlier worker left behind (design D8).

    The pid is stopped only when it is alive and its command line holds
    *binary*. Any other process is left alone. The pid file is removed.
    """
    try:
        pid = int(json.loads(pid_path.read_text(encoding="utf-8"))["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        pid = 0
    pid_path.unlink(missing_ok=True)
    if pid <= 0 or not _alive(pid) or str(binary) not in _command_line(pid):
        return
    os.kill(pid, signal.SIGTERM)
    if not _wait_gone(pid, stop_timeout):
        os.kill(pid, signal.SIGKILL)
        _wait_gone(pid, 5.0)


# ── The log ────────────────────────────────────────────────────────────────


class _CappedLog:
    """A log file that rotates once to ``<name>.1`` when it would pass the cap."""

    def __init__(self, path: Path, cap: int) -> None:
        self.path, self.cap = path, cap
        self._rotated = path.with_name(path.name + ".1")
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            os.replace(path, self._rotated)
        self._handle: IO[bytes] = path.open("wb")
        self._size = 0

    def write(self, line: bytes) -> None:
        """Append a line, rotating first when it would pass the cap."""
        if self._size + len(line) > self.cap:
            self._handle.close()
            os.replace(self.path, self._rotated)
            self._handle = self.path.open("wb")
            self._size = 0
        self._handle.write(line)
        self._handle.flush()
        self._size += len(line)

    def close(self) -> None:
        """Close the file."""
        self._handle.close()


def _pump(stream: IO[bytes], log: _CappedLog) -> None:
    for line in stream:
        log.write(line)


# ── The server ─────────────────────────────────────────────────────────────


class LlamaServer:
    """One pinned ``llama-server`` process, owned by one worker."""

    def __init__(  # noqa: PLR0913 - the lifecycle's tunables, set once
        self,
        binary: Path,
        model: Path,
        projector: Path,
        *,
        log_path: Path,
        pid_path: Path,
        start_timeout: float = 180.0,
        poll_interval: float = 0.5,
        stop_timeout: float = 10.0,
        log_cap: int = LOG_CAP_BYTES,
    ) -> None:
        self.binary, self.model, self.projector = binary, model, projector
        self.log_path, self.pid_path = log_path, pid_path
        self.start_timeout, self.poll_interval = start_timeout, poll_interval
        self.stop_timeout, self.log_cap = stop_timeout, log_cap
        self._lock = threading.RLock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._log: _CappedLog | None = None
        self._pump: threading.Thread | None = None
        self._port = 0

    @property
    def base_url(self) -> str:
        """Return the URL of the running server."""
        return f"http://{HOST}:{self._port}"

    def ensure_started(self) -> str:
        """Start the server if it is not running; return its base URL.

        Raises:
            ServerError: If the build is wrong, the server exits twice, or
                it is not healthy within the start timeout.
        """
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return self.base_url
            self._release()
            check_build(self.binary)
            stop_stale(self.pid_path, self.binary, self.stop_timeout)
            self._log = _CappedLog(self.log_path, self.log_cap)
            for attempt in (1, 2):
                self._launch(free_port())
                if self._wait_healthy():
                    return self.base_url
                if attempt == 2:
                    self._release()
                    raise ServerError(
                        "server_start_failed",
                        f"llama-server exited at start; see the log {self.log_path}",
                    )
            raise AssertionError("unreachable")  # pragma: no cover

    def stop(self) -> None:
        """Stop the server (SIGTERM, then SIGKILL after the stop timeout). Safe to repeat."""
        with self._lock:
            proc = self._proc
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=self.stop_timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            self._release()

    def install_shutdown_hooks(self) -> None:
        """Stop the server on normal exit and on SIGTERM (design D8).

        The host ends a worker with SIGTERM, which would otherwise skip the
        exit hook and leave the server running.
        """
        atexit.register(self.stop)
        if threading.current_thread() is not threading.main_thread():
            return
        previous = signal.getsignal(signal.SIGTERM)

        def on_sigterm(signum: int, frame: FrameType | None) -> None:
            self.stop()
            if callable(previous):
                previous(signum, frame)
                return
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            os.kill(os.getpid(), signal.SIGTERM)

        signal.signal(signal.SIGTERM, on_sigterm)

    # ── Internals ──────────────────────────────────────────────────────

    def _launch(self, port: int) -> None:
        assert self._log is not None  # noqa: S101 - set by ensure_started
        self._port = port
        self._proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            server_command(self.binary, self.model, self.projector, port),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        assert self._proc.stdout is not None  # noqa: S101 - PIPE was requested
        self._pump = threading.Thread(
            target=_pump, args=(self._proc.stdout, self._log), daemon=True
        )
        self._pump.start()
        self.pid_path.parent.mkdir(parents=True, exist_ok=True)
        self.pid_path.write_text(
            json.dumps({"pid": self._proc.pid, "binary": str(self.binary)}), encoding="utf-8"
        )

    def _wait_healthy(self) -> bool:
        """Poll ``/health``; return True when healthy, False if the process exited.

        Raises:
            ServerError: If the start timeout passes first (the server is stopped).
        """
        assert self._proc is not None  # noqa: S101 - set by _launch
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + self.start_timeout
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                self._forget_process()
                return False
            try:
                with opener.open(f"{self.base_url}/health", timeout=2) as response:
                    if response.status == 200:
                        return True
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(self.poll_interval)
        self.stop()
        raise ServerError(
            "server_not_healthy",
            f"llama-server was not healthy after {self.start_timeout:g} s; "
            f"see the log {self.log_path}",
        )

    def _forget_process(self) -> None:
        """Drop the finished process and its pump, and remove our pid file."""
        if self._pump is not None:
            self._pump.join(timeout=5)
        if self._proc is not None:
            self._remove_pid_file(self._proc.pid)
        self._proc, self._pump = None, None

    def _remove_pid_file(self, pid: int) -> None:
        """Remove the pid file when it names *pid*; a file for another server stays."""
        try:
            recorded = int(json.loads(self.pid_path.read_text(encoding="utf-8"))["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            return
        if recorded == pid:
            self.pid_path.unlink(missing_ok=True)

    def _release(self) -> None:
        """Forget the process and close the log."""
        self._forget_process()
        if self._log is not None:
            self._log.close()
        self._log = None
