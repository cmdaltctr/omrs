"""The runtime manager of this process and the leases it injects (managed-llamacpp-runtimes D1).

``compose`` builds one :class:`RuntimeManager` per process and installs a gate
resolver (:mod:`omrs.core.runtime_gate`). The llama.cpp Chat, classification
and embedding clients in ``core/`` ask the resolver for a gate; this module
answers with an adapted lease of the ``chat`` or ``embeddings`` runtime, or
``None`` when the role is ``external``. Classification shares the Chat
runtime only when ``llamacpp_classify_url`` is blank.

The module also lists the runtimes in force for ``GET /v1/runtimes``: Chat,
embeddings and one OCR runtime for each OCR route whose engine declares one.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from .compose_runtime_manager import close_runtime_manager, runtime_manager
from .core import runtime_gate
from .core.runtime_gate import GateRefused, Role, RuntimeGate
from .integrations.llamacpp_runtime import (
    DeclaredFile,
    RuntimeLease,
    RuntimeManager,
    RuntimeRequestFailed,
    RuntimeSpec,
    RuntimeUnavailable,
    chat_spec,
    embeddings_spec,
    ocr_spec,
)
from .integrations.llamacpp_runtime.lease import reason_text
from .integrations.llamacpp_runtime.rules import loopback_port, model_kind

if TYPE_CHECKING:
    from .compose_providers import ProviderValues
    from .config import Settings

T = TypeVar("T")

#: The OCR route settings, in the order the list shows them.
OCR_ROUTE_SETTINGS = ("ocr_engine_primary", "ocr_engine_fallback")


def reset() -> None:
    """Leave every lease, drop the manager and remove the gate resolver (tests)."""
    runtime_gate.install(None)
    close_runtime_manager()


# ── Settings in force ────────────────────────────────────────────────────


def current_settings(values: ProviderValues | None = None) -> Settings:
    """Return the resolved settings with the saved web values applied."""
    from . import compose
    from .compose_providers import apply_provider_values

    settings = compose.get_settings()
    return apply_provider_values(settings, values) if values is not None else settings


def _chat_model(settings: Any) -> str:
    """The model OMRS's Chat server loads: the Chat model while Chat is llama.cpp (ADR-108)."""
    return str(settings.answer.model) if settings.answer.provider.strip() == "llamacpp" else ""


def chat_runtime(settings: Any) -> RuntimeSpec | str:
    """Return the ``chat`` spec, or the reason a managed one cannot be built."""
    if settings.llamacpp_chat_server != "managed":
        return RuntimeSpec(
            id="chat", role="chat", mode="external", binary="", url_base=settings.llamacpp_chat_url
        )
    return _managed(
        lambda kind, port: chat_spec(
            mode="managed",
            binary=settings.llamacpp_server_binary,
            model=_chat_model(settings),
            port=port,
            window=int(settings.llamacpp_context_window),
            kind=kind,
        ),
        settings.llamacpp_server_binary,
        _chat_model(settings),
        settings.llamacpp_chat_url,
    )


def embeddings_runtime(settings: Any) -> RuntimeSpec | str:
    """Return the ``embeddings`` spec, or the reason a managed one cannot be built."""
    if settings.llamacpp_embed_server != "managed":
        url = settings.llamacpp_embed_url
        return RuntimeSpec(
            id="embeddings", role="embeddings", mode="external", binary="", url_base=url
        )
    return _managed(
        lambda kind, port: embeddings_spec(
            mode="managed",
            binary=settings.llamacpp_server_binary,
            model=settings.llamacpp_embed_model,
            port=port,
            kind=kind,
        ),
        settings.llamacpp_server_binary,
        settings.llamacpp_embed_model,
        settings.llamacpp_embed_url,
    )


def _managed(build: Callable[[Any, int], RuntimeSpec], binary: str, model: str, url: str) -> Any:
    if not binary.strip() or not model.strip():
        return "not-configured"
    kind = model_kind(model)
    if kind is None:
        return "model-invalid"
    port = loopback_port(url)
    if port is None:
        return "not-loopback"
    return build(kind, port)


# ── Gates for the clients in core/ ───────────────────────────────────────


class LeaseGate:
    """A runtime lease seen through :class:`~omrs.core.runtime_gate.RuntimeGate`."""

    def __init__(self, lease: RuntimeLease) -> None:
        self.lease = lease

    def request(self, send: Callable[[str], T]) -> T:
        """Run ``send(base_url)`` through the lease; a refusal becomes ``GateRefused``."""
        try:
            return self.lease.request(send)
        except RuntimeUnavailable as exc:
            raise GateRefused(exc.reason, exc.reason_text) from exc
        except RuntimeRequestFailed as exc:
            raise GateRefused(exc.reason, reason_text(exc.reason)) from exc

    async def arequest(self, send: Callable[[str], Awaitable[T]]) -> T:
        """The async form of :meth:`request`."""
        try:
            return await self.lease.arequest(send)
        except RuntimeUnavailable as exc:
            raise GateRefused(exc.reason, exc.reason_text) from exc
        except RuntimeRequestFailed as exc:
            raise GateRefused(exc.reason, reason_text(exc.reason)) from exc


class RefusedGate:
    """A managed role whose spec cannot be built: every request is refused at once."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def request(self, send: Callable[[str], T]) -> T:
        """Refuse."""
        raise GateRefused(self.reason, reason_text(self.reason))

    async def arequest(self, send: Callable[[str], Awaitable[T]]) -> T:
        """Refuse."""
        raise GateRefused(self.reason, reason_text(self.reason))


def gate(role: Role, settings: Any) -> RuntimeGate | None:
    """Return the gate of *role* under *settings*, or ``None`` for an external role."""
    if role == "classification" and str(settings.llamacpp_classify_url or "").strip():
        return None  # classification has its own address: not OMRS's Chat server
    spec = embeddings_runtime(settings) if role == "embeddings" else chat_runtime(settings)
    if isinstance(spec, str):
        return RefusedGate(spec)
    if spec.mode == "external":
        return None
    return LeaseGate(runtime_manager().lease(spec))


def install_gates(provider_source: Callable[[], ProviderValues] | None) -> None:
    """Install the gate resolver of this process.

    Args:
        provider_source: Returns the saved web values (``omrs web``); ``None``
            reads the settings alone (the CLI, the stdio MCP server, the watcher).
    """

    def resolve(role: Role) -> RuntimeGate | None:
        values = provider_source() if provider_source is not None else None
        return gate(role, current_settings(values))

    runtime_gate.install(resolve)


# ── The runtimes list (GET /v1/runtimes) ─────────────────────────────────


def _ocr_runtimes(settings: Any) -> dict[str, tuple[RuntimeSpec, list[str]]]:
    """Return the OCR runtimes of the routes in force, keyed by runtime id."""
    from .integrations.ocr_worker.manifest import declared_runtime
    from .integrations.ocr_worker.routes import engine_cache_dir

    workers = str(getattr(settings, "ocr_workers_dir", "") or "").strip()
    found: dict[str, tuple[RuntimeSpec, list[str]]] = {}
    if not workers:
        return found
    external = str(getattr(settings, "ocr_runtime_url", "") or "").strip()
    for setting in OCR_ROUTE_SETTINGS:
        name = str(getattr(settings, setting, "") or "").strip()
        if not name or "/" in name or name in {".", ".."}:
            continue
        if f"ocr-{name}" in found:
            found[f"ocr-{name}"][1].append(setting)
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
        found[spec.id] = (spec, [setting])
    return found


def runtime_specs(settings: Any) -> list[tuple[RuntimeSpec, list[str]]]:
    """Return each runtime in force with the settings that use it."""
    chat = chat_runtime(settings)
    embed = embeddings_runtime(settings)
    chat_users = ["llamacpp_chat_url"]
    if not str(settings.llamacpp_classify_url or "").strip():
        chat_users.append("llamacpp_classify_url")
    rows = [
        (_listed("chat", chat), chat_users),
        (_listed("embeddings", embed), ["llamacpp_embed_url"]),
    ]
    rows += list(_ocr_runtimes(settings).values())
    return rows


def _listed(runtime_id: str, spec: RuntimeSpec | str) -> RuntimeSpec:
    """A spec for the status read; a managed role that cannot be built keeps its id."""
    if isinstance(spec, RuntimeSpec):
        return spec
    return RuntimeSpec(id=runtime_id, role=runtime_id, mode="managed", binary="")  # type: ignore[arg-type]


def list_runtimes(
    values: ProviderValues | None = None, manager: RuntimeManager | None = None
) -> list[dict[str, Any]]:
    """Return the ``GET /v1/runtimes`` items. Starts nothing and writes nothing.

    Args:
        values: The saved web values, applied over the resolved settings.
        manager: The runtime manager to read with; this process's by default.
    """
    rows = runtime_specs(current_settings(values))
    used_by = {spec.id: users for spec, users in rows}
    reader = manager if manager is not None else runtime_manager()
    return reader.status([spec for spec, _ in rows], used_by)


def find_runtime(runtime_id: str, values: ProviderValues | None = None) -> RuntimeSpec | None:
    """Return the listed spec of *runtime_id*, or ``None`` when it is not in force."""
    for spec, _ in runtime_specs(current_settings(values)):
        if spec.id == runtime_id:
            return spec
    return None
