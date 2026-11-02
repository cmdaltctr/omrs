"""Ordered OCR routes (design D3; ordered-reader-and-ocr-lists D6).

Every OCR dispatch goes to the first route of the engine list. When that
route is unavailable BEFORE dispatch, the same request goes to the next one,
and so on down the list. After dispatch there is no switch: a worker failure
stays a per-file error (spec: no cross-route retry). The one exception is an
operator stop of the engine's runtime, which moves the request once
(``dispatch.RoutedClient``). An empty or poor answer never moves a request.

A route names an engine. The host resolves an engine from its name and
the workers directory alone: the engine's own environment runs the
shared worker core (``python -m omrs_ocr_worker_core``) from the engine
folder. The host never branches on engine names, so a new engine is a
new folder plus a route setting.

Both routes resolve only from the workers folder and an engine name, so a
pipeline step's chosen engine always applies (integrations-show-runtime-components,
design D7, removed the explicit ``OCR_WORKER_COMMAND`` override).
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .dispatch import RoutedClient
from .fingerprint import UNAVAILABLE_OCR_WORKER_FINGERPRINT, OcrWorkerFingerprint
from .managed import ManagedOcrClient
from .manifest import DeclaredRuntime, declared_runtime
from .runtime import runtime_lease

if TYPE_CHECKING:
    from ..llamacpp_runtime.manager import RuntimeManager

logger = logging.getLogger(__name__)

#: The module every engine environment runs.
WORKER_CORE_MODULE = "omrs_ocr_worker_core"

#: The shared model cache root, and the default cache folder inside an engine
#: folder. The worker core repeats this rule (its ``model_cache_dir``).
MODEL_CACHE_ENV = "OMRS_OCR_MODEL_CACHE"
MODEL_CACHE_DIRNAME = ".model-cache"

#: Engine names are folder names: no path separators, no parent links.
_ENGINE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

#: Route summaries already logged in this process (start-up log, once).
_logged_summaries: set[str] = set()

#: Settings in, the selected document router's page judge (or ``None``) out. The
#: composition root installs it (change document-reading-routers, design D12),
#: so this package imports no decision model provider.
_judge_factory: Callable[[Any], Any] | None = None


def install_judge_factory(factory: Callable[[Any], Any] | None) -> None:
    """Install the page judge factory of the OCR routes; ``None`` removes it."""
    global _judge_factory
    _judge_factory = factory


def page_judge(settings: Any) -> Any:
    """Return the page judge of *settings*: ``None`` with no factory or no router."""
    return _judge_factory(settings) if _judge_factory is not None else None


@dataclass(frozen=True)
class RouteCommand:
    """How to start one route's worker.

    Attributes:
        command: Argv-style launch command; empty means unavailable.
        cwd: Working directory for the worker, if any.
        runtime: The llama.cpp runtime the engine declares, or ``None``.
        runtime_url: Address of an external runtime (``ocr_runtime_url``);
            blank means the host starts the declared runtime.
    """

    command: tuple[str, ...]
    cwd: str | None
    runtime: DeclaredRuntime | None = None
    runtime_url: str = ""


_NO_ROUTE = RouteCommand(command=(), cwd=None)


def _engine_python(engine_dir: Path) -> Path:
    """Return the engine environment's interpreter path."""
    if os.name == "nt":  # pragma: no cover - POSIX CI
        return engine_dir / ".venv" / "Scripts" / "python.exe"
    return engine_dir / ".venv" / "bin" / "python"


def engine_cache_dir(name: str, engine_dir: Path, environ: Mapping[str, str] | None = None) -> Path:
    """Return the engine's model cache: ``$OMRS_OCR_MODEL_CACHE/<name>`` or ``.model-cache``."""
    root = (environ if environ is not None else os.environ).get(MODEL_CACHE_ENV, "").strip()
    if root:
        return Path(root).expanduser() / name
    return engine_dir / MODEL_CACHE_DIRNAME


def resolve_engine_command(
    engine: str, workers_dir: str, environ: Mapping[str, str] | None = None
) -> RouteCommand:
    """Resolve an engine name to its worker command.

    Args:
        engine: Engine name, the folder name under ``engines/``.
        workers_dir: The configured workers directory.
        environ: The environment that names the model cache; the process
            environment by default.

    Returns:
        The command ``<workers_dir>/engines/<engine>/.venv/bin/python -m
        omrs_ocr_worker_core`` with the engine folder as working
        directory, or an empty command when the name is empty or
        invalid, the directory is unset, the engine is not provisioned or
        its runtime declaration breaks a rule. The route carries the
        declared runtime when the engine has one.
    """
    name = engine.strip()
    root = workers_dir.strip()
    if not name or not root:
        return _NO_ROUTE
    if not _ENGINE_NAME_RE.match(name) or name in {".", ".."}:
        logger.warning("OCR engine name %r is not a folder name; route unavailable", name)
        return _NO_ROUTE
    engine_dir = Path(root).expanduser() / "engines" / name
    python = _engine_python(engine_dir)
    if not python.is_file():
        logger.info(
            "OCR engine %r is not provisioned (no %s); route unavailable. Run "
            "`python3 ocr-workers/provision.py %s`.",
            name,
            python,
            name,
        )
        return _NO_ROUTE
    try:
        runtime = declared_runtime(engine_dir, engine_cache_dir(name, engine_dir, environ))
    except ValueError as exc:  # RuntimeDeclarationError, or a manifest that does not parse
        logger.warning(
            "OCR engine %r runtime declaration refused: %s; route unavailable", name, exc
        )
        return _NO_ROUTE
    return RouteCommand(
        command=(str(python), "-m", WORKER_CORE_MODULE),
        cwd=str(engine_dir),
        runtime=runtime,
    )


def resolve_route_command(
    engine: str, settings: Any, runtime_manager: RuntimeManager | None = None
) -> RouteCommand:
    """Resolve one route's command from the injected workers folder.

    An engine that declares a runtime needs the runtime manager. Without one
    the route is unavailable. ``ocr_runtime_url`` turns the declared runtime
    external.
    """
    workers_dir = getattr(settings, "ocr_workers_dir", "")
    route = resolve_engine_command(
        engine,
        workers_dir if isinstance(workers_dir, str) else "",
        runtime_manager.environ if runtime_manager is not None else None,
    )
    if route.runtime is None:
        return route
    if runtime_manager is None:
        logger.warning(
            "OCR engine %r declares a llama.cpp runtime but no runtime manager is set; "
            "route unavailable",
            engine.strip(),
        )
        return _NO_ROUTE
    return replace(route, runtime_url=settings.ocr_runtime_url.strip())


def request_timeout(settings: Any, pages: int) -> float:
    """Return the timeout for one request of *pages* pages.

    ``max(ocr_worker_request_timeout, pages x ocr_worker_seconds_per_page)``:
    it grows with the request and is never below the per-request floor.
    """
    floor = float(settings.ocr_worker_request_timeout)
    per_page = float(getattr(settings, "ocr_worker_seconds_per_page", 0.0))
    return max(floor, max(pages, 0) * per_page)


def engine_names(settings: Any) -> tuple[str, ...]:
    """Return the engine order of *settings*: ``ocr_engines``, else primary then fallback.

    Mirrors ``core.reading_lists.engine_list``, which this leaf module cannot
    import (``integrations-are-leaves``). A test pins the two to the same answer.
    A blank name is left out; a fallback equal to the primary stays, so both
    entries resolve to one shared client.
    """
    listed = tuple(getattr(settings, "ocr_engines", ()) or ())
    if listed:
        return listed
    primary = str(getattr(settings, "ocr_engine_primary", "") or "").strip()
    fallback = str(getattr(settings, "ocr_engine_fallback", "") or "").strip()
    return tuple(name for name in (primary, fallback) if name)


@dataclass(frozen=True)
class OcrRoutes:
    """The frozen, ordered route clients (design D3, D6).

    Each route owns one lazy, long-lived client. A route's subprocess
    starts only on that route's first dispatch. Routes that resolve to the
    same command share one client.

    Attributes:
        routes: The route clients in list order. An entry is ``None`` when its
            engine resolved no command; it reports the unavailable fingerprint.
        judge: The page judge of the selected document router, or ``None``. The
            composition root builds it per settings (change document-reading-routers,
            design D12); the page unit hands it to the page rules.
    """

    routes: tuple[Any, ...] = ()
    judge: Any = None

    @classmethod
    def of(cls, client: Any) -> OcrRoutes:
        """Return *client* as routes: routes pass through, a client is the first route only."""
        if isinstance(client, OcrRoutes):
            return client
        return cls(routes=(client,))

    @property
    def primary(self) -> Any:
        """The first route's client, or ``None``."""
        return self.routes[0] if self.routes else None

    @property
    def fallback(self) -> Any:
        """The second route's client, or ``None``."""
        return self.routes[1] if len(self.routes) > 1 else None

    @property
    def fingerprints(self) -> tuple[OcrWorkerFingerprint, ...]:
        """The fingerprint of every route, in list order."""
        return tuple(_fingerprint_of(client) for client in self.routes)

    @property
    def fingerprint(self) -> OcrWorkerFingerprint:
        """The first route's fingerprint (the index identity's worker field)."""
        return _fingerprint_of(self.primary)

    @property
    def fallback_fingerprint(self) -> OcrWorkerFingerprint:
        """The second route's fingerprint."""
        return _fingerprint_of(self.fallback)

    def select(self, *, protocol: str | None = None) -> Any:
        """Return the client for the next dispatch, chosen BEFORE dispatch.

        Args:
            protocol: When set, only a route whose fingerprint speaks this
                protocol version is usable (page-listed requests need 1.1).

        Returns:
            The first available client, else ``None``. When two or more are
            available and one holds a runtime lease, a :class:`RoutedClient`: a
            route that cannot start its runtime before dispatch passes the
            request on (design D10). Only availability decides. The answer a
            route gave never does.
        """
        usable: list[Any] = []
        for client in self.routes:
            if client is None or client in usable:
                continue
            fingerprint = _fingerprint_of(client)
            if not fingerprint.available:
                continue
            if protocol is not None and fingerprint.protocol_version != protocol:
                continue
            usable.append(client)
        if len(usable) > 1 and any(getattr(c, "lease", None) is not None for c in usable):
            return RoutedClient(usable)
        return usable[0] if usable else None

    def close(self) -> None:
        """Close every distinct route client."""
        closed: set[int] = set()
        for client in self.routes:
            if client is not None and id(client) not in closed:
                closed.add(id(client))
                client.close()


def _fingerprint_of(client: Any) -> OcrWorkerFingerprint:
    """Return a client's fingerprint, or the unavailable constant."""
    if client is None:
        return UNAVAILABLE_OCR_WORKER_FINGERPRINT
    return getattr(client, "fingerprint", UNAVAILABLE_OCR_WORKER_FINGERPRINT)


def backend_id_of(client: Any) -> str:
    """Return the answering engine's backend identifier for diagnostics.

    A worker that predates ``backend_id`` reports the generic
    ``ocr_worker``, never a guessed engine name.
    """
    return getattr(_fingerprint_of(client), "backend_id", "") or "ocr_worker"


def build_route_clients(
    settings: Any,
    *,
    probe: Callable[[list[str]], OcrWorkerFingerprint],
    runtime_manager: RuntimeManager | None = None,
) -> OcrRoutes:
    """Compose the route clients of the engine list from injected settings.

    The probe runs only when the operator enabled OCR and the route
    resolved a command, so an unconfigured install spawns nothing.

    Args:
        settings: Settings carrying the OCR route fields.
        probe: The composition boundary's capability probe.
        runtime_manager: The process's runtime manager. A route whose engine
            declares a llama.cpp runtime is unavailable without one.

    Returns:
        The routes in list order, with the page judge of the settings' router.
        Routes that resolve to the same command share one client.
        Construction starts no parsing process.
    """
    enabled = bool(getattr(settings, "ocr_fallback_enabled", False))
    names = engine_names(settings)
    shared: dict[RouteCommand, ManagedOcrClient] = {}
    clients: list[ManagedOcrClient] = []
    for name in names:
        route = resolve_route_command(name, settings, runtime_manager)
        if route not in shared:
            shared[route] = _client(
                route, settings, probe=probe, enabled=enabled, runtime_manager=runtime_manager
            )
        clients.append(shared[route])
    routes = OcrRoutes(routes=tuple(clients), judge=page_judge(settings))
    if enabled:
        _log_routes_once(names, routes)
    return routes


def _client(
    route: RouteCommand,
    settings: Any,
    *,
    probe: Callable[[list[str]], OcrWorkerFingerprint],
    enabled: bool,
    runtime_manager: RuntimeManager | None,
) -> ManagedOcrClient:
    """Build one route's managed client, probing only when it can run."""
    command = list(route.command)
    fingerprint = probe(command) if enabled and command else UNAVAILABLE_OCR_WORKER_FINGERPRINT
    return ManagedOcrClient(
        fingerprint=fingerprint,
        command=command,
        request_timeout=settings.ocr_worker_request_timeout,
        cwd=route.cwd,
        lease=runtime_lease(route, runtime_manager),
    )


def route_role(index: int) -> str:
    """Name a list position (0-based): primary, fallback, then ``engine 3``."""
    return ("primary", "fallback")[index] if index < 2 else f"engine {index + 1}"


def _log_routes_once(names: tuple[str, ...], routes: OcrRoutes) -> None:
    """Log the resolved engines once per process; the line always shows two roles."""
    padded = names + ("",) * (2 - len(names))
    states = ["available" if fp.available else "unavailable" for fp in routes.fingerprints]
    states += ["unavailable"] * (len(padded) - len(states))
    words = [
        f"{route_role(i)}={name or '-'} [{state}]"
        for i, (name, state) in enumerate(zip(padded, states, strict=True))
    ]
    _log_once("OCR routes: " + ", ".join(words))


def _log_once(summary: str) -> None:
    """Log *summary* at most once per process."""
    if summary in _logged_summaries:
        return
    _logged_summaries.add(summary)
    logger.info(summary)


def log_route_plan(settings: Any) -> None:
    """Log the engines once, from the engine folders alone.

    The Engine-owned pool starts a worker on first use, so this start-up line
    starts no process and probes nothing: an engine is ``provisioned`` when its
    interpreter exists. Nothing is logged while OCR fallback is off.
    """
    if not getattr(settings, "ocr_fallback_enabled", False):
        return
    workers_dir = str(getattr(settings, "ocr_workers_dir", "") or "")
    names = engine_names(settings)
    words = []
    for index, name in enumerate(names + ("",) * (2 - len(names))):
        # The engine folder alone answers this. ``resolve_route_command`` also asks for the
        # runtime manager, which this line does not have, and would call the route unavailable.
        state = (
            "provisioned"
            if resolve_engine_command(name, workers_dir).command
            else "not provisioned"
        )
        words.append(f"{route_role(index)}={name or '-'} [{state}]")
    summary = "OCR routes: " + ", ".join(words)
    if not str(getattr(settings, "ocr_workers_dir", "") or "").strip():
        summary += " (OCR workers folder not set)"
    _log_once(summary)


def reset_route_log() -> None:
    """Forget which route summaries were logged (used by tests)."""
    _logged_summaries.clear()
