"""``RouterLease``: this process's use of the router, one model at a time (design D6 to D8).

The router lease wraps the process's :class:`~.lease.RuntimeLease` of runtime
``router``, which joins, adopts, starts, restarts and stops the one router
process. On top of it, each model gets its own client lock, readiness check
and, for a one-slot entry, request lock:

1. a managed request names a listed model, or it is refused before any
   contact (``model-not-listed``);
2. the router lease joins the router; a start writes ``models.ini`` from this
   process's list first (:mod:`.preset_writer`);
3. on the first use of model X, under ``start.lock``, X's section in
   ``models.ini`` must equal this process's section; when it differs and no
   other process uses X, only that section is rewritten and the router
   reloads (:mod:`.reload`), else X gives ``version-busy``;
4. X is made ready (:mod:`.readiness`), once per lease and router start;
5. a one-slot X serialises on its ``request.lock``.

In external mode the lease only holds the URL: no name check, no load.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Collection, Iterable, Iterator
from typing import Any, TypeVar

from . import readiness
from .hashes import HashCache
from .lease import RuntimeLease, _is_connection_failure
from .locks import LockFile
from .manager import RuntimeManager
from .model_locks import ModelHolds, request_lock
from .model_reasons import ModelUnavailable
from .preset_writer import (
    EntryLike,
    EntryOutcome,
    PresetPlan,
    plan_preset,
    read_preset,
    split_sections,
    write_preset,
)
from .process import StartRefused
from .reload import apply_sections, running_record
from .router_spec import HASHES_FILE, ROUTER_ID, router_dir
from .spec import RuntimeSpec

T = TypeVar("T")

#: The line of an entry with no file yet (the download job is task 6.2a).
NOT_DOWNLOADED_TEXT = "The model file is not downloaded yet."


def open_router(
    manager: RuntimeManager,
    spec: RuntimeSpec,
    entries: Iterable[EntryLike],
    *,
    decision_models: Collection[str] = (),
) -> RouterLease:
    """Return this process's router lease for *spec* and the model list *entries*.

    One router lease exists per runtime lease. When the list changed since
    the last call, the reload rule applies (:meth:`RouterLease.update_entries`).

    Args:
        manager: The process's runtime manager.
        spec: :func:`.router_spec.router_spec` or :func:`.router_spec.external_router_spec`.
        entries: The ``llamacpp_models`` entries in force, already checked by
            compose (fields of ``config.llamacpp_models.LlamaCppModelEntry``).
        decision_models: Model names a managed ``llamacpp`` decision entry names.

    Raises:
        ValueError: *spec* is not the router runtime.
    """
    if spec.id != ROUTER_ID:
        raise ValueError(f"not the router runtime: {spec.id!r}")
    base = manager.lease(spec)
    router: RouterLease | None = getattr(base, "router_view", None)
    entries = list(entries)
    if router is None:
        router = RouterLease(base, entries, decision_models)
        base.router_view = router  # type: ignore[attr-defined]
    elif router.entries != entries or router.decision_models != frozenset(decision_models):
        router.update_entries(entries, decision_models)
    return router


def _names(entries: Iterable[EntryLike]) -> list[str]:
    return [entry.model for entry in entries]


class RouterLease:
    """This process's use of the router. Get it from :func:`open_router`."""

    def __init__(
        self, base: RuntimeLease, entries: list[EntryLike], decision_models: Collection[str]
    ) -> None:
        self.base = base
        self.spec = base.spec
        self.folder = router_dir(base.manager.root)
        self.entries = list(entries)
        self.decision_models = frozenset(decision_models)
        self._lock = threading.RLock()
        self._holds = ModelHolds(base.manager.root)
        self._plan: PresetPlan | None = None
        self._ready: dict[str, int] = {}
        self._active: dict[str, int] = {}
        self._pending: set[str] = set()
        if self.spec.mode == "managed":
            base.before_start = self._before_start
            base.on_leave(self._on_leave)

    # ── Plan and start ──────────────────────────────────────────────────

    def _new_plan(self) -> PresetPlan:
        """Check every entry again (caller holds ``start.lock``)."""
        hashes = HashCache(self.folder / HASHES_FILE)
        self._plan = plan_preset(self.entries, decision_models=self.decision_models, hashes=hashes)
        return self._plan

    def _before_start(self) -> dict[str, Any]:
        """Write ``models.ini`` before a router start (under ``start.lock``)."""
        with self._lock:
            plan = self._new_plan()
            if not plan.digests:
                raise StartRefused("not-configured")
            write_preset(self.folder, plan.text)
            self._ready.clear()
            return {"models": plan.digests, "argv": list(self.spec.argv)}

    def _on_leave(self) -> None:
        with self._lock:
            self._holds.release_all()
            self._ready.clear()

    def join(self) -> str:
        """Join the router (start or adopt it) and return its base URL."""
        return self.base.join()

    def leave(self) -> None:
        """Leave the router; it stops when no other OMRS process uses it."""
        self.base.leave()

    # ── One model ───────────────────────────────────────────────────────

    def _outcome(self, model: str) -> EntryOutcome:
        plan = self._plan if self._plan is not None else self._locked(self._new_plan)
        outcome = plan.outcome(model)
        if outcome is None:
            raise ModelUnavailable(model, "model-not-listed")
        return outcome

    def _locked(self, work: Callable[[], T]) -> T:
        start = LockFile(self.folder / "start.lock")
        start.acquire()
        try:
            return work()
        finally:
            start.close()

    def _join_model(self, model: str) -> None:
        """Hold *model* with this process's section in force (caller holds ``self._lock``)."""
        if self._holds.held(model):
            return

        def under_start() -> None:
            outcome = self._new_plan().outcome(model)
            if outcome is None:
                raise ModelUnavailable(model, "model-not-listed")
            if outcome.state == "not-downloaded":
                raise ModelUnavailable(model, "model-invalid", NOT_DOWNLOADED_TEXT)
            if outcome.state == "failed":
                raise ModelUnavailable(model, str(outcome.reason), outcome.reason_text)
            result = apply_sections(
                self.folder, {model: outcome.section}, self._holds, self._active
            )
            if result[model] == "version-busy":
                self._pending.add(model)
                raise ModelUnavailable(model, "version-busy")
            self._pending.discard(model)
            self._ready.pop(model, None)
            if not self._holds.hold(model):  # pragma: no cover - start.lock prevents it
                raise ModelUnavailable(model, "version-busy")

        self._locked(under_start)

    def ensure_ready(self, model: str) -> str:
        """Join the router and make *model* loaded; return the router base URL.

        Raises:
            ModelUnavailable: The model cannot serve; other models are not affected.
            RuntimeUnavailable: The router cannot serve.
        """
        with self.model_session(model) as url:
            return url

    @contextlib.contextmanager
    def model_session(self, model: str) -> Iterator[str]:
        """Hold the router and *model* for one request; yield the router base URL.

        The model is loaded and, for a one-slot entry, its request lock is held
        before this yields, so the caller's request timeout starts after both.

        Raises:
            ModelUnavailable: Before any request was sent to *model*.
            RuntimeUnavailable: The router cannot serve; nothing was sent.
        """
        managed = self.spec.mode == "managed"
        if managed and model not in _names(self.entries):
            raise ModelUnavailable(model, "model-not-listed")
        with self.base.session() as url:
            if not managed:
                yield url
                return
            with self._lock:
                self._join_model(model)
                self._active[model] = self._active.get(model, 0) + 1
            ticket: LockFile | None = None
            try:
                self._make_ready(url, model)
                if self._outcome(model).one_slot:
                    ticket = request_lock(self.base.manager.root, model)
                yield url
            finally:
                if ticket is not None:
                    ticket.close()
                with self._lock:
                    self._active[model] -= 1

    def _make_ready(self, url: str, model: str) -> None:
        generation = self.base.generation
        if self._ready.get(model) == generation:
            return
        readiness.ensure_loaded(url, model)
        with self._lock:
            self._ready[model] = generation

    def request_model(self, model: str, send: Callable[[str], T]) -> T:
        """Run ``send(base_url)`` for *model*, with one router crash restart.

        Raises:
            ModelUnavailable: Before dispatch, for *model* only.
            RuntimeUnavailable: The router cannot serve; nothing was sent.
        """
        with self.model_session(model) as url:
            try:
                return send(url)
            except Exception as error:
                if self.spec.mode != "managed" or not _is_connection_failure(error):
                    raise
                if not self.base.restart_if_crashed():
                    raise
            self._make_ready(self.base.base_url or url, model)
            return send(self.base.base_url or url)

    # ── Reload rule and status ──────────────────────────────────────────

    def update_entries(
        self, entries: Iterable[EntryLike], decision_models: Collection[str] | None = None
    ) -> dict[str, str]:
        """Take a new model list and apply the reload rule (design D7).

        Returns:
            ``{model: outcome}``: ``saved`` (no router runs; the next start
            writes the file), ``unchanged``, ``reloaded``, ``added``,
            ``removed`` or ``version-busy`` (another process uses the model;
            it shows as reload pending).
        """
        with self._lock:
            self.entries = list(entries)
            if decision_models is not None:
                self.decision_models = frozenset(decision_models)
            if self.spec.mode != "managed":
                return {entry.model: "saved" for entry in self.entries}

            def under_start() -> dict[str, str]:
                plan = self._new_plan()
                if running_record(self.folder) is None:
                    return {o.model: "saved" for o in plan.outcomes}
                wanted = {o.model: o.section for o in plan.outcomes}
                for name in split_sections(read_preset(self.folder)):
                    wanted.setdefault(name, "")
                result = apply_sections(self.folder, wanted, self._holds, self._active)
                for model, outcome in result.items():
                    if outcome == "version-busy":
                        self._pending.add(model)
                    else:
                        self._pending.discard(model)
                        if outcome != "unchanged":
                            self._ready.pop(model, None)
                return result

            return self._locked(under_start)

    def restart_pending(self) -> bool:
        """Whether the running router started with other router arguments ("Restart to apply")."""
        record = running_record(self.folder)
        return record is not None and record.digest != self.spec.digest

    def model_status(self) -> list[dict[str, Any]]:
        """Return one item per listed model: ``model``, ``state``, ``reason``,
        ``reason_text``, ``note`` and ``reload_pending``.

        A listed entry shows the router's own state when the router runs,
        else ``unloaded``. Reading starts nothing and writes nothing but the
        ``hashes.json`` cache.
        """
        with self._lock:
            plan = self._plan if self._plan is not None else self._locked(self._new_plan)
            pending = set(self._pending)
        record = running_record(self.folder) if self.spec.mode == "managed" else None
        live = readiness.router_models(f"http://127.0.0.1:{record.port}") if record else {}
        items: list[dict[str, Any]] = []
        for outcome in plan.outcomes:
            state: str = outcome.state
            if state == "listed":
                state = str(live.get(outcome.model, {}).get("value", "unloaded"))
            items.append(
                {
                    "model": outcome.model,
                    "state": state,
                    "reason": outcome.reason,
                    "reason_text": outcome.reason_text,
                    "note": outcome.note,
                    "reload_pending": outcome.model in pending,
                }
            )
        return items
