"""Streamed Ollama model pull (add-model-search-and-download D6).

One ``POST {base}/api/pull`` with ``{"model": name, "stream": true}``. The
reply is JSON lines. Progress is the sum of ``completed`` over the ``total``
of each layer ``digest``. The status ``success`` ends the pull. An ``error``
line fails it.

This module is a leaf: it imports no ``omrs.core`` and no ``omrs.transports``
module. It runs in a worker thread, so it uses the synchronous ``httpx``
client. No exception text or server message reaches an error, so a path or a
token cannot leak through this code.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable

import httpx

#: Seconds to open a connection.
CONNECT_TIMEOUT_SECONDS = 10.0
#: Seconds to wait for the next line. Ollama can stay quiet while it checks a layer.
READ_TIMEOUT_SECONDS = 60.0


class OllamaPullError(Exception):
    """The pull failed.

    Attributes:
        reason: ``failed`` or ``ollama-unreachable``.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class PullCancelled(Exception):
    """The cancel event was set; the stream is closed."""


def _progress(layers: dict[str, tuple[int, int]]) -> tuple[int, int | None]:
    """Return ``(bytes done, bytes total)`` summed over all layers."""
    done = sum(completed for completed, _ in layers.values())
    total = sum(size for _, size in layers.values())
    return done, total or None


def _read_stream(
    response: httpx.Response,
    on_progress: Callable[[int, int | None], None],
    cancel: threading.Event,
) -> None:
    """Read the JSON lines of *response* until ``success``.

    Raises:
        PullCancelled: *cancel* was set.
        OllamaPullError: ``failed`` for an ``error`` line, a bad line or a
            stream that ends before ``success``.
    """
    layers: dict[str, tuple[int, int]] = {}
    for line in response.iter_lines():
        if cancel.is_set():
            raise PullCancelled
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            raise OllamaPullError("failed") from None
        if not isinstance(record, dict) or "error" in record:
            raise OllamaPullError("failed")
        if record.get("status") == "success":
            return
        digest, total = record.get("digest"), record.get("total")
        if isinstance(digest, str) and isinstance(total, int):
            completed = record.get("completed")
            layers[digest] = (completed if isinstance(completed, int) else 0, total)
            on_progress(*_progress(layers))
            if cancel.is_set():
                raise PullCancelled
    raise OllamaPullError("failed")


def pull_model(
    base_url: str,
    name: str,
    *,
    on_progress: Callable[[int, int | None], None],
    cancel: threading.Event,
    client: httpx.Client | None = None,
) -> None:
    """Pull *name* through Ollama and block until the pull ends.

    Args:
        base_url: The Ollama address, for example ``http://127.0.0.1:11434``.
        name: The model name. The route has already checked it.
        on_progress: Called with ``(bytes done, bytes total or None)`` after
            each layer line.
        cancel: When set, the stream closes and the call raises
            :class:`PullCancelled`. Ollama keeps its partial layers.
        client: An ``httpx`` client, for tests. A default client is built
            and closed when it is ``None``.

    Raises:
        PullCancelled: The cancel event was set.
        OllamaPullError: ``ollama-unreachable`` when the connection fails;
            ``failed`` for an error line, an HTTP error or a broken stream.
    """
    if cancel.is_set():
        raise PullCancelled
    url = f"{base_url.rstrip('/')}/api/pull"
    timeout = httpx.Timeout(READ_TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS)
    own = client if client is not None else httpx.Client(follow_redirects=False)
    try:
        with own.stream(
            "POST",
            url,
            json={"model": name, "stream": True},
            timeout=timeout,
            follow_redirects=False,
        ) as response:
            if response.status_code != 200:
                raise OllamaPullError("failed")
            _read_stream(response, on_progress, cancel)
    except (OllamaPullError, PullCancelled):
        raise
    except (httpx.ConnectError, httpx.ConnectTimeout):
        raise OllamaPullError("ollama-unreachable") from None
    except Exception:  # noqa: BLE001 - the text may hold the address; report only the reason
        raise OllamaPullError("failed") from None
    finally:
        if client is None:
            own.close()
