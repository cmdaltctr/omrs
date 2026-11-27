"""SSH and scp to the Exp 35 pod, and the watcher's one-line log (mac_watch35.py).

The key goes to ssh by path only. No key is printed.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

_SSH_OPTIONS = ("BatchMode=yes", "StrictHostKeyChecking=no", "UserKnownHostsFile=/dev/null",
                "ConnectTimeout=20", "ServerAliveInterval=15", "LogLevel=ERROR")  # fmt: skip


def say(text: str) -> None:
    print(f"[{datetime.now(UTC):%H:%M:%S}] {text}", flush=True)


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

    def __init__(self, host: str, port: int | str, key: Path) -> None:
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
