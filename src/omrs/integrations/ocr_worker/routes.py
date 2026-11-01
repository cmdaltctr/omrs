"""Primary and fallback OCR routes (design D3).

Every OCR dispatch goes to the primary route. When the primary route is
unavailable BEFORE dispatch, the same request goes to the fallback route.
After dispatch there is no switch: a worker failure stays a per-file
error (spec: no cross-route retry).

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


@dataclass(frozen=True)
class OcrRoutes:
    """The frozen pair of route clients (design D3).

    Each route owns one lazy, long-lived client. A route's subprocess
    starts only on that route's first dispatch. A fallback that resolves
    to the primary's command shares the primary's client.

    Attributes:
        primary: The primary route's client, or ``None``.
        fallback: The fallback route's client, or ``None``.
    """

    primary: Any = None
    fallback: Any = None

    @classmethod
    def of(cls, client: Any) -> OcrRoutes:
        """Return *client* as routes: routes pass through, a client is primary-only."""
        if isinstance(client, OcrRoutes):
            return client
        return cls(primary=client, fallback=None)

    @property
    def fingerprint(self) -> OcrWorkerFingerprint:
        """The primary route's fingerprint (the index identity's worker field)."""
        return _fingerprint_of(self.primary)

    @property
    def fallback_fingerprint(self) -> OcrWorkerFingerprint:
        """The fallback route's fingerprint."""
        return _fingerprint_of(self.fallback)

    def select(self) -> Any:
        """Return the client for the next dispatch, chosen BEFORE dispatch.

        Returns:
            The primary client when available, else the fallback client
            when available, else ``None``. When both are available and one
            holds a runtime lease, a :class:`RoutedClient`: a route that cannot
            start its runtime before dispatch passes the request on (design D10).
        """
        usable: list[Any] = []
        for client in (self.primary, self.fallback):
            if client is not None and _fingerprint_of(client).available and client not in usable:
                usable.append(client)
        if len(usable) > 1 and any(getattr(c, "lease", None) is not None for c in usable):
            return RoutedClient(usable)
        return usable[0] if usable else None

    def close(self) -> None:
        """Close every distinct route client."""
        closed: set[int] = set()
        for client in (self.primary, self.fallback):
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
    """Compose both route clients from injected settings.

    The probe runs only when the operator enabled OCR and the route
    resolved a command, so an unconfigured install spawns nothing.

    Args:
        settings: Settings carrying the OCR route fields.
        probe: The composition boundary's capability probe.
        runtime_manager: The process's runtime manager. A route whose engine
            declares a llama.cpp runtime is unavailable without one.

    Returns:
        The route pair. Construction starts no parsing process.
    """
    enabled = bool(getattr(settings, "ocr_fallback_enabled", False))
    primary_name = str(getattr(settings, "ocr_engine_primary", "") or "")
    fallback_name = str(getattr(settings, "ocr_engine_fallback", "") or "")
    primary_route = resolve_route_command(primary_name, settings, runtime_manager)
    primary = _client(
        primary_route, settings, probe=probe, enabled=enabled, runtime_manager=runtime_manager
    )
    fallback = None
    if fallback_name.strip():
        fallback_route = resolve_route_command(fallback_name, settings, runtime_manager)
        if fallback_route == primary_route:
            fallback = primary
        else:
            fallback = _client(
                fallback_route,
                settings,
                probe=probe,
                enabled=enabled,
                runtime_manager=runtime_manager,
            )
    routes = OcrRoutes(primary=primary, fallback=fallback)
    if enabled:
        _log_routes_once(primary_name, fallback_name, routes)
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


def _log_routes_once(primary_name: str, fallback_name: str, routes: OcrRoutes) -> None:
    """Log the resolved primary and fallback engines once per process."""
    primary_label = primary_name or "-"
    summary = (
        f"OCR routes: primary={primary_label} "
        f"[{'available' if routes.fingerprint.available else 'unavailable'}], "
        f"fallback={fallback_name or '-'} "
        f"[{'available' if routes.fallback_fingerprint.available else 'unavailable'}]"
    )
    if summary in _logged_summaries:
        return
    _logged_summaries.add(summary)
    logger.info(summary)


def log_route_plan(settings: Any) -> None:
    """Log the primary and fallback engines once, from the engine folders alone.

    The Engine-owned pool starts a worker on first use, so this start-up line
    starts no process and probes nothing: an engine is ``provisioned`` when its
    interpreter exists. Nothing is logged while OCR fallback is off.
    """
    if not getattr(settings, "ocr_fallback_enabled", False):
        return
    words = []
    for role, key in (("primary", "ocr_engine_primary"), ("fallback", "ocr_engine_fallback")):
        name = str(getattr(settings, key, "") or "").strip()
        state = (
            "provisioned" if resolve_route_command(name, settings).command else "not provisioned"
        )
        words.append(f"{role}={name or '-'} [{state}]")
    summary = "OCR routes: " + ", ".join(words)
    if not str(getattr(settings, "ocr_workers_dir", "") or "").strip():
        summary += " (OCR workers folder not set)"
    if summary in _logged_summaries:
        return
    _logged_summaries.add(summary)
    logger.info(summary)


def reset_route_log() -> None:
    """Forget which route summaries were logged (used by tests)."""
    _logged_summaries.clear()
