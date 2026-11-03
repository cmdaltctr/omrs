"""One dispatch over the ordered routes (design D3, D8, D10; ordered lists D6).

A route whose engine declares a llama.cpp runtime can be unavailable only when
the host tries to start it. The host learns that before it sends the request,
so the same request goes to the next route, and so on down the list. The
operator pressing Stop during a parse is the one failure after dispatch that
also moves the request, to the next route, once. The walk goes forward and
never back, so no request is sent to a route twice. A second operator stop in
the same walk ends it.
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
        """Hold the routes in order: the first engine of the list first.

        Args:
            routes: The available route clients, in list order.
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
        on, as often as it takes. A route whose runtime the operator stopped
        during the request also passes it on, but only once per request: a
        second stop, or any other failure after dispatch, is the file's error.
        The answer a route gives never moves the request, empty or not.

        Raises:
            OcrWorkerError: The last route failed, or a route failed after dispatch.
        """
        last = len(self._routes) - 1
        stop_retried = False
        for index, route in enumerate(self._routes):
            try:
                result = route.parse(pdf_path, pages=pages, timeout=timeout)
            except OcrWorkerError as exc:
                stopped = exc.code == RUNTIME_STOPPED_CODE
                if exc.code not in _MOVES_ON or index == last or (stopped and stop_retried):
                    raise
                stop_retried = stop_retried or stopped
                logger.info(
                    "OCR route %d did not take the request (%s); trying the next", index, exc.code
                )
                continue
            self._answered = route
            return result
        raise AssertionError("no route")  # pragma: no cover - the loop always returns or raises
