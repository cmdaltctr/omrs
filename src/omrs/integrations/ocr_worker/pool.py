"""The Engine-scoped OCR client pool (design D5 of integrations-show-runtime-components).

A Read document step can name its own OCR engines. The pool keeps one lazy
:class:`ManagedOcrClient` per resolved :class:`RouteCommand`, so two nodes
that use the same engine share one worker, and a node that inherits the host
engine shares the host client. A worker starts only on its first dispatch.

One pool-wide lock is held around each parse dispatch. Two engines then
never parse at the same time, so they never hold peak memory together. An
idle engine stays loaded: a worker has no idle exit and stops only when
the pool closes or the worker fails.

The Engine owns the pool and closes it in ``Engine.close()``. ``core/``
sees only the ``ocr`` resource: it calls :meth:`OcrClientPool.routes` with
the effective settings of a node.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from .fingerprint import OcrWorkerFingerprint
from .managed import ManagedOcrClient
from .routes import OcrRoutes, RouteCommand, resolve_route_command


class OcrClientPool:
    """One lazy OCR worker client per route command, shared by every node.

    Construction starts nothing and probes nothing.
    """

    def __init__(self, *, probe: Callable[[list[str]], OcrWorkerFingerprint]) -> None:
        """Hold the capability probe; build no client.

        Args:
            probe: The composition boundary's capability probe. It runs once
                per route command, when the pool builds that command's client.
        """
        self._probe = probe
        self._clients: dict[RouteCommand, ManagedOcrClient] = {}
        self._lock = threading.Lock()
        self._dispatch_lock = threading.Lock()
        self._closed = False

    def routes(self, settings: Any) -> OcrRoutes:
        """Return the primary and fallback routes of *settings*.

        Args:
            settings: The effective settings of a node or of the host.

        Returns:
            The route pair. With the OCR fallback off, or a route that
            resolves no command, that route is ``None``: it reports the
            unavailable fingerprint, as an unprobed client does.

        Raises:
            RuntimeError: When the pool is closed.
        """
        if not getattr(settings, "ocr_fallback_enabled", False):
            return OcrRoutes()
        primary_name = str(getattr(settings, "ocr_engine_primary", "") or "")
        fallback_name = str(getattr(settings, "ocr_engine_fallback", "") or "")
        primary = self._client(resolve_route_command(primary_name, settings), settings)
        fallback = None
        if fallback_name.strip():
            route = resolve_route_command(fallback_name, settings)
            fallback = self._client(route, settings)
        return OcrRoutes(primary=primary, fallback=fallback)

    def close(self) -> None:
        """Close every client the pool built. Idempotent."""
        with self._lock:
            self._closed = True
            clients, self._clients = list(self._clients.values()), {}
        for client in clients:
            client.close()

    def _client(self, route: RouteCommand, settings: Any) -> ManagedOcrClient | None:
        """Return the shared client of *route*; build and probe it on first use."""
        if not route.command:
            return None
        with self._lock:
            if self._closed:
                raise RuntimeError("OcrClientPool is closed; construct a new pool.")
            client = self._clients.get(route)
            if client is None:
                client = ManagedOcrClient(
                    fingerprint=self._probe(list(route.command)),
                    command=list(route.command),
                    request_timeout=settings.ocr_worker_request_timeout,
                    cwd=route.cwd,
                    dispatch_lock=self._dispatch_lock,
                )
                self._clients[route] = client
            return client
