"""Owner-scoped lifecycle wrapper for the OCR worker subprocess (task 2.6a).

The wave-1 :class:`OcrWorkerClient` owns the subprocess mechanics —
lazy start, single-flight dispatch, discard-on-failure. This wrapper
adds the OWNER side of design D2.2: a resolved capability fingerprint
that gates dispatch, a spawn-generation counter that makes reuse and
restart observable, and a close state that stops new requests when the
owning engine (or ingest operation) shuts down.

``core/`` receives this collaborator by injection and never imports
subprocess code itself; the composition boundary constructs it via
``omrs.capabilities.build_ocr_routes``.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Sequence
from typing import Any

from ..llamacpp_runtime.lease import RuntimeLease, RuntimeRequestFailed, RuntimeUnavailable
from .client import OcrWorkerClient, OcrWorkerError
from .fingerprint import OcrWorkerFingerprint
from .protocol import ParseSuccess
from .runtime import RUNTIME_URL_ENV

logger = logging.getLogger(__name__)

#: Failure codes that make the subprocess unusable; a structured
#: worker-reported error is deliberately absent — that exchange leaves
#: a healthy process that later requests reuse (design D2.2).
_FATAL_OCR_WORKER_CODES = frozenset(
    {
        "timeout",
        "worker_crashed",
        "worker_closed_output",
        "worker_closed_input",
        "protocol_violation",
        "spawn_failed",
    }
)


#: The request never reached a worker: the runtime or the fingerprint is unavailable.
UNAVAILABLE_CODE = "worker_unavailable"
#: An operator stopped the runtime while the request ran (design D8).
RUNTIME_STOPPED_CODE = "runtime_stopped"


class ManagedOcrClient:
    """Owner-scoped OCR worker client: lazy, long-lived, invalidated on failure.

    Construction is cheap and starts nothing. The first :meth:`parse`
    starts one subprocess; healthy subprocesses are reused; a fatal
    failure discards the handle so the NEXT request lazily starts a
    fresh process (the failed request is never replayed — dispatch is
    caller-driven).
    """

    def __init__(
        self,
        *,
        fingerprint: OcrWorkerFingerprint,
        command: list[str],
        request_timeout: float = 300.0,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        on_stderr_line: Any = None,
        dispatch_lock: Any = None,
        lease: RuntimeLease | None = None,
    ) -> None:
        """Hold the resolved fingerprint and worker command; start nothing.

        Args:
            fingerprint: Resolved capability fingerprint (the probe
                result). An unavailable fingerprint makes every
                :meth:`parse` fail before dispatch.
            command: Worker launch command, argv-style.
            request_timeout: Seconds to wait for each terminal response.
            cwd: Working directory for the subprocess, if any.
            env: Extra environment mappings merged over the current
                environment, if any.
            on_stderr_line: Optional callback for drained worker
                diagnostics, forwarded through OMRS logging.
            dispatch_lock: Optional lock held around each dispatch. The
                OCR client pool shares one lock between its clients, so at
                most one worker parses at a time (design D5).
            lease: The lease of the llama.cpp runtime the engine declares.
                Before a parse the client joins the runtime, takes its request
                lock and starts the worker with ``OMRS_OCR_RUNTIME_URL``.
                ``None`` for an engine that declares no runtime.
        """
        self.fingerprint = fingerprint
        self._command = list(command)
        self._request_timeout = request_timeout
        self._cwd = cwd
        self._env = env
        self._on_stderr_line = on_stderr_line
        self._client: OcrWorkerClient | None = None
        self._lock = threading.Lock()
        self._closed = False
        self._process_generations = 0
        self._dispatch_lock = dispatch_lock or contextlib.nullcontext()
        self._lease = lease
        self._worker_url: str | None = None
        if lease is not None:
            lease.on_idle_leave(self._close_worker)

    # ── Observability ───────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        """Whether the resolved fingerprint reports a compatible worker."""
        return self.fingerprint.available

    @property
    def lease(self) -> RuntimeLease | None:
        """The lease of the runtime the engine declares, or ``None``."""
        return self._lease

    @property
    def is_started(self) -> bool:
        """Whether a worker subprocess is currently held."""
        client = self._client
        return client is not None and client.is_started

    @property
    def process_generations(self) -> int:
        """How many distinct subprocesses have been constructed.

        Reuse keeps this at 1; each fatal failure followed by a new
        request increments it. Test observability for the lazy/reuse/
        restart contract — deliberately absent from the fingerprint,
        which carries no transient process detail.
        """
        return self._process_generations

    # ── Dispatch ────────────────────────────────────────────────────

    def parse(
        self,
        pdf_path: str,
        *,
        pages: Sequence[int] | None = None,
        timeout: float | None = None,
    ) -> ParseSuccess:
        """Dispatch one parse request to the worker, optionally page-listed.

        Args:
            pdf_path: Path of the PDF the worker must parse.
            pages: 1-based page numbers to parse (protocol 1.1, change
                page-level-ocr-routing task 4.3). ``None`` parses the
                whole document and speaks protocol 1.0.
            timeout: Seconds to wait for this request's terminal
                response; the client's request timeout when ``None``.
                The routing seam scales it by page count (design D3).

        Returns:
            The terminal success envelope with structured Markdown;
            ``pages_markdown`` is parallel to *pages* when it was given.

        Raises:
            RuntimeError: When the owner has closed this client.
            OcrWorkerError: ``worker_unavailable`` before dispatch when
                the fingerprint is unavailable (no process is started);
                otherwise the structured failure from the subprocess
                exchange (timeout, crash, protocol violation, or a
                worker-reported error code).
        """
        if self._closed:
            raise RuntimeError("ManagedOcrClient is closed; construct a new client.")
        if not self.fingerprint.available:
            raise OcrWorkerError(
                UNAVAILABLE_CODE,
                "the OCR worker fingerprint is unavailable; dispatch refused",
            )
        with self._dispatch_lock:
            if self._lease is not None:
                return self._parse_in_runtime(self._lease, pdf_path, pages, timeout)
            return self._send(self._ensure_client(), pdf_path, pages, timeout)

    # ── Owner lifecycle ─────────────────────────────────────────────

    def close(self) -> None:
        """Stop accepting requests and close the subprocess, bounded.

        Mirrors the engine's resource release: stdin closes first so a
        well-behaved worker exits on its own, then a bounded graceful
        wait, then termination (delegated to the underlying client's
        close). Idempotent.
        """
        with self._lock:
            self._closed = True
            client = self._client
            self._client = None
        if client is not None:
            client.close()
            logger.debug("closed managed OCR worker client")
        if self._lease is not None:  # the worker first, then the runtime (design D9)
            self._lease.leave()

    def __enter__(self) -> ManagedOcrClient:
        """Return self for ``with``-scoped ownership."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Close the subprocess on scope exit."""
        self.close()

    # ── Internals ───────────────────────────────────────────────────

    def _send(
        self,
        client: OcrWorkerClient,
        pdf_path: str,
        pages: Sequence[int] | None,
        timeout: float | None,
    ) -> ParseSuccess:
        """Send one request; a fatal failure discards the worker."""
        try:
            return client.parse(pdf_path, pages=pages, timeout=timeout)
        except OcrWorkerError as exc:
            if exc.code in _FATAL_OCR_WORKER_CODES:
                self._drop_client(client)
            raise

    def _parse_in_runtime(
        self,
        lease: RuntimeLease,
        pdf_path: str,
        pages: Sequence[int] | None,
        timeout: float | None,
    ) -> ParseSuccess:
        """Parse while holding the runtime (design D10).

        ``session`` joins the runtime and takes its request lock, so the
        request timeout starts when the lock is held. A runtime that cannot
        serve is refused before dispatch (``worker_unavailable``). After a
        failure the lease checks for a crash or an operator stop.
        """
        try:
            with lease.session() as base_url:
                client = self._ensure_client(base_url)
                try:
                    return self._send(client, pdf_path, pages, timeout)
                except OcrWorkerError as failure:
                    outcome = failure
        except RuntimeUnavailable as unavailable:
            raise OcrWorkerError(UNAVAILABLE_CODE, unavailable.reason_text) from unavailable
        self._check_runtime_after(lease, outcome)
        raise outcome

    def _check_runtime_after(self, lease: RuntimeLease, failure: OcrWorkerError) -> None:
        """After a failure, restart a crashed server or report an operator stop.

        A crashed server restarts once, for the next request. The failed
        request is not sent again. An operator stop raises ``runtime_stopped``
        so the dispatcher can send the request to the fallback route once.
        """
        try:
            lease.restart_if_crashed()
        except RuntimeRequestFailed as stopped:
            self._discard_worker()  # the dispatch lock is held here
            raise OcrWorkerError(
                RUNTIME_STOPPED_CODE, "an operator stopped the runtime during the request"
            ) from stopped
        except RuntimeUnavailable:
            logger.warning("OCR runtime did not restart after: %s", failure)

    def _close_worker(self) -> None:
        """Close the worker, not the client, before an idle leave.

        It waits for a parse in progress, because a parse holds the dispatch lock.
        """
        with self._dispatch_lock:
            self._discard_worker()

    def _discard_worker(self) -> None:
        """Close the worker, not the client. The caller holds the dispatch lock."""
        with self._lock:
            client, self._client = self._client, None
        if client is not None:
            client.close()

    def _worker_env(self, base_url: str | None) -> dict[str, str] | None:
        """Return the worker's extra environment; add the runtime URL for a runtime."""
        if base_url is None:
            return self._env
        return {**(self._env or {}), RUNTIME_URL_ENV: base_url}

    def _ensure_client(self, base_url: str | None = None) -> OcrWorkerClient:
        """Return the shared underlying client, constructing it lazily.

        A worker started for another runtime URL (the server restarted on a
        new port) is closed and replaced.
        """
        stale: OcrWorkerClient | None = None
        with self._lock:
            if self._closed:
                raise RuntimeError("ManagedOcrClient is closed; construct a new client.")
            if self._client is not None and self._worker_url != base_url:
                stale, self._client = self._client, None
            if self._client is None:
                self._client = OcrWorkerClient(
                    self._command,
                    cwd=self._cwd,
                    env=self._worker_env(base_url),
                    request_timeout=self._request_timeout,
                    on_stderr_line=self._on_stderr_line,
                )
                self._worker_url = base_url
                self._process_generations += 1
            client = self._client
        if stale is not None:
            stale.close()
        return client

    def _drop_client(self, client: OcrWorkerClient) -> None:
        """Discard a fatally failed client; the next parse builds a fresh one."""
        with self._lock:
            if self._client is client:
                self._client = None
        client.close()
