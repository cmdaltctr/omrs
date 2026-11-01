"""Build the llama.cpp runtime of an OCR route (change managed-llamacpp-runtimes, D10).

The engine declares the runtime in its manifest (see ``manifest.py``). The
host turns that declaration into a :class:`RuntimeSpec` and asks the shared
runtime manager for a lease. The host uses the engine folder name as data and
never reads which engine it is.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from ..llamacpp_runtime.spec import DeclaredFile, RuntimeSpec, ocr_spec

if TYPE_CHECKING:
    from ..llamacpp_runtime.lease import RuntimeLease
    from ..llamacpp_runtime.manager import RuntimeManager
    from .manifest import DeclaredRuntime
    from .routes import RouteCommand

#: The environment variable that tells a worker where its runtime listens.
RUNTIME_URL_ENV = "OMRS_OCR_RUNTIME_URL"


def runtime_spec(route: RouteCommand, declared: DeclaredRuntime) -> RuntimeSpec:
    """Return the runtime a route's engine declared.

    The runtime id uses the engine folder name, which is the name of the
    route's working directory. A route with a ``runtime_url`` is external: the
    manager checks the build at that address and starts nothing.

    Args:
        route: The route of the engine.
        declared: The engine's checked declaration.
    """
    spec = ocr_spec(
        engine_folder=Path(route.cwd or "").name,
        binary=str(declared.program),
        build=declared.build,
        flags=declared.flags,
        files=[DeclaredFile(f.flag, str(f.path), f.sha256) for f in declared.files],
    )
    if route.runtime_url:
        return replace(spec, mode="external", url_base=route.runtime_url)
    return spec


def runtime_lease(route: RouteCommand, manager: RuntimeManager | None) -> RuntimeLease | None:
    """Return the lease of a route's runtime, or ``None`` when it declares none.

    Getting a lease joins nothing and starts nothing.
    """
    if route.runtime is None or manager is None:
        return None
    return manager.lease(runtime_spec(route, route.runtime))
