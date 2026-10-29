"""The single model download job on this server (ADR-106, design D7).

One :class:`ModelDownloadJob` lives on ``WebRuntime``, next to ``InstallJob``
and separate from it: it starts no subprocess, and it counts bytes, not lines.
Installs and downloads may run at the same time.

The job runs one blocking adapter in a worker thread (``asyncio.to_thread``).
The adapter table :data:`ADAPTERS` is keyed by ``ModelSourceKind`` and holds
one entry for each source, so no code branches on a provider name.

* **One at a time.** :meth:`ModelDownloadJob.start` raises :class:`DownloadBusy`
  while a job runs.
* **Progress.** The adapter reports bytes through :class:`Progress`. A status
  read takes a snapshot under a lock.
* **Cancel.** :meth:`ModelDownloadJob.cancel` sets a ``threading.Event`` that the
  adapter checks. The job ends ``cancelled`` after the adapter stops, or after
  ``cancel_grace`` seconds when it does not (an Ollama stream that is quiet).
* **Stall.** A watchdog checks the time of the last progress report every
  ``watch_interval`` seconds. After ``stall_seconds`` without one, the job
  cancels the adapter and ends ``failed`` with the reason ``stalled``.
* **Errors.** An adapter error maps to a fixed reason. The exception text and
  the token reach neither the status nor a log line above debug level.

The state is kept in memory, so a restart shows ``idle``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ...core.providers.model_sources import ModelSourceKind
from ...integrations import huggingface_models, ollama_pull
from .security import redact

logger = logging.getLogger(__name__)

#: Seconds without a progress report before the job fails as ``stalled``.
STALL_SECONDS = 60.0
#: Seconds between two stall checks.
WATCH_INTERVAL_SECONDS = 5.0
#: Seconds the job waits for the adapter to stop after a cancel.
CANCEL_GRACE_SECONDS = 3.0

IDLE = "idle"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELLED = "cancelled"

#: Reasons that an adapter error can map to (the rest of the fixed set is
#: raised by the route: ``busy``, ``no-space``, or by the watchdog: ``stalled``).
_ADAPTER_REASONS = frozenset({"not-found", "gated", "network", "ollama-unreachable", "failed"})
_CANCEL_ERRORS = (huggingface_models.DownloadCancelled, ollama_pull.PullCancelled)


class DownloadBusy(RuntimeError):
    """Raised when a download starts while another one runs."""


@dataclass(frozen=True)
class DownloadRequest:
    """What one download needs. The route has already checked every value.

    Attributes:
        kind: The model source; it selects the adapter.
        provider: The provider name, for the status.
        display: The model as the status shows it.
        model_value: The value to save as the model after success.
        bytes_total: Bytes still to download, or ``None`` when unknown.
        cache_folder: The folder that receives the files, with ``~`` for home.
        repo: Hugging Face repo id (``huggingface-gguf``).
        revision: Pinned commit hash (``huggingface-gguf``).
        files: Repo paths of the chosen quantisation (``huggingface-gguf``).
        token: ``HF_TOKEN`` from the server environment, or ``None``.
        name: Ollama model name (``ollama-pull``).
        base_url: Ollama address (``ollama-pull``).
    """

    kind: ModelSourceKind
    provider: str
    display: str
    model_value: str
    bytes_total: int | None = None
    cache_folder: str | None = None
    repo: str = ""
    revision: str = ""
    files: tuple[str, ...] = ()
    token: str | None = field(default=None, repr=False)
    name: str = ""
    base_url: str = ""


class Progress:
    """State of one job, shared by the event loop and the worker thread.

    The adapter calls :meth:`add` or :meth:`update`. Every access holds a lock.
    """

    def __init__(self, request: DownloadRequest, clock: Callable[[], float]) -> None:
        self.request = request
        self.cancel = threading.Event()
        self.cancel_signal = asyncio.Event()
        self.user_cancelled = False
        self.stalled = False
        self.task: asyncio.Task[None] | None = None
        self._clock = clock
        self._lock = threading.Lock()
        self._state = RUNNING
        self._reason: str | None = None
        self._done = 0
        self._total = request.bytes_total
        self._last = clock()

    def add(self, count: int) -> None:
        """Add *count* downloaded bytes."""
        with self._lock:
            self._done += max(count, 0)
            self._last = self._clock()

    def update(self, done: int, total: int | None) -> None:
        """Set the bytes done and, when known, the bytes in total (Ollama)."""
        with self._lock:
            self._done = max(done, 0)
            if total is not None:
                self._total = total
            self._last = self._clock()

    def seconds_quiet(self) -> float:
        """Return the seconds since the last progress report."""
        with self._lock:
            return self._clock() - self._last

    @property
    def running(self) -> bool:
        """Whether the job has not ended."""
        with self._lock:
            return self._state == RUNNING

    def finish(self, state: str, reason: str | None) -> None:
        """End the job with *state* and, for ``failed``, a fixed *reason*."""
        with self._lock:
            self._state, self._reason = state, reason if state == FAILED else None

    def snapshot(self) -> dict[str, Any]:
        """Return the status fields (without the ``status`` envelope key)."""
        with self._lock:
            request = self.request
            return {
                "state": self._state,
                "provider": request.provider,
                "model": request.display,
                "model_value": request.model_value if self._state == SUCCEEDED else None,
                "bytes_done": self._done,
                "bytes_total": self._total,
                "reason": self._reason,
                "cache_folder": request.cache_folder,
            }


#: One blocking transfer: request, progress sink, cancel event.
Adapter = Callable[[DownloadRequest, Progress, threading.Event], None]


def _hugging_face(request: DownloadRequest, progress: Progress, cancel: threading.Event) -> None:
    huggingface_models.download_files(
        request.repo,
        request.revision,
        request.files,
        on_bytes=progress.add,
        cancel=cancel,
        token=request.token or None,
    )


def _ollama(request: DownloadRequest, progress: Progress, cancel: threading.Event) -> None:
    ollama_pull.pull_model(
        request.base_url, request.name, on_progress=progress.update, cancel=cancel
    )


#: The adapter of each model source. A third source adds one entry here.
ADAPTERS: Mapping[ModelSourceKind, Adapter] = {
    "huggingface-gguf": _hugging_face,
    "ollama-pull": _ollama,
}

_Ended = tuple[str, str | None]


def _reason_of(error: BaseException) -> str:
    """Return the fixed reason for an adapter error. The error text is dropped."""
    reason = getattr(error, "reason", None)
    known = isinstance(error, (huggingface_models.ModelHostError, ollama_pull.OllamaPullError))
    return reason if known and reason in _ADAPTER_REASONS else "failed"


@dataclass
class ModelDownloadJob:
    """State and runner of the one model download this server may run.

    Attributes:
        adapters: The adapter of each source kind (tests replace it).
        clock: Seconds, monotonic (tests replace it).
        stall_seconds: Seconds without progress before ``stalled``.
        watch_interval: Seconds between two stall checks.
        cancel_grace: Seconds to wait for the adapter after a cancel.
    """

    adapters: Mapping[ModelSourceKind, Adapter] = field(default_factory=lambda: ADAPTERS)
    clock: Callable[[], float] = time.monotonic
    stall_seconds: float = STALL_SECONDS
    watch_interval: float = WATCH_INTERVAL_SECONDS
    cancel_grace: float = CANCEL_GRACE_SECONDS
    _current: Progress | None = None

    @property
    def running(self) -> bool:
        """Whether a download runs now."""
        return self._current is not None and self._current.running

    def snapshot(self) -> dict[str, Any]:
        """Return the state in the ``ModelDownloadStatus`` shape, without ``status``."""
        if self._current is None:
            return {
                "state": IDLE,
                "provider": None,
                "model": None,
                "model_value": None,
                "bytes_done": 0,
                "bytes_total": None,
                "reason": None,
                "cache_folder": None,
            }
        return self._current.snapshot()

    def start(self, request: DownloadRequest) -> None:
        """Start the download of *request*. Call it on the event loop.

        Args:
            request: A request that the route has checked.

        Raises:
            DownloadBusy: Another download runs.
        """
        if self.running:
            raise DownloadBusy
        run = Progress(request, self.clock)
        self._current = run
        run.task = asyncio.get_running_loop().create_task(self._run(run))
        self._log(run, f"Model download of {request.display} started.")

    def fail(self, request: DownloadRequest, reason: str) -> None:
        """Record a job that failed before its transfer began, and run no adapter.

        Args:
            request: The request that the route checked.
            reason: A fixed reason, for example ``network``.

        Raises:
            DownloadBusy: Another download runs.
        """
        if self.running:
            raise DownloadBusy
        run = Progress(request, self.clock)
        run.finish(FAILED, reason)
        self._current = run
        self._log(run, f"Model download of {request.display} failed before it began: {reason}")

    def cancel(self) -> bool:
        """Ask the running download to stop. Call it on the event loop.

        Returns:
            ``True`` when a download ran and now stops, ``False`` when none ran.
        """
        run = self._current
        if run is None or not run.running:
            return False
        run.user_cancelled = True
        run.cancel.set()
        run.cancel_signal.set()
        return True

    async def wait(self, timeout: float | None = None) -> None:
        """Wait until the current job ends, or *timeout* seconds pass. Never raises."""
        run = self._current
        if run is not None and run.task is not None:
            await asyncio.wait({run.task}, timeout=timeout)

    async def stop(self, timeout: float = 5.0) -> None:
        """Cancel the running download and wait up to *timeout* seconds (shutdown)."""
        if self.cancel():
            await self.wait(timeout)

    # ── Runner ───────────────────────────────────────────────────────────

    async def _run(self, run: Progress) -> None:
        worker: asyncio.Future[None] = asyncio.ensure_future(asyncio.to_thread(self._call, run))
        # A worker that outlives its job must not leave an unread exception.
        worker.add_done_callback(lambda done: done.cancelled() or done.exception())
        watch = asyncio.ensure_future(self._watch(run))
        signal = asyncio.ensure_future(run.cancel_signal.wait())
        try:
            await asyncio.wait({worker, watch, signal}, return_when=asyncio.FIRST_COMPLETED)
            if not worker.done():
                run.stalled = watch.done() and not run.user_cancelled
                run.cancel.set()
                await asyncio.wait({worker}, timeout=self.cancel_grace)
            state, reason = self._outcome(run, worker)
        except asyncio.CancelledError:
            # The server is shutting down: stop the adapter and keep the result.
            run.cancel.set()
            run.finish(CANCELLED, None)
            raise
        finally:
            watch.cancel()
            signal.cancel()
        run.finish(state, reason)
        self._log(run, f"Model download of {run.request.display} ended: {state} {reason or ''}")

    def _call(self, run: Progress) -> None:
        """Run the adapter of the request's source. This runs in a worker thread."""
        self.adapters[run.request.kind](run.request, run, run.cancel)

    async def _watch(self, run: Progress) -> None:
        """Return when the job has had no progress report for ``stall_seconds``."""
        while True:
            await asyncio.sleep(self.watch_interval)
            if run.seconds_quiet() >= self.stall_seconds:
                return

    def _outcome(self, run: Progress, worker: asyncio.Future[None]) -> _Ended:
        """Map the end of the worker to a state and a fixed reason."""
        error = worker.exception() if worker.done() and not worker.cancelled() else None
        if worker.done() and not worker.cancelled() and error is None:
            return SUCCEEDED, None
        if run.stalled:
            return FAILED, "stalled"
        if run.user_cancelled or error is None or isinstance(error, _CANCEL_ERRORS):
            return CANCELLED, None
        logger.debug("Model download error type: %s", type(error).__name__)
        return FAILED, _reason_of(error)

    def _log(self, run: Progress, text: str) -> None:
        secrets = [run.request.token] if run.request.token else []
        logger.info("%s", redact(text, secrets))
