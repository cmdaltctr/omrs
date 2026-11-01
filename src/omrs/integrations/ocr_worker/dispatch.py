"""One dispatch over the primary and the fallback route (design D3, D8, D10).

A route whose engine declares a llama.cpp runtime can be unavailable only when
the host tries to start it. The host learns that before it sends the request,
so the same request goes to the fallback route. The operator pressing Stop
during a parse is the one failure after dispatch that also moves the request to
the fallback, once. The walk goes forward over the two routes and never back,
so no request is sent to a route twice.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from .client import OcrWorkerError
from .fingerprint import OcrWorkerFingerprint
from .managed import RUNTIME_STOPPED_CODE, UNAVAILABLE_CODE
from .protocol import ParseSuccess

logger = logging.getLogger(__name__)

_MOVES_ON = frozenset({UNAVAILABLE_CODE, RUNTIME_STOPPED_CODE})


class RoutedClient:
    """The routes of one dispatch, as one client.

    ``fingerprint`` is the fingerprint of the route that answered the last
    request, or of the first route before any answer. Make one per dispatch.
    """

    def __init__(self, routes: Sequence[Any]) -> None:
        """Hold the routes in order: primary first.

        Args:
            routes: The available route clients, primary first.
        """
        self._routes = list(routes)
        self._answered: Any = self._routes[0]

    @property
    def fingerprint(self) -> OcrWorkerFingerprint:
        """The fingerprint of the route that answered, else of the first route."""
        return self._answered.fingerprint

    def parse(
        self, pdf_path: str, *, pages: Sequence[int] | None = None, timeout: float | None = None
    ) -> ParseSuccess:
        """Send the request to the first route that takes it.

        A route that cannot start its runtime before dispatch passes the request
        on. So does a route whose runtime the operator stopped during the request.
        Any other failure after dispatch is the file's error.

        Raises:
            OcrWorkerError: The last route failed, or a route failed after dispatch.
        """
        last = len(self._routes) - 1
        for index, route in enumerate(self._routes):
            try:
                result = route.parse(pdf_path, pages=pages, timeout=timeout)
            except OcrWorkerError as exc:
                if exc.code not in _MOVES_ON or index == last:
                    raise
                logger.info(
                    "OCR route %d did not take the request (%s); trying the next", index, exc.code
                )
                continue
            self._answered = route
            return result
        raise AssertionError("no route")  # pragma: no cover - the loop always returns or raises
