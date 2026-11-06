"""``RuntimeLease``: one process's use of one runtime (design D4 to D8).

A lease that uses a managed runtime holds a shared lock on ``clients.lock``.
It adopts, starts or stops a server only while it holds ``start.lock``. To
leave, it drops the shared lock and tries an exclusive lock without
blocking: success means no other client, so the server stops.

Lock order: a process blocks on ``clients.lock`` only while it holds no other
runtime lock. Under ``start.lock`` only non-blocking attempts on
``clients.lock`` happen, so no wait cycle can form.

:class:`RuntimeUnavailable` means nothing was sent; :class:`RuntimeRequestFailed`
means the request was sent and the server went away under it. Get a lease
from :meth:`omrs.integrations.llamacpp_runtime.manager.RuntimeManager.lease`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from collections.abc import Awaitable, Callable, Iterator
from typing import TYPE_CHECKING, Any, TypeVar

from . import locks, process
from .locks import LockFile
from .rules import NOT_PROVISIONED, NOT_PROVISIONED_TEXT
from .spec import RuntimeSpec
from .state import ServerRecord, read_server_record, runtime_dir, write_server_record

if TYPE_CHECKING:
    from .manager import RuntimeManager

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: The reason of a request refused or cut by an operator stop (design D8).
OPERATOR_STOP = "operator-stop"
#: Tries to replace another version of a runtime before ``version-busy``.
_VERSION_TRIES = 3

_REASON_TEXTS = {
    "binary-invalid": "The llama-server program is missing, cannot run or has another name.",
    "model-invalid": "The model is not a .gguf file or a Hugging Face id.",
    "not-loopback": "The server address is not on this computer.",
    "port-in-use": "Another program uses the port.",
    "exited": "The server stopped before it was ready.",
    "timeout": "The server was not ready in time and was stopped.",
    "not-configured": "No program or model is set.",
    "not-supported": "Managed servers need file locks, which this system does not have.",
    "version-busy": "Another OMRS process still uses the older version of this server.",
    "wrong-build": "The llama-server build is not the build the runtime declares.",
    "file-changed": "A model file changed: {name}.",
    "bind-failed": "The server could not open a port after 4 tries.",
    NOT_PROVISIONED: NOT_PROVISIONED_TEXT,
    OPERATOR_STOP: "An operator stopped this server.",
}


def reason_text(reason: str, detail: str = "") -> str:
    """Return the fixed plain-English line of *reason*.

    A detail fills ``{name}``; a line without ``{name}`` gets the detail after a colon.
    """
    template = _REASON_TEXTS.get(reason, reason)
    if detail and "{name}" not in template:
        return f"{template.rstrip('.')}: {detail}."
    return template.format(name=detail or "unknown")


class RuntimeUnavailable(RuntimeError):
    """The runtime cannot serve; nothing was sent to it (before dispatch).

    Attributes:
        reason: A ``rules.REASONS`` value, or ``OPERATOR_STOP``.
        reason_text: The plain-English line (names the file for ``file-changed``).
        runtime_id: The runtime.
    """

    def __init__(self, runtime_id: str, reason: str, text: str | None = None) -> None:
        self.runtime_id = runtime_id
        self.reason = reason
        self.reason_text = text or reason_text(reason)
        super().__init__(f"{runtime_id}: {self.reason_text}")


class RuntimeRequestFailed(RuntimeError):
    """The request was sent and the server went away (after dispatch).

    Attributes:
        reason: ``exited`` (a second crash) or ``OPERATOR_STOP``.
        runtime_id: The runtime.
    """

    def __init__(self, runtime_id: str, reason: str) -> None:
        self.runtime_id = runtime_id
        self.reason = reason
        super().__init__(f"{runtime_id}: {reason_text(reason)}")


def _is_connection_failure(error: BaseException) -> bool:
    """Return whether *error* (or its cause) is a refused or cut connection."""
    try:
        import httpx

        lost: tuple[type[BaseException], ...] = (
            ConnectionError,
            httpx.ConnectError,
            httpx.RemoteProtocolError,
            httpx.ReadError,
        )
    except ImportError:  # pragma: no cover - httpx is a base dependency
        lost = (ConnectionError,)
    current: BaseException | None = error
    for _ in range(6):
        if current is None:
            return False
        if isinstance(current, lost):
            return True
        current = current.__cause__ or current.__context__
    return False


class RuntimeLease:
    """This process's use of one runtime. Get it from :meth:`RuntimeManager.lease`.

    The lease joins on first use. After an operator stop it refuses with
    ``OPERATOR_STOP`` until it leaves; a later join starts the server again.
    """

    def __init__(self, manager: RuntimeManager, spec: RuntimeSpec) -> None:
        self.manager = manager
        self.spec = spec
        self.folder = runtime_dir(manager.root, spec.id)
        self._lock = threading.RLock()
        self._clients: LockFile | None = None
        self._url: str | None = None
        self._generation = 0
        self._operator_stopped = False
        self._in_progress = 0
        self._last_end = time.monotonic()
        self._idle_hooks: list[Callable[[], None]] = []
        self._leave_hooks: list[Callable[[], None]] = []
        #: Called under ``start.lock`` before each start; returns extra record
        #: fields. The router writes ``models.ini`` here (one-llamacpp-router D4).
        self.before_start: Callable[[], dict[str, Any]] | None = None

    # ── Read-only views ─────────────────────────────────────────────────

    @property
    def joined(self) -> bool:
        """Whether this lease holds the runtime now."""
        return self._url is not None

    @property
    def base_url(self) -> str | None:
        """``http://127.0.0.1:<port>`` (or the external URL); ``None`` before a join.

        The port of an OCR runtime changes after a restart on a new port.
        """
        return self._url

    @property
    def generation(self) -> int:
        """The server generation this lease joined (0 for external or not joined)."""
        return self._generation

    @property
    def operator_stopped(self) -> bool:
        """Whether an operator stopped the server this lease joined."""
        return self._operator_stopped

    def on_idle_leave(self, hook: Callable[[], None]) -> None:
        """Run *hook* before an idle leave (the OCR host closes its worker there)."""
        self._idle_hooks.append(hook)

    def on_leave(self, hook: Callable[[], None]) -> None:
        """Run *hook* at every leave of a joined lease (the router drops model locks)."""
        self._leave_hooks.append(hook)

    # ── Join and leave ──────────────────────────────────────────────────

    def join(self) -> str:
        """Join the runtime and return its base URL (design D4).

        Raises:
            RuntimeUnavailable: The runtime cannot serve; nothing was sent.
        """
        with self._lock:
            if self._url is not None:
                return self._url
            if self._operator_stopped:
                raise RuntimeUnavailable(self.spec.id, OPERATOR_STOP)
            if self.spec.mode == "external":
                return self._join_external()
            if not locks.LOCKS_SUPPORTED:
                raise RuntimeUnavailable(self.spec.id, "not-supported")
            for _ in range(_VERSION_TRIES):
                clients = LockFile(self.folder / "clients.lock")
                clients.acquire(shared=True)  # blocks while holding no other lock
                try:
                    record = self._decide(clients)
                except BaseException:
                    clients.close()
                    raise
                if record is None:  # the old version stopped: join again
                    clients.close()
                    continue
                self._clients = clients
                self._adopt(record)
                self.manager._ensure_timer()
                return f"http://127.0.0.1:{record.port}"
            raise RuntimeUnavailable(self.spec.id, "version-busy")

    def _join_external(self) -> str:
        url = self.spec.url_base.rstrip("/")
        if self.spec.role == "ocr" and self.spec.build is not None:
            if process.props_build(url) != self.spec.build:
                raise RuntimeUnavailable(self.spec.id, "wrong-build")
        self._url = url
        return url

    def _adopt(self, record: ServerRecord) -> None:
        self._url = f"http://127.0.0.1:{record.port}"
        self._generation = record.generation
        self._last_end = time.monotonic()

    def _decide(self, clients: LockFile) -> ServerRecord | None:
        """Adopt, replace or start under ``start.lock``; ``None`` means join again."""
        start = LockFile(self.folder / "start.lock")
        start.acquire()
        try:
            record = read_server_record(self.folder)
            if record is None or not process.owns(record.pid, record.binary):
                return self._start(record)  # stale or none: never signal it
            if record.digest == self.spec.digest:
                return self._adopt_running(record)
            # Another version: replace it only when no other client holds it.
            clients.close()
            probe = LockFile(self.folder / "clients.lock")
            try:
                if not probe.acquire(shared=False, blocking=False):
                    raise RuntimeUnavailable(self.spec.id, "version-busy")
                process.stop(record.pid, record.binary)
                record.state, record.stopped_by = "stopped", None
                write_server_record(self.folder, record)
            finally:
                probe.close()
            return None
        finally:
            start.close()

    def _adopt_running(self, record: ServerRecord) -> ServerRecord:
        if record.state == "running":
            return record
        # Its starter died during the start: wait for health as a starter would.
        outcome = process.wait_healthy(record.port, lambda: process.owns(record.pid, record.binary))
        if outcome != "ok":
            process.stop(record.pid, record.binary)
            self._fail(record, "timeout" if outcome == "timeout" else "exited")
        record.state = "running"
        write_server_record(self.folder, record)
        return record

    def _fail(self, previous: ServerRecord | None, reason: str, detail: str = "") -> None:
        text = reason_text(reason, detail)
        write_server_record(
            self.folder,
            ServerRecord(
                pid=0,
                port=0,
                binary=self.spec.binary,
                digest=self.spec.digest,
                build=self.spec.build,
                state="stopped",
                generation=previous.generation if previous else 0,
                reason=reason,
                reason_text=text,
            ),
        )
        raise RuntimeUnavailable(self.spec.id, reason, text)

    def _start(self, previous: ServerRecord | None) -> ServerRecord:
        """Start a new server (caller holds ``start.lock``) and record it."""
        generation = (previous.generation if previous else 0) + 1

        extra: dict[str, Any] = {}

        def launched(pid: int, port: int) -> None:
            record = self._record(pid, port, generation, "starting", extra)
            write_server_record(self.folder, record)

        try:
            extra = self.before_start() if self.before_start is not None else {}
            pid, port = process.start_server(self.spec, self.folder, self.manager.environ, launched)
        except process.StartRefused as refused:
            self._fail(previous, refused.reason, refused.detail)
            raise  # pragma: no cover - _fail always raises
        record = self._record(pid, port, generation, "running", extra)
        write_server_record(self.folder, record)
        return record

    def _record(
        self, pid: int, port: int, generation: int, state: Any, extra: dict[str, Any]
    ) -> ServerRecord:
        return ServerRecord(
            pid=pid,
            port=port,
            binary=self.spec.binary,
            digest=self.spec.digest,
            build=self.spec.build,
            state=state,
            generation=generation,
            **extra,
        )

    def leave(self, stopped_by: str = "last-client") -> None:
        """Leave the runtime; stop the server when no other client holds it.

        Leaving also clears an operator stop, so the next join starts again.
        """
        with self._lock:
            self._operator_stopped = False
            if self._url is None:
                return
            for hook in list(self._leave_hooks):
                hook()
            self._url, self._generation = None, 0
            clients, self._clients = self._clients, None
            if clients is None:  # external
                return
            clients.close()
            self.manager._stop_if_unused(self.folder, stopped_by)

    # ── Requests ────────────────────────────────────────────────────────

    def _uses_request_lock(self) -> bool:
        """Whether requests serialise on ``request.lock`` (``-np 1``, design D6)."""
        return self.spec.one_slot and locks.LOCKS_SUPPORTED

    def _check_operator_stop(self) -> None:
        if self._operator_stopped or self._stopped_by_operator_now():
            raise RuntimeUnavailable(self.spec.id, OPERATOR_STOP)

    def _stopped_by_operator_now(self) -> bool:
        if self.spec.mode == "external":
            return False
        record = read_server_record(self.folder)
        stopped = (
            record is not None
            and record.stopped_by == "operator"
            and record.generation == self._generation
        )
        self._operator_stopped = self._operator_stopped or stopped
        return stopped

    def _begin(self) -> tuple[str, LockFile | None]:
        with self._lock:
            self.join()
            self._check_operator_stop()
            self._in_progress += 1
        ticket: LockFile | None = None
        try:
            if self._uses_request_lock():
                ticket = LockFile(self.folder / "request.lock")
                ticket.acquire()  # no timeout of its own: each holder is bounded
            url = self._url
            if url is None:
                raise RuntimeUnavailable(self.spec.id, "exited")
        except BaseException:
            self._end(ticket)
            raise
        return url, ticket

    def _end(self, ticket: LockFile | None) -> None:
        if ticket is not None:
            ticket.close()
        with self._lock:
            self._in_progress -= 1
            self._last_end = time.monotonic()
        if self.spec.mode == "managed":
            process.cap_log(self.folder / process.LOG_FILE)

    @contextlib.contextmanager
    def session(self) -> Iterator[str]:
        """Hold the runtime for one request and yield its base URL.

        Joins on first use and takes the request lock of a one-slot runtime,
        so the caller's timeout starts only when the lock is held. No crash
        restart runs here; see :meth:`restart_if_crashed`.
        """
        url, ticket = self._begin()
        try:
            yield url
        finally:
            self._end(ticket)

    def request(self, send: Callable[[str], T]) -> T:
        """Run ``send(base_url)`` once, with one crash restart (design D5, D6).

        Raises:
            RuntimeUnavailable: Before dispatch.
            RuntimeRequestFailed: The server went away twice, or an operator
                stopped it during the request.
        """
        url, ticket = self._begin()
        try:
            try:
                return send(url)
            except Exception as error:
                if not _is_connection_failure(error) or not self.restart_if_crashed():
                    raise
            try:
                return send(self._url or url)
            except Exception as error:
                raise self._second_failure(error) from error
        finally:
            self._end(ticket)

    async def arequest(self, send: Callable[[str], Awaitable[T]]) -> T:
        """The async form of :meth:`request`; lock work runs in a thread."""
        url, ticket = await asyncio.to_thread(self._begin)
        try:
            try:
                return await send(url)
            except Exception as error:
                if not _is_connection_failure(error):
                    raise
                if not await asyncio.to_thread(self.restart_if_crashed):
                    raise
            try:
                return await send(self._url or url)
            except Exception as error:
                raise self._second_failure(error) from error
        finally:
            await asyncio.to_thread(self._end, ticket)

    def _second_failure(self, error: Exception) -> Exception:
        if not _is_connection_failure(error):
            return error
        if self._stopped_by_operator_now():
            return RuntimeRequestFailed(self.spec.id, OPERATOR_STOP)
        return RuntimeRequestFailed(self.spec.id, "exited")

    def restart_if_crashed(self) -> bool:
        """After a lost connection, restart a crashed server once (design D5).

        Returns:
            ``True`` when a server runs again at :attr:`base_url` (this call
            or another process started it), ``False`` when the joined server
            still runs (the failure was not a crash) or the runtime is external.

        Raises:
            RuntimeRequestFailed: An operator stopped the server (no restart).
            RuntimeUnavailable: The restart failed its checks or its start.
        """
        if self.spec.mode == "external":
            return False
        with self._lock:
            if self._url is None:
                return False
            start = LockFile(self.folder / "start.lock")
            start.acquire()
            try:
                record = read_server_record(self.folder)
                if self._stopped_by_operator_now():
                    raise RuntimeRequestFailed(self.spec.id, OPERATOR_STOP)
                if record is not None and process.owns(record.pid, record.binary):
                    if record.generation == self._generation:
                        return False
                    self._adopt(record)
                    return True
                self._adopt(self._start(record))
                return True
            finally:
                start.close()

    # ── Idle stop ───────────────────────────────────────────────────────

    def _idle_due(self, now: float, idle_seconds: float) -> bool:
        with self._lock:
            return (
                self._url is not None
                and self.spec.mode == "managed"
                and self._in_progress == 0
                and now - self._last_end >= idle_seconds
            )

    def _idle_leave(self, idle_seconds: float) -> None:
        for hook in list(self._idle_hooks):
            try:
                hook()
            except Exception:  # noqa: BLE001 - a hook never blocks the leave
                logger.warning("idle hook of runtime %s failed", self.spec.id, exc_info=True)
        with self._lock:
            if self._idle_due(time.monotonic(), idle_seconds):
                self.leave(stopped_by="idle")
