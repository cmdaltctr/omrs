"""The runtime manager process and the router gates it injects (one-llamacpp-router D1, D6).

``compose`` builds one :class:`RuntimeManager` per process and installs the gate
resolver (:mod:`omrs.core.runtime_gate`). Every llama.cpp client in ``core/``
(embeddings, classification, Chat, judge) asks the resolver for a gate. One
router serves every model by name: the gate takes the router lease, makes the
request's model ready and takes the model's request lock when the entry is
one-slot. The answer is ``None`` while the router is ``external``.

The module lists the runtimes in force for ``GET /v1/runtimes``: the router,
with one row per listed model, and one OCR runtime for each engine in the OCR
engine list that declares one. OCR runtimes do not change.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable, Iterator, Mapping
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, TypeVar

from .compose_runtime_manager import close_runtime_manager, runtime_manager
from .core import runtime_gate
from .core.reading_lists import engine_list
from .core.runtime_gate import GateRefused, Role, RuntimeGate
from .integrations.llamacpp_runtime import (
    ROUTER_ID,
    DeclaredFile,
    ModelUnavailable,
    RouterLease,
    RuntimeManager,
    RuntimeRequestFailed,
    RuntimeSpec,
    RuntimeUnavailable,
    external_router_spec,
    ocr_spec,
    open_router,
    process,
    resolve_server_binary,
    router_spec,
)
from .integrations.llamacpp_runtime.lease import reason_text
from .integrations.llamacpp_runtime.rules import NOT_PROVISIONED, child_environment, loopback_port

if TYPE_CHECKING:
    from .compose_providers import ProviderValues
    from .config import Settings

T = TypeVar("T")


def reset() -> None:
    """Leave every lease, drop the manager and remove the gate resolver (tests)."""
    from .integrations.ocr_worker.routes import install_judge_factory

    runtime_gate.install(None)
    install_judge_factory(None)
    close_runtime_manager()


# ── Settings in force ────────────────────────────────────────────────────


def current_settings(values: ProviderValues | None = None) -> Settings:
    """Return the resolved settings with the saved web values applied."""
    from . import compose
    from .compose_providers import apply_provider_values

    settings = compose.get_settings()
    return apply_provider_values(settings, values) if values is not None else settings


def _setting(settings: Any, name: str) -> Any:
    """Return router setting *name*; ``EffectiveSettings`` lacks some, so the process gives them."""
    value = getattr(settings, name, None)
    return value if value is not None else getattr(current_settings(), name)


def _field(entry: Any, name: str) -> Any:
    """Return field *name* of a settings map entry given as a mapping or an object."""
    return entry.get(name) if isinstance(entry, Mapping) else getattr(entry, name, None)


def managed_decision_models(settings: Any) -> list[str]:
    """Return the ``model`` of each managed ``llamacpp`` decision entry (the decision role)."""
    return [
        str(_field(entry, "model"))
        for entry in (getattr(settings, "decision_models", None) or {}).values()
        if _field(entry, "kind") == "llamacpp" and _field(entry, "server") == "managed"
    ]


_ENTRY_FIELDS = ("model", "file", "projector", "sha256", "projector_sha256", "preset")


def _entry(entry: Any) -> SimpleNamespace:
    """Return one ``llamacpp_models`` entry as the object the preset writer reads."""
    return SimpleNamespace(**{name: _field(entry, name) for name in _ENTRY_FIELDS})


def _entries(settings: Any) -> list[SimpleNamespace]:
    """Return the ``llamacpp_models`` entries in force, in list order."""
    return [_entry(e) for e in (getattr(settings, "llamacpp_models", None) or {}).values()]


# ── The router ───────────────────────────────────────────────────────────


def router_runtime(settings: Any) -> RuntimeSpec | str:
    """Return the router spec (managed or external), or the reason a managed one cannot be built.

    Returns:
        The spec, or ``not-provisioned`` (no program set and no pinned build
        installed) or ``not-loopback`` (the router address is not a loopback ``http`` URL).
    """
    url = str(_setting(settings, "llamacpp_router_url"))
    if _setting(settings, "llamacpp_router_server") != "managed":
        return external_router_spec(url)
    binary = resolve_server_binary(str(_setting(settings, "llamacpp_server_binary") or ""))
    if not binary.strip():
        return NOT_PROVISIONED
    port = loopback_port(url)
    if port is None:
        return "not-loopback"
    return router_spec(
        binary=binary,
        root=runtime_manager().root,
        port=port,
        models_max=int(_setting(settings, "llamacpp_router_models_max")),
        memory_margin_mib=int(_setting(settings, "llamacpp_router_memory_margin_mib")),
    )


def router_lease_for(settings: Any) -> RouterLease | str:
    """Return this process's router lease under *settings*, or the reason it cannot be built.

    Building the lease starts nothing; the first request joins the router.
    """
    spec = router_runtime(settings)
    if isinstance(spec, str):
        return spec
    decision = managed_decision_models(settings)
    return open_router(runtime_manager(), spec, _entries(settings), decision_models=decision)


def _refusal(error: Exception) -> GateRefused:
    if isinstance(error, (ModelUnavailable, RuntimeUnavailable)):
        return GateRefused(error.reason, error.reason_text)
    reason = str(getattr(error, "reason", "exited"))
    return GateRefused(reason, reason_text(reason))


_REFUSALS = (ModelUnavailable, RuntimeUnavailable, RuntimeRequestFailed)


class RouterGate:
    """The router lease seen through :class:`~omrs.core.runtime_gate.RuntimeGate`."""

    def __init__(self, router: RouterLease) -> None:
        self.router = router

    @staticmethod
    def _named(model: str | None) -> str:
        if not model:  # nothing names the model: no entry can serve it
            raise GateRefused("model-not-listed", reason_text("model-not-listed"))
        return model

    def request(self, send: Callable[[str], T], model: str | None = None) -> T:
        """Run ``send(base_url)`` for *model*; a refusal becomes ``GateRefused``."""
        name = self._named(model)
        try:
            return self.router.request_model(name, send)
        except _REFUSALS as error:
            raise _refusal(error) from error

    async def arequest(self, send: Callable[[str], Awaitable[T]], model: str | None = None) -> T:
        """The async form of :meth:`request`.

        The lock, load and crash-restart work runs in a thread; *send* runs on
        this event loop, which is free while the thread waits for it.
        """
        name = self._named(model)
        loop = asyncio.get_running_loop()

        def send_on_loop(url: str) -> T:
            return asyncio.run_coroutine_threadsafe(send(url), loop).result()  # type: ignore[arg-type]

        try:
            return await asyncio.to_thread(self.router.request_model, name, send_on_loop)
        except _REFUSALS as error:
            raise _refusal(error) from error


class RefusedGate:
    """A managed router whose spec cannot be built: every request is refused at once."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def request(self, send: Callable[[str], T], model: str | None = None) -> T:
        """Refuse."""
        raise GateRefused(self.reason, reason_text(self.reason))

    async def arequest(self, send: Callable[[str], Awaitable[T]], model: str | None = None) -> T:
        """Refuse."""
        raise GateRefused(self.reason, reason_text(self.reason))


def gate(role: Role, settings: Any) -> RuntimeGate | None:
    """Return the gate of *role* under *settings*, or ``None`` for an external router.

    Every role uses the one router; the request's model name picks the model.
    """
    router = router_lease_for(settings)
    if isinstance(router, str):
        return RefusedGate(router)
    return None if router.spec.mode == "external" else RouterGate(router)


def install_gates(provider_source: Callable[[], ProviderValues] | None) -> None:
    """Install the gate resolver of this process and the page judge factory of its OCR routes.

    The OCR routes take each settings' document router judge from the factory
    (change document-reading-routers, design D12); a managed decision model
    asks through the router (one-llamacpp-router, D10).

    Args:
        provider_source: Returns the saved web values (``omrs web``); ``None``
            reads the settings alone (the CLI, the stdio MCP server, the watcher).
    """

    def resolve(role: Role) -> RuntimeGate | None:
        values = provider_source() if provider_source is not None else None
        return gate(role, current_settings(values))

    runtime_gate.install(resolve)
    from .compose_decision import page_judge_for
    from .integrations.ocr_worker.routes import install_judge_factory

    install_judge_factory(page_judge_for)


def decision_router_for(settings: Any, entry: Any) -> RouterLease | str | None:
    """Return the router lease a decision *entry* asks through, a reason, or ``None``.

    ``None`` for an entry OMRS does not run (not ``llamacpp``, or not ``managed``).
    """
    if _field(entry, "kind") != "llamacpp" or _field(entry, "server") != "managed":
        return None
    return router_lease_for(settings)


def decision_build_line(router: RouterLease | str | None) -> str | None:
    """Return the llama.cpp build line of the router a decision entry uses, ``None`` for none."""
    if router is None:
        return None
    if isinstance(router, str):
        return reason_text(router)
    if router.spec.mode != "managed":
        return None
    floor = router.spec.min_build
    found = process.read_build(router.spec.binary, child_environment(os.environ, "file"))
    if found is None:
        return f"llama.cpp build not found; it needs b{floor} or later."
    if floor is not None and found < floor:
        return f"llama.cpp build b{found} is below the floor b{floor}."
    return f"llama.cpp build b{found}."


# ── The runtimes list (GET /v1/runtimes) ─────────────────────────────────


def _ocr_runtimes(settings: Any) -> dict[str, tuple[RuntimeSpec, list[str]]]:
    """Return the OCR runtimes of the engines in ``ocr_engines``, keyed by runtime id."""
    from .integrations.ocr_worker.manifest import declared_runtime
    from .integrations.ocr_worker.routes import engine_cache_dir

    workers = str(getattr(settings, "ocr_workers_dir", "") or "").strip()
    found: dict[str, tuple[RuntimeSpec, list[str]]] = {}
    if not workers:
        return found
    external = str(getattr(settings, "ocr_runtime_url", "") or "").strip()
    for entry in engine_list(settings):
        name = str(entry or "").strip()
        if not name or "/" in name or name in {".", ".."}:
            continue
        if f"ocr-{name}" in found:
            continue
        folder = Path(workers).expanduser() / "engines" / name
        try:
            declared = declared_runtime(folder, engine_cache_dir(name, folder))
            if declared is None:
                continue
            spec = ocr_spec(
                engine_folder=name,
                binary=str(declared.program),
                build=declared.build,
                flags=declared.flags,
                files=[DeclaredFile(f.flag, str(f.path), f.sha256) for f in declared.files],
            )
        except ValueError:  # a broken declaration or folder name: the route is unavailable
            continue
        if external:
            spec = replace(spec, mode="external", url_base=external)
        found[spec.id] = (spec, ["ocr_engines"])
    return found


#: The setting that gives each router role (``config.llamacpp_roles``).
_ROLE_SETTINGS = {
    "embeddings": "llamacpp_embed_model",
    "classification": "llamacpp_chat_model",
    "chat": "answer.model",
    "judge": "answer.verify_model",
    "decision": "decision_models",
}


def _roles(settings: Any) -> Any:
    from .compose_answer import llamacpp_roles

    return llamacpp_roles(settings)


def runtime_specs(settings: Any) -> list[tuple[RuntimeSpec, list[str]]]:
    """Return each runtime in force with the settings that use it: the router, then OCR."""
    spec = router_runtime(settings)
    if isinstance(spec, str):  # a managed router that cannot be built keeps its id
        spec = RuntimeSpec(id=ROUTER_ID, role="router", mode="managed", binary="")
    held = {role for roles in _roles(settings).roles.values() for role in roles}
    users = sorted(_ROLE_SETTINGS[role] for role in held)
    return [(spec, users), *_ocr_runtimes(settings).values()]


def model_memory_bytes(status: Mapping[str, Any]) -> int | None:
    """Return the router's own memory figure of one model, ``None`` when it reports none.

    The figure is the sum of ``model``, ``context`` and ``compute`` over every
    device of the ``memory.effective`` object (spike 1.2).
    """
    memory = status.get("memory")
    effective = memory.get("effective") if isinstance(memory, Mapping) else None
    if not isinstance(effective, Mapping):
        return None
    total = 0
    for device in effective.get("devices") or []:
        for key in ("model", "context", "compute"):
            value = device.get(key) if isinstance(device, Mapping) else None
            total += value if isinstance(value, int) else 0
    return total


def _live_models(spec: RuntimeSpec, item: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the router's own model table while it runs, else ``{}`` (a read only)."""
    from .integrations.llamacpp_runtime import readiness

    if item.get("state") != "running":
        return {}
    if spec.mode == "managed":
        return readiness.router_models(f"http://{item['address']}") if item.get("address") else {}
    return readiness.router_models(spec.url_base.rstrip("/").removesuffix("/v1"))


def _model_rows(
    settings: Any, spec: RuntimeSpec, item: Mapping[str, Any]
) -> Iterator[dict[str, Any]]:
    """Yield one ``models`` row per listed entry. Starts nothing and writes nothing.

    A managed entry that cannot serve shows its own state (``not-downloaded``,
    or ``failed`` with a fixed reason). Otherwise the row shows the router's
    state of the model while it runs, else ``unloaded``.
    """
    from .integrations.llamacpp_runtime import readiness
    from .integrations.llamacpp_runtime.hashes import HashCache
    from .integrations.llamacpp_runtime.preset_writer import plan_entry
    from .integrations.llamacpp_runtime.router_spec import HASHES_FILE, router_dir

    report = _roles(settings)
    hashes = HashCache(router_dir(runtime_manager().root) / HASHES_FILE, save=False)
    decision = set(managed_decision_models(settings))
    live = _live_models(spec, item)
    for name, entry in (getattr(settings, "llamacpp_models", None) or {}).items():
        model = str(_field(entry, "model"))
        row: dict[str, Any] = {"model": model, "roles": list(report.roles.get(name, ()))}
        row.update(state="unloaded", reason=None, memory_bytes=None)
        if spec.mode == "managed":
            outcome = plan_entry(_entry(entry), decision=model in decision, hashes=hashes)
            if outcome.state != "listed":
                row.update(state=outcome.state, reason=outcome.reason)
                yield row
                continue
        if model in live:
            row["state"] = readiness.status_word(live[model])
            row["memory_bytes"] = model_memory_bytes(live[model])
        yield row


def list_runtimes(
    values: ProviderValues | None = None, manager: RuntimeManager | None = None
) -> list[dict[str, Any]]:
    """Return the ``GET /v1/runtimes`` items. Starts nothing and writes nothing.

    Args:
        values: The saved web values, applied over the resolved settings.
        manager: The runtime manager to read with; this process's by default.
    """
    settings = current_settings(values)
    rows = runtime_specs(settings)
    used_by = {spec.id: users for spec, users in rows}
    reader = manager if manager is not None else runtime_manager()
    items = reader.status([spec for spec, _ in rows], used_by)
    for (spec, _), item in zip(rows, items, strict=True):
        item["models"] = list(_model_rows(settings, spec, item)) if spec.id == ROUTER_ID else []
    refusal = router_runtime(settings)
    if isinstance(refusal, str) and items[0]["state"] == "stopped":
        items[0].update(state="failed", reason=refusal, reason_text=reason_text(refusal))
    return items


def find_runtime(runtime_id: str, values: ProviderValues | None = None) -> RuntimeSpec | None:
    """Return the listed spec of *runtime_id*, or ``None`` when it is not in force."""
    for spec, _ in runtime_specs(current_settings(values)):
        if spec.id == runtime_id:
            return spec
    return None
