"""The Router panel's view of the shared ``router`` runtime (one-llamacpp-router, D1, D7, D9).

:class:`RouterControl` is a thin adapter over the process's
:class:`~omrs.integrations.llamacpp_runtime.RuntimeManager`. Start joins the
``router`` runtime as a client (it starts or adopts the router), Stop is an
operator stop, and the status reads the runtime state files. The methods
block, so the routes call them through ``run_in_threadpool``.

The router is detached and may belong to another OMRS process. Its output goes
to ``server.log`` in the runtime folder, which no route reads. A status read
opens no lease and sends no request to a model: it only reads the state files,
the preset file and the router's own ``GET /v1/models``. The CLI and the stdio
MCP server do not import this module.

The module keeps its old name so the lifespan hook has one place; it holds the
router adapter only.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi.concurrency import run_in_threadpool

from ...config.llamacpp_models import LlamaCppModelEntry
from ...integrations.llamacpp_runtime import (
    ROUTER_ID,
    ModelUnavailable,
    RuntimeManager,
    RuntimeSpec,
    RuntimeUnavailable,
    open_router,
    provision,
    read_server_record,
    router_spec,
    rules,
)
from ...integrations.llamacpp_runtime import process as runtime_process
from ...integrations.llamacpp_runtime import readiness as runtime_readiness
from ...integrations.llamacpp_runtime.hashes import HashCache
from ...integrations.llamacpp_runtime.lease import reason_text
from ...integrations.llamacpp_runtime.preset_writer import plan_preset, read_preset, split_sections
from ...integrations.llamacpp_runtime.router_lease import (
    DOWNLOADING_NOTE,
    download_running,
    install_downloader,
)
from ...integrations.llamacpp_runtime.router_spec import HASHES_FILE, router_dir

logger = logging.getLogger(__name__)

State = Literal["stopped", "starting", "running", "failed"]
#: Seconds a health probe of an external router waits.
_PROBE_SECONDS = 1.0
#: ``GET /health`` answers of a router that is still loading.
_HEALTH_LOADING = 503
_LIVE_STATES = ("loaded", "loading", "unloaded")


@dataclass(frozen=True)
class RouterConfig:
    """The saved values one start or status read uses.

    Attributes:
        mode: ``managed`` or ``external``.
        binary: The saved program path; blank means the provisioned build.
        url: The router address; its port is the port of a managed router.
        models_max: ``llamacpp_router_models_max``.
        memory_margin_mib: ``llamacpp_router_memory_margin_mib``.
        entries: The model list by entry id, in order.
        decision_models: Model names that a managed ``llamacpp`` decision entry names.
    """

    mode: str
    binary: str
    url: str
    models_max: int
    memory_margin_mib: int
    entries: Mapping[str, LlamaCppModelEntry]
    decision_models: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelState:
    """The state of one listed model: a fixed state, a fixed reason and a reload flag."""

    state: str
    reason: str | None = None
    reason_text: str | None = None
    note: str | None = None
    reload_pending: bool = False


@dataclass(frozen=True)
class RouterStatus:
    """The state of the router.

    Attributes:
        state: ``stopped``, ``starting``, ``running`` or ``failed``.
        reason: One of ``rules.REASONS`` when the state is ``failed``.
        reason_text: The plain-English line of *reason*.
        running_with: The arguments the live process started with, else ``None``.
        pending_restart: The saved router arguments differ from the live ones.
        program: ``{"path", "source"}``: the program in force.
        models: The state of each listed model, by model name.
    """

    state: State
    reason: str | None = None
    reason_text: str | None = None
    running_with: dict[str, int] | None = None
    pending_restart: bool = False
    program: dict[str, str] = field(default_factory=dict)
    models: Mapping[str, ModelState] = field(default_factory=dict)


def program_in_force(saved: str) -> dict[str, str]:
    """Return the program a start uses: a user path, the provisioned build, or none."""
    resolved = provision.resolve_server_binary(saved)
    if saved.strip():
        return {"path": resolved, "source": "user"}
    return {"path": resolved, "source": "provisioned" if resolved else "none"}


def _still_downloading(models: Mapping[str, ModelState]) -> bool:
    """Return whether a listed model with no file has an automatic download queued or running."""
    return any(
        m.state == rules.NOT_DOWNLOADED and download_running(name) for name, m in models.items()
    )


def _argument(argv: list[str], flag: str) -> int | None:
    """Return the integer after *flag* in a recorded argument list, or ``None``."""
    try:
        return int(argv[argv.index(flag) + 1])
    except (ValueError, IndexError):
        return None


class RouterControl:
    """Start, stop and status of the router over the shared runtime manager.

    Args:
        manager: The runtime manager of this process.
    """

    def __init__(self, manager: RuntimeManager) -> None:
        self.manager = manager
        self._router: Any = None
        self._refusal: tuple[str, str] | None = None
        # A Start waits for the automatic downloads: nothing runs yet, the router is
        # ``starting``. The last download ends the wait (see ``load``). The wait lives in
        # this process only, so a server restart shows no failure from before.
        self._waiting = False
        self._to_load: set[str] = set()  # downloaded while the Start waited

    def _end_wait(self, refusal: tuple[str, str] | None = None) -> None:
        """Forget a waiting Start; *refusal* is what the status shows next, if any."""
        self._waiting = False
        self._to_load.clear()
        self._refusal = refusal

    # ── Checks ───────────────────────────────────────────────────────────

    def check(self, config: RouterConfig) -> RuntimeSpec | tuple[str, str]:
        """Return the managed router spec, or ``(reason, line)`` of the rule that refuses it."""
        binary = provision.resolve_server_binary(config.binary)
        refusal = None
        if not binary.strip():
            refusal = rules.NOT_PROVISIONED
        elif not rules.check_binary(binary):
            refusal = "binary-invalid"
        port = rules.loopback_port(config.url)
        if refusal is None and port is None:
            refusal = "not-loopback"
        if refusal is not None or port is None:
            reason = refusal or "not-loopback"
            return reason, reason_text(reason)
        return router_spec(
            binary=binary,
            root=self.manager.root,
            port=port,
            models_max=config.models_max,
            memory_margin_mib=config.memory_margin_mib,
        )

    def _owned(self) -> Any:
        """Return the record of a router that runs and is ours, else ``None``."""
        record = read_server_record(router_dir(self.manager.root))
        if record is not None and runtime_process.owns(record.pid, record.binary):
            return record
        return None

    # ── Status ───────────────────────────────────────────────────────────

    def status(self, config: RouterConfig) -> RouterStatus:
        """Return the state from the runtime files. Starts and writes nothing."""
        program = program_in_force(config.binary)
        if config.mode == "external":
            self._end_wait()  # a mode change ends a waiting Start
            return self._external(config, program)
        folder = router_dir(self.manager.root)
        record = read_server_record(folder)
        owned = self._owned()
        checked = self.check(config)
        spec = checked if isinstance(checked, RuntimeSpec) else None
        models = self._models(config, owned)
        if owned is not None:
            running = (
                {
                    "models_max": _argument(owned.argv, "--models-max") or 0,
                    "memory_margin_mib": _argument(owned.argv, "--models-memory-margin") or 0,
                }
                if owned.argv
                else None
            )
            pending = spec is not None and owned.digest != spec.digest
            state: State = "running" if owned.state == "running" else "starting"
            return RouterStatus(state, None, None, running, pending, program, models)
        if self._waiting:
            if _still_downloading(models):
                line = reason_text(rules.NOT_DOWNLOADED, rules.DOWNLOADING)
                return RouterStatus(
                    "starting", rules.NOT_DOWNLOADED, line, None, False, program, models
                )
            # The downloads ended and the router did not start: one failed or was cancelled.
            self._end_wait((rules.NOT_DOWNLOADED, reason_text(rules.NOT_DOWNLOADED)))
        reason: tuple[str, str] | None = self._refusal
        # A stored ``not-downloaded`` line is stale: only this process knows its downloads.
        if reason is None and record is not None and record.reason != rules.NOT_DOWNLOADED:
            if record.reason:
                reason = (record.reason, record.reason_text or reason_text(record.reason))
            elif record.state != "stopped":
                reason = ("exited", reason_text("exited"))  # gone with no stop recorded: it crashed
        if reason is not None:
            return RouterStatus("failed", reason[0], reason[1], None, False, program, models)
        return RouterStatus("stopped", None, None, None, False, program, models)

    def _external(self, config: RouterConfig, program: dict[str, str]) -> RouterStatus:
        base = config.url.rstrip("/").removesuffix("/v1")
        health = runtime_process.http_get_json(f"{base}/health", _PROBE_SECONDS)[0]
        state: State = {200: "running", _HEALTH_LOADING: "starting"}.get(health, "stopped")  # type: ignore[assignment]
        live = runtime_readiness.router_models(base) if state == "running" else {}
        models = {
            entry.model: ModelState(_live_state(live.get(entry.model)))
            for entry in config.entries.values()
        }
        return RouterStatus(state, None, None, None, False, program, models)

    def _models(self, config: RouterConfig, owned: Any) -> dict[str, ModelState]:
        """Return the state of each listed model of a managed router."""
        folder = router_dir(self.manager.root)
        plan = plan_preset(
            list(config.entries.values()),
            decision_models=config.decision_models,
            hashes=HashCache(folder / HASHES_FILE),
        )
        running = owned is not None and owned.state == "running"
        live = runtime_readiness.router_models(f"http://127.0.0.1:{owned.port}") if running else {}
        written = split_sections(read_preset(folder)) if running else {}
        found: dict[str, ModelState] = {}
        for outcome in plan.outcomes:
            if outcome.state == "listed":
                state = _live_state(live.get(outcome.model))
                pending = running and written.get(outcome.model) != outcome.section
                found[outcome.model] = ModelState(state, None, None, outcome.note, pending)
            else:
                note = outcome.note
                if outcome.state == "not-downloaded" and download_running(outcome.model):
                    note = DOWNLOADING_NOTE
                found[outcome.model] = ModelState(
                    outcome.state, outcome.reason, outcome.reason_text or None, note
                )
        return found

    # ── Control ──────────────────────────────────────────────────────────

    def start(self, config: RouterConfig, *, ask_downloads: bool = True) -> RouterStatus:
        """Join the ``router`` runtime with *config*; it starts the router when none runs.

        A router that runs with other arguments is left alone (Restart applies
        them). Every refusal is a ``failed`` status with one fixed reason. A start
        that follows a finished download passes ``ask_downloads=False``: only the
        user's own Start asks for a download.
        """
        checked = self.check(config)
        self._end_wait()
        if not isinstance(checked, RuntimeSpec):
            self._refusal = checked
            return self.status(config)
        owned = self._owned()
        if owned is not None and owned.digest != checked.digest:
            return self.status(config)  # running with other arguments
        router = open_router(
            self.manager,
            checked,
            list(config.entries.values()),
            decision_models=config.decision_models,
        )
        if router.base.operator_stopped:
            router.leave()  # the operator's own Start: join again
        self._router = router
        router.ask_downloads = ask_downloads
        try:
            router.join()
        except RuntimeUnavailable as refused:
            if refused.reason == rules.NOT_DOWNLOADED:
                self._waiting = True  # the status says whether a download still runs
            else:
                self._refusal = (refused.reason, refused.reason_text)
        finally:
            router.ask_downloads = True
        return self.status(config)

    def stop(self, config: RouterConfig) -> RouterStatus:
        """Operator stop. With no recorded router, nothing is signalled.

        The lease stays: a process that joined this router does not start it
        again until it leaves. Start leaves and joins again. A Start that waits for
        downloads is over: the downloads end without starting the router.
        """
        self._end_wait()
        self.manager.stop(ROUTER_ID)
        return self.status(config)

    def restart(self, config: RouterConfig) -> RouterStatus:
        """Stop the router, then start it with *config*."""
        self.stop(config)
        return self.start(config)

    def apply_models(self, config: RouterConfig) -> dict[str, str]:
        """Apply the reload rule to a running router after a list change (design D7).

        Only a router that runs with the saved arguments is changed: the entry's
        section is rewritten and the router reloads that one model. A router that
        runs with other arguments, or none, is left alone; Start writes the file.

        Returns:
            ``{model: outcome}`` of the reload rule, or ``{}`` when nothing ran.
        """
        checked = self.check(config)
        owned = self._owned()
        if not isinstance(checked, RuntimeSpec) or owned is None or owned.state != "running":
            return {}
        if owned.digest != checked.digest:
            return {}  # "Restart to apply" first; the models.ini rewrite follows
        entries = list(config.entries.values())
        router = open_router(self.manager, checked, entries, decision_models=config.decision_models)
        return router.update_entries(entries, config.decision_models)

    def load(self, config: RouterConfig, model: str) -> None:
        """Load *model* after its automatic download, and end a waiting Start (task 6.2a).

        A router that runs with other arguments is left alone (Restart applies
        them). With no router running, nothing starts unless a Start still waits and no
        other listed model still downloads: then the router starts and loads every model
        that downloaded meanwhile. A mode other than ``managed`` starts nothing and ends
        the wait. The start that follows a download asks for no download, so when every
        download has ended and no model has a file the status reads ``not-downloaded`` and
        nothing is asked for again until the user presses Start. A refusal is logged only:
        the entry shows its own state.
        """
        if config.mode != "managed":
            self._end_wait()
            return
        checked = self.check(config)
        owned = self._owned()
        if not isinstance(checked, RuntimeSpec) or (owned and owned.digest != checked.digest):
            return
        entries = list(config.entries.values())
        with_file = {e.model for e in entries if (e.file or "").strip()}  # a failed one has none
        models = {model} & with_file
        if owned is None:
            if not self._waiting:
                return  # nothing asked for the router to start
            if _still_downloading(self._models(config, None)):
                self._to_load |= models  # the last download starts the router
                return
            models |= self._to_load & with_file
            self.start(config, ask_downloads=False)
            if self._owned() is None:
                return  # refused again: the status says why
        router = open_router(self.manager, checked, entries, decision_models=config.decision_models)
        for name in sorted(models):
            try:
                router.ensure_ready(name)
            except (RuntimeUnavailable, ModelUnavailable) as refused:
                logger.info("The downloaded model was not loaded: %s", refused.reason)

    def shutdown(self) -> None:
        """Leave the ``router`` lease when ``omrs web`` exits; the last client stops the router."""
        if self._router is not None:
            self._router.leave()


def _live_state(status: Mapping[str, object] | None) -> str:
    """Map the router's own ``status.value`` to a model state; an unknown word is ``unloaded``."""
    value = None if status is None else status.get("value")
    return str(value) if value in _LIVE_STATES else "unloaded"


def owning_lifespan(inner: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """Wrap an app lifespan with the runtime sweep at start and the router leave at shutdown.

    At start-up the manager stops every owned server that no OMRS process
    uses (design D9). While the app runs, the automatic model downloader
    (task 6.2a) is installed. At shutdown it stops, then the adapter leaves its
    lease. Both read ``app.state`` then, so a test can replace them. A failure
    is logged and never raised.
    """

    @asynccontextmanager
    async def lifespan(app: Any) -> AsyncIterator[None]:
        from .router_autodownload import RouterDownloads  # lazy: it imports the routes

        manager = getattr(app.state, "runtime_manager", None)
        if manager is not None:
            try:
                await run_in_threadpool(manager.sweep)
            except Exception:
                logger.exception("The llama.cpp runtime sweep failed.")
        downloads = RouterDownloads(app, asyncio.get_running_loop())
        install_downloader(downloads)
        try:
            async with inner(app):
                try:
                    yield
                finally:
                    install_downloader(None)
                    await downloads.close()
        finally:
            control = getattr(app.state, "llamacpp_router", None)
            if control is not None:
                try:
                    await run_in_threadpool(control.shutdown)
                except Exception:
                    logger.exception("The llama.cpp router runtime could not be left cleanly.")

    return lifespan
