"""The llama.cpp Chat card adapter over the shared ``chat`` runtime (task 5.1).

The adapter maps the runtime state files to the card's status. Every process
here is a fake ``llama-server`` from ``llamacpp_fake``. No real
``llama-server`` runs and the user's own server on its own port is never
contacted. The lease, start and stop rules have their own tests in
``tests/test_llamacpp_runtime_*.py``.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit import test_web_llamacpp_server as server  # noqa: E402
from tests.unit.llamacpp_fake import wait_until  # noqa: E402

from omrs.integrations.llamacpp_runtime import process  # noqa: E402
from omrs.transports.api import llamacpp_server as adapter  # noqa: E402

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")

harness = server.harness
rig = server.rig

RUNTIME = Path(process.__file__).parent
SCANNED = [Path(adapter.__file__), *sorted(RUNTIME.glob("*.py"))]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_start_leaves_a_server_running_with_other_values_alone(rig: Any) -> None:
    with rig() as r:
        r.save_all()
        assert r.post("start").json()["state"] == "running"
        first = r.program.pids()[-1]
        assert r.put({"context_window": 8192}).status_code == 200

        body = r.post("start").json()

        assert (body["state"], body["pending_restart"]) == ("running", True)
        assert r.program.pids() == [first]


def test_a_crashed_server_reads_failed_exited(rig: Any) -> None:
    with rig() as r:
        r.save_all()
        r.post("start")
        pid = r.program.pids()[-1]
        os.killpg(pid, signal.SIGKILL)
        wait_until(lambda: not _alive(pid))

        body = r.get()

        assert (body["state"], body["reason"], body["pid_running"]) == ("failed", "exited", False)


def test_a_server_that_ignores_sigterm_gets_sigkill_after_the_grace(
    rig: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(process, "STOP_GRACE_SECONDS", 1.0)
    with rig(mode="ignore-term") as r:
        r.save_all()
        r.post("start")
        pid = r.program.pids()[-1]
        began = time.monotonic()

        body = r.post("stop").json()

        assert body["state"] == "stopped"
        assert time.monotonic() - began >= 1.0
        wait_until(lambda: not _alive(pid))


def test_stop_with_nothing_recorded_signals_nothing(rig: Any) -> None:
    with rig() as r:
        body = r.post("stop").json()
        assert (body["state"], body["reason"], body["pid_running"]) == ("stopped", None, False)
        assert r.program.pids() == []


@pytest.mark.parametrize("path", SCANNED, ids=lambda p: p.name)
def test_the_runtime_code_looks_up_no_process_by_name_or_port(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    for word in ("pkill", "killall", "lsof", "pgrep", "psutil", "process_iter", "netstat"):
        assert word not in source
    assert "shell=True" not in source


def test_the_adapter_is_not_imported_by_the_cli_or_stdio_transports() -> None:
    root = Path(adapter.__file__).parents[1]
    for folder in ("cli", "mcp"):
        for path in (root / folder).rglob("*.py"):
            assert "llamacpp_server" not in path.read_text(encoding="utf-8"), path
