"""``RuntimeManager``: the runtimes of one OMRS process (design D1, D7 to D9, D11).

``compose.py`` builds one manager per process and injects its leases (see
:mod:`.lease`). The manager owns what spans leases: the idle timer, the
operator stop, the ``omrs web`` start-up sweep, the status list and the
``atexit`` leave. Callers in ``core/`` get a lease by injection and never
import this package.
"""

from __future__ import annotations

import atexit
import logging
import os
import signal
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from . import locks, process
from .lease import (
    OPERATOR_STOP,
    RuntimeLease,
    RuntimeRequestFailed,
    RuntimeUnavailable,
    reason_text,
)
from .locks import LockFile
from .spec import RUNTIME_ID_RE, RuntimeSpec
from .state import read_server_record, runtime_dir, state_root, write_server_record

__all__ = [
    "IDLE_CHECK_SECONDS",
    "IDLE_STOP_SECONDS",
    "OPERATOR_STOP",
    "RuntimeLease",
    "RuntimeManager",
    "RuntimeRequestFailed",
    "RuntimeUnavailable",
    "install_sigterm_exit",
    "reason_text",
]

logger = logging.getLogger(__name__)

#: A lease leaves after this many seconds with no request (design D7). Fixed.
IDLE_STOP_SECONDS = 600
#: Seconds between two idle checks of the manager's timer thread.
IDLE_CHECK_SECONDS = 60.0


def install_sigterm_exit() -> None:
    """Turn SIGTERM into ``SystemExit`` so ``atexit`` hooks leave every lease (D9).

    Only the main thread can set a handler; a handler someone else set stays.
    """
    if threading.current_thread() is not threading.main_thread():
        return
    if signal.getsignal(signal.SIGTERM) in (signal.SIG_DFL, None):
        signal.signal(signal.SIGTERM, _exit_on_sigterm)


def _exit_on_sigterm(signum: int, _frame: object) -> None:
    raise SystemExit(128 + signum)


class RuntimeManager:
    """The runtimes of one OMRS process (``compose.py`` builds one).

    Args:
        root: The state root; ``state_root()`` by default.
        environ: The environment the child's minimal environment comes from;
            the process environment at each start by default.
        exit_hook: Register :meth:`close` with ``atexit`` (design D9).
    """

    def __init__(
        self,
        root: Path | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        exit_hook: bool = True,
    ) -> None:
        self.root = Path(root) if root is not None else state_root()
        self._environ = environ
        self._leases: dict[str, RuntimeLease] = {}
        self._lock = threading.Lock()
        self._timer_lock = threading.Lock()
        self._timer: threading.Thread | None = None
        self._closed = threading.Event()
        self._exit_hook = exit_hook
        if exit_hook:
            atexit.register(self.close)

    @property
    def environ(self) -> Mapping[str, str]:
        """The environment a child's minimal environment is taken from."""
        return self._environ if self._environ is not None else os.environ

    def lease(self, spec: RuntimeSpec) -> RuntimeLease:
        """Return this process's lease of *spec*; a changed spec replaces the old lease."""
        with self._lock:
            old = self._leases.get(spec.id)
            if old is not None and old.spec == spec:
                return old
            lease = RuntimeLease(self, spec)
            self._leases[spec.id] = lease
        if old is not None:
            old.leave()
        return lease

    def stop(self, runtime_id: str) -> bool:
        """Operator stop (design D8): stop the recorded server, record ``operator``.

        Returns:
            ``True`` when a server was stopped; ``False`` for an external
            runtime, a stopped runtime or a pid that is no longer ours.

        Raises:
            ValueError: *runtime_id* is not a runtime id.
        """
        folder = runtime_dir(self.root, runtime_id)
        lease = self._leases.get(runtime_id)
        if lease is not None and lease.spec.mode == "external":
            return False
        if not locks.LOCKS_SUPPORTED or not folder.exists():
            return False
        start = LockFile(folder / "start.lock")
        start.acquire()
        try:
            record = read_server_record(folder)
            if record is None or not process.stop(record.pid, record.binary):
                return False
            record.state, record.stopped_by = "stopped", "operator"
            write_server_record(folder, record)
        finally:
            start.close()
        if lease is not None and lease.generation == record.generation:
            with lease._lock:
                lease._operator_stopped = True
        return True

    def _stop_if_unused(self, folder: Path, stopped_by: str) -> bool:
        """The second half of a leave: stop the server when no client holds it."""
        probe = LockFile(folder / "clients.lock")
        try:
            if not probe.acquire(shared=False, blocking=False):
                return False  # another client exists
            start = LockFile(folder / "start.lock")
            start.acquire()
            try:
                record = read_server_record(folder)
                if record is None or not process.stop(record.pid, record.binary):
                    return False
                record.state, record.stopped_by = "stopped", stopped_by  # type: ignore[assignment]
                write_server_record(folder, record)
                return True
            finally:
                start.close()
        finally:
            probe.close()

    def sweep(self) -> list[str]:
        """Stop every owned server that no OMRS process uses (``omrs web`` start-up, D9).

        A runtime whose ``start.lock`` is busy is being started or stopped, so
        it is skipped. Returns the ids of the stopped runtimes.
        """
        folder_root = self.root / "runtimes"
        if not locks.LOCKS_SUPPORTED or not folder_root.is_dir():
            return []
        stopped: list[str] = []
        for folder in sorted(folder_root.iterdir()):
            if not folder.is_dir() or not RUNTIME_ID_RE.fullmatch(folder.name):
                continue
            record = read_server_record(folder)
            if record is None or not process.owns(record.pid, record.binary):
                continue
            start = LockFile(folder / "start.lock")
            try:
                if not start.acquire(blocking=False):
                    continue
                probe = LockFile(folder / "clients.lock")
                try:
                    if probe.acquire(shared=False, blocking=False) and process.stop(
                        record.pid, record.binary
                    ):
                        record.state, record.stopped_by = "stopped", "last-client"
                        write_server_record(folder, record)
                        stopped.append(folder.name)
                finally:
                    probe.close()
            finally:
                start.close()
        return stopped

    def status(
        self, specs: Sequence[RuntimeSpec], used_by: Mapping[str, Sequence[str]] | None = None
    ) -> list[dict[str, Any]]:
        """Return one ``GET /v1/runtimes`` item per spec. Starts and writes nothing."""
        names = used_by or {}
        return [self._status_item(spec, list(names.get(spec.id, ()))) for spec in specs]

    def _status_item(self, spec: RuntimeSpec, used_by: list[str]) -> dict[str, Any]:
        item: dict[str, Any] = {
            "id": spec.id,
            "role": spec.role,
            "mode": spec.mode,
            "state": "stopped",
            "reason": None,
            "reason_text": None,
            "memory_bytes": None,
            "clients": "none",
            "used_by": used_by,
            "address": None,
            "files_checked": False,
        }
        if spec.mode == "external":
            parts = urlsplit(spec.url_base)
            item["address"] = f"{parts.hostname}:{parts.port or 80}" if parts.hostname else None
            health = process.http_get_json(f"{spec.url_base.rstrip('/')}/health", 1.0)[0]
            item["state"] = {200: "running", 503: "starting"}.get(health, "stopped")
            return item
        if not locks.LOCKS_SUPPORTED:
            item["state"], item["reason"] = "failed", "not-supported"
            item["reason_text"] = reason_text("not-supported")
            return item
        folder = runtime_dir(self.root, spec.id)
        item["files_checked"] = bool(spec.files)
        record = read_server_record(folder)
        if record is not None and process.owns(record.pid, record.binary):
            item["state"] = "running" if record.state == "running" else "starting"
            item["address"] = f"127.0.0.1:{record.port}"
            item["memory_bytes"] = process.rss_bytes(record.pid)
        elif record is not None and record.reason:
            item["state"], item["reason"] = "failed", record.reason
            item["reason_text"] = record.reason_text or reason_text(record.reason)
        elif record is not None and record.state != "stopped":
            # Recorded as live but the process is gone: it crashed.
            item["state"], item["reason"] = "failed", "exited"
            item["reason_text"] = reason_text("exited")
        if (folder / "clients.lock").exists():
            probe = LockFile(folder / "clients.lock")
            try:
                item["clients"] = "none" if probe.acquire(blocking=False) else "some"
            finally:
                probe.close()
        return item

    # ── Idle timer and exit ─────────────────────────────────────────────

    def _ensure_timer(self) -> None:
        with self._timer_lock:
            if self._closed.is_set() or (self._timer is not None and self._timer.is_alive()):
                return
            self._timer = threading.Thread(
                target=self._watch_idle, name="omrs-runtime-idle", daemon=True
            )
            self._timer.start()

    def _watch_idle(self) -> None:
        while not self._closed.wait(IDLE_CHECK_SECONDS):
            now = time.monotonic()
            for lease in list(self._leases.values()):
                if lease._idle_due(now, IDLE_STOP_SECONDS):
                    lease._idle_leave(IDLE_STOP_SECONDS)

    def close(self) -> None:
        """Leave every lease and stop the idle timer (normal exit, design D9)."""
        self._closed.set()
        if self._exit_hook:
            atexit.unregister(self.close)
        with self._lock:
            leases = list(self._leases.values())
        for lease in leases:
            try:
                lease.leave()
            except Exception:  # noqa: BLE001 - leave every other lease
                logger.warning("leaving runtime %s failed", lease.spec.id, exc_info=True)
