"""Automatic download of a listed router model with no file (one-llamacpp-router, task 6.2a).

:class:`RouterDownloads` is the router lease's
:class:`~omrs.integrations.llamacpp_runtime.router_lease.Downloader` in ``omrs web``.
The router lease asks it for a model from any thread; it queues the model on the
app's event loop and downloads one model at a time:

1. find the list entry that names the model and has no file;
2. read the repo's current revision and plan the download as the Get a model route
   does (``model_downloads``: quantisation, gated and free-space checks), so the
   download runs at that pinned revision;
3. run it on the one :class:`~.model_download_job.ModelDownloadJob` (progress, cancel);
   a download the user started first is waited for;
4. record the file path and SHA-256 through the Use this model writer, apply the
   reload rule, and load the model.

A failed or cancelled download leaves the entry ``not-downloaded``, and a Start that waits
for the downloads ends (``RouterControl.load``). The model is then on a failed list: a
request for it queues nothing (``RouterLease.model_session`` asks on every request). Only the
user's next Start (:meth:`RouterDownloads.clear_failed`) or a Get a model download of that
model asks again. Nothing here raises into the router lease.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from ...config.settings_file_write import SettingsFileError
from ...integrations import huggingface_models as hf_models
from .llamacpp_chat_rule import model_list
from .model_download_job import RUNNING, SUCCEEDED, DownloadBusy

logger = logging.getLogger(__name__)

#: The provider whose model source is the router's (``huggingface-gguf``).
PROVIDER = "llamacpp"


def missing_entry(store: Any, model: str) -> str | None:
    """Return the id of the list entry that names *model* and has no file, else ``None``."""
    for entry_id, entry in model_list(store.read()).items():
        if entry.model == model and not (entry.file or "").strip():
            return entry_id
    return None


class RouterDownloads:
    """Queue and run automatic downloads of router models on the app's event loop.

    Args:
        app: The FastAPI app (its ``state.runtime``, ``state.mcp_http`` and
            ``state.llamacpp_router`` are read when a download runs).
        loop: The app's event loop.
    """

    def __init__(self, app: Any, loop: asyncio.AbstractEventLoop) -> None:
        self.app = app
        self.loop = loop
        self._lock = threading.Lock()
        self._active: set[str] = set()
        self._failed: set[str] = set()  # automatic download failed or was cancelled
        self._queue: list[str] = []
        self._worker: asyncio.Task[None] | None = None

    def request(self, model: str) -> None:
        """Queue *model* unless it is queued, runs or failed. Safe from any thread; never blocks.

        A model on the failed list is skipped until the user asks again: their Start
        (:meth:`clear_failed`) or a Get a model download of that model that runs.
        """
        with self._lock:
            if model in self._active:
                return
            if model in self._failed:
                if not self._manual_download_runs(model):
                    return
                self._failed.discard(model)
            self._active.add(model)
        try:
            self.loop.call_soon_threadsafe(self._enqueue, model)
        except RuntimeError:  # the loop closed: the app is gone
            with self._lock:
                self._active.discard(model)

    def clear_failed(self) -> None:
        """Forget every failed or cancelled download: the user pressed Start."""
        with self._lock:
            self._failed.clear()

    def _manual_download_runs(self, model: str) -> bool:
        """Return whether the Get a model job runs a download of *model* (the user's own)."""
        runtime = getattr(self.app.state, "runtime", None)
        if runtime is None:
            return False
        shown = runtime.model_downloads.snapshot()
        return bool(shown["state"] == RUNNING and shown["model"] == model)

    def downloading(self, model: str) -> bool:
        """Return whether *model* is queued or runs."""
        with self._lock:
            return model in self._active

    async def close(self) -> None:
        """Stop the queue at shutdown. A running transfer stops with the download job."""
        worker, self._worker = self._worker, None
        if worker is not None and not worker.done():
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    def _enqueue(self, model: str) -> None:
        self._queue.append(model)
        if self._worker is None or self._worker.done():
            self._worker = self.loop.create_task(self._drain())

    async def _drain(self) -> None:
        while self._queue:
            model = self._queue.pop(0)
            try:
                await self._one(model)
            except Exception:  # noqa: BLE001 - one failed download must not stop the queue
                logger.exception("The automatic download of %s failed.", model)
                with self._lock:
                    self._failed.add(model)
            finally:
                with self._lock:
                    self._active.discard(model)

    async def _one(self, model: str) -> None:
        state = self.app.state
        runtime, store = state.runtime, state.mcp_http.store
        entry_id = await run_in_threadpool(missing_entry, store, model)
        if runtime is None or entry_id is None:
            return  # the entry has a file now, or left the list
        job = runtime.model_downloads
        await job.wait()  # a download that runs (the user's own) ends first
        planned = await self._plan(runtime, model)
        if planned is None:
            await self._ended_without_file(runtime, store, model)
            return
        while True:
            await job.wait()
            try:
                job.start(planned)
                break
            except DownloadBusy:
                continue
        await job.wait()
        done = job.snapshot()
        if done["state"] != SUCCEEDED or done["model"] != model:
            logger.info("The automatic download of %s ended: %s", model, done["state"])
            await self._ended_without_file(runtime, store, model)
            return
        await self._record(runtime, store, entry_id, model, done["file_path"], done["sha256"])

    async def _ended_without_file(self, runtime: Any, store: Any, model: str) -> None:
        """Tell the router that *model* will get no file, so a waiting Start can end.

        The Start waits while any download is queued or runs. When this was the last one,
        the router starts with the models that did arrive, or the wait ends in a failure.
        """
        from .routes.llamacpp_router_view import load_router

        with self._lock:
            self._active.discard(model)  # it no longer downloads
            self._failed.add(model)  # and a request does not queue it again
        loaded = await run_in_threadpool(load_router, runtime, store)
        await run_in_threadpool(self.app.state.llamacpp_router.load, loaded.config, model)

    async def _plan(self, runtime: Any, model: str) -> Any:
        """Return the checked download request of *model* at its pinned revision, or ``None``."""
        from .provider_state import descriptor_of
        from .routes.model_downloads import StartBody, _plan_gguf

        repo, _, label = model.rpartition(":")
        try:
            listed = await run_in_threadpool(hf_models.list_repo_files, repo)
        except hf_models.ModelHostError as exc:
            logger.info("The automatic download of %s cannot start: %s", model, exc.reason)
            return None
        body = StartBody(provider=PROVIDER, repo=repo, revision=listed.revision, label=label)
        descriptor = descriptor_of(PROVIDER)
        planned = await _plan_gguf(body, runtime, descriptor)  # type: ignore[arg-type]
        if isinstance(planned, Response):
            logger.info(
                "The automatic download of %s was refused (%s).", model, planned.status_code
            )
            return None
        return planned

    async def _record(
        self, runtime: Any, store: Any, entry_id: str, model: str, path: str, sha256: str
    ) -> None:
        """Write the file and its SHA-256 into the entry, apply the reload rule, load it."""
        from .routes.llamacpp_router_entry import EntryRefused
        from .routes.llamacpp_router_models import apply_saved, save_entry

        control = self.app.state.llamacpp_router
        sent = {"file": path, "sha256": sha256}
        async with runtime.providers.lock:
            try:
                await run_in_threadpool(save_entry, runtime, store, entry_id, sent, None)
            except (EntryRefused, SettingsFileError) as refused:
                logger.info("The downloaded file of %s was not recorded: %s", model, refused)
                with self._lock:
                    self._failed.add(model)
                return
            loaded = await run_in_threadpool(apply_saved, runtime, store, control)
        await run_in_threadpool(control.load, loaded.config, model)
