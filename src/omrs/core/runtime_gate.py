"""An optional gate in front of the local llama.cpp router (one-llamacpp-router D6).

When OMRS manages the router, every llama.cpp request goes through a gate. The
gate joins the router first (it starts or adopts it), makes the request's model
ready, holds the model's request lock when the model is one-slot, and restarts
a crashed router once. The request's ``model`` field names the model.
``compose`` installs one resolver per process with :func:`install`; a llama.cpp
client in ``core/`` asks :func:`gate_for` when it builds its HTTP client. With
no resolver, or with an ``external`` router, the answer is ``None`` and the
client talks to its URL as before.

``core/`` never imports the runtime manager. ``compose`` adapts the router
lease to :class:`RuntimeGate` and turns its refusals into :class:`GateRefused`.

The HTTP transports below put the gate under an ``httpx`` client. A refusal
becomes a 424 answer with ``x-should-retry: false``. The OpenAI client and
llama_index retry a 5xx answer on their own, and each retry would try the
start again; they retry neither a 424 nor an answer with that header. A
streamed answer leaves the gate when its headers arrive.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Literal, Protocol, TypeVar

import httpx

T = TypeVar("T")

#: The client roles that can use a managed runtime.
Role = Literal["chat", "classification", "embeddings"]

#: The header that tells the OpenAI client not to retry an answer.
NO_RETRY_HEADER = "x-should-retry"
#: The status of a refusal: Failed Dependency, which no client layer retries.
REFUSED_STATUS = 424


class RuntimeGate(Protocol):
    """Holds the router and one model for one request (the router lease, adapted by ``compose``)."""

    def request(self, send: Callable[[str], T], model: str | None = None) -> T:
        """Run ``send(base_url)`` with the router and *model* held; raise :class:`GateRefused`."""
        ...

    async def arequest(self, send: Callable[[str], Awaitable[T]], model: str | None = None) -> T:
        """The async form of :meth:`request`."""
        ...


class GateRefused(RuntimeError):
    """The runtime cannot serve the request.

    Attributes:
        reason: One fixed reason word, for example ``timeout``.
        text: The plain-English line for the reason.
    """

    def __init__(self, reason: str, text: str) -> None:
        super().__init__(text)
        self.reason = reason
        self.text = text


Resolver = Callable[[Role], "RuntimeGate | None"]

_resolver: Resolver | None = None


def install(resolver: Resolver | None) -> None:
    """Install the process's gate resolver (``compose`` calls this); ``None`` removes it."""
    global _resolver
    _resolver = resolver


def gate_for(role: Role) -> RuntimeGate | None:
    """Return the gate of *role*, or ``None`` when the role talks to its URL directly."""
    return _resolver(role) if _resolver is not None else None


def request_model(request: httpx.Request) -> str | None:
    """Return the ``model`` field of a JSON request body, or ``None`` when it has none."""
    try:
        body = json.loads(request.content or b"{}")
    except (ValueError, httpx.RequestNotRead):
        return None
    model = body.get("model") if isinstance(body, dict) else None
    return model if isinstance(model, str) and model else None


def refusal_response(request: httpx.Request, refused: GateRefused) -> httpx.Response:
    """Return the answer that stands for a refusal; clients must not retry it."""
    error = {"message": refused.text, "type": "runtime_unavailable", "code": refused.reason}
    body = {"error": error}
    headers = {NO_RETRY_HEADER: "false"}
    return httpx.Response(REFUSED_STATUS, headers=headers, json=body, request=request)


class GatedTransport(httpx.BaseTransport):
    """An ``httpx`` transport that sends each request through a gate.

    Args:
        gate: The runtime gate.
        inner: The transport that sends the request; a plain HTTP transport by default.
    """

    def __init__(self, gate: RuntimeGate, inner: httpx.BaseTransport | None = None) -> None:
        self._gate = gate
        self._inner = inner if inner is not None else httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        """Send *request* with the runtime held."""
        try:
            return self._gate.request(
                lambda _base: self._inner.handle_request(request), request_model(request)
            )
        except GateRefused as refused:
            return refusal_response(request, refused)

    def close(self) -> None:
        """Close the inner transport."""
        self._inner.close()


class AsyncGatedTransport(httpx.AsyncBaseTransport):
    """The async form of :class:`GatedTransport`."""

    def __init__(self, gate: RuntimeGate, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self._gate = gate
        self._inner = inner if inner is not None else httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Send *request* with the runtime held."""

        async def send(_base: str) -> httpx.Response:
            return await self._inner.handle_async_request(request)

        try:
            return await self._gate.arequest(send, request_model(request))
        except GateRefused as refused:
            return refusal_response(request, refused)

    async def aclose(self) -> None:
        """Close the inner transport."""
        await self._inner.aclose()


def http_clients(role: Role) -> dict[str, httpx.Client | httpx.AsyncClient]:
    """Return ``http_client`` and ``async_http_client`` for an OpenAI-style client of *role*.

    Empty when the role has no gate, so the client keeps its default HTTP clients.
    """
    gate = gate_for(role)
    if gate is None:
        return {}
    return {
        "http_client": httpx.Client(transport=GatedTransport(gate)),
        "async_http_client": httpx.AsyncClient(transport=AsyncGatedTransport(gate)),
    }
