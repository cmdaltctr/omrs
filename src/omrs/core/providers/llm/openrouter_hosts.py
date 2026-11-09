"""OpenRouter host pinning: the endpoint check and the host record (pre-exp35 D11).

With ``answer.allowed_hosts`` (or ``answer.verify_allowed_hosts``) set, the
request carries ``provider: {only, allow_fallbacks: false,
require_parameters: true}``. Before the first call of a role, OMRS reads the
model's public endpoint list (``GET /models/{author}/{slug}/endpoints``, each
entry with ``provider_name``, ``tag`` and ``supported_parameters``) and refuses
when no listed host supports every value the request sets. A list of an
unexpected shape, or one that cannot be read, counts as "support unknown" and
refuses too. A parsed list stays in process memory; a failed read is not kept.

A host matches an endpoint by provider name (any case) or by slug, as
OpenRouter matches ``only``: the slug ``deepinfra`` matches ``deepinfra/fp8``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from .sampling import NO_HOST, FetchJson, HostPin, HostRefused, sent_values

logger = logging.getLogger(__name__)

_API_BASE = "https://openrouter.ai/api/v1"
_FETCH_TIMEOUT_SECONDS = 10.0
_VALUES = ("temperature", "seed")

#: One endpoint: ``(provider name, slug, supported parameters)``, names in lower case.
_Endpoint = tuple[str, str, frozenset[str]]
#: Model id -> its endpoints, for lists read in this process.
_cache: dict[str, tuple[_Endpoint, ...]] = {}


def clear_cache() -> None:
    """Forget every endpoint list (tests, and nothing else, call this)."""
    _cache.clear()


def fetch_json(url: str, headers: Mapping[str, str]) -> Any:
    """Read *url* and return its JSON. The default endpoint-list read."""
    import httpx

    response = httpx.get(url, headers=dict(headers), timeout=_FETCH_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def parse_endpoints(payload: Any) -> tuple[_Endpoint, ...] | None:
    """Return the endpoints in *payload*, or ``None`` when its shape is not the documented one."""
    data = payload.get("data") if isinstance(payload, dict) else None
    entries = data.get("endpoints") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return None
    found: list[_Endpoint] = []
    for entry in entries:
        name = entry.get("provider_name") if isinstance(entry, dict) else None
        params = entry.get("supported_parameters") if isinstance(entry, dict) else None
        if not isinstance(name, str) or not isinstance(params, list):
            return None
        tag = entry.get("tag")
        found.append(
            (
                name.strip().lower(),
                tag.strip().lower() if isinstance(tag, str) else "",
                frozenset(p for p in params if isinstance(p, str)),
            )
        )
    return tuple(found)


def _endpoints(settings: Any, model: str, fetch: FetchJson | None) -> tuple[_Endpoint, ...] | None:
    if model in _cache:
        return _cache[model]
    key = str(getattr(settings, "openrouter_api_key", "") or "").strip()
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        parsed = parse_endpoints(
            (fetch or fetch_json)(f"{_API_BASE}/models/{model}/endpoints", headers)
        )
    except Exception as exc:  # noqa: BLE001 - any failure means "support unknown"
        logger.warning("Could not read the OpenRouter endpoint list: %s", type(exc).__name__)
        return None
    if parsed is not None:
        _cache[model] = parsed
    return parsed


def _matches(host: str, endpoint: _Endpoint) -> bool:
    wanted = host.strip().lower()
    name, slug, _ = endpoint
    return wanted in (name, slug) or (bool(slug) and slug.startswith(f"{wanted}/"))


def _needed(llm: Any) -> tuple[str, ...]:
    temperature, seed = sent_values(llm)
    return tuple(n for n, v in zip(_VALUES, (temperature, seed), strict=True) if v is not None)


def check_hosts(settings: Any, llm: Any, hosts: tuple[str, ...], fetch: FetchJson | None) -> None:
    """Refuse when no host in *hosts* has an endpoint that takes every value *llm* sends.

    Raises:
        HostRefused: The message names the model, the hosts and the missing
            values, or says that support is unknown.
    """
    model = str(getattr(llm, "model", "") or "")
    listed = ", ".join(hosts)
    endpoints = _endpoints(settings, model, fetch)
    if endpoints is None:
        raise HostRefused(
            f"OpenRouter host support for {model} is unknown: the endpoint list could not be "
            f"read or had an unexpected shape. No call was made. Allowed hosts: {listed}."
        )
    needed = _needed(llm)
    mine = [e for e in endpoints if any(_matches(h, e) for h in hosts)]
    if any(set(needed) <= e[2] for e in mine):
        return
    if not mine:
        raise HostRefused(f"OpenRouter does not serve {model} on any allowed host: {listed}.")
    missing = [n for n in needed if not any(n in e[2] for e in mine)] or list(needed)
    raise HostRefused(
        f"No allowed OpenRouter host for {model} takes {' and '.join(missing)}: {listed}. "
        "No call was made."
    )


def _only(llm: Any) -> list[str] | None:
    extra = getattr(llm, "additional_kwargs", None)
    body = extra.get("extra_body") if isinstance(extra, dict) else None
    routing = body.get("provider") if isinstance(body, dict) else None
    only = routing.get("only") if isinstance(routing, dict) else None
    return [str(h) for h in only] if isinstance(only, list) else None


def record_host(llm: Any, raw: Any) -> dict[str, Any]:
    """Return the host that served *raw*, its published support and whether it is in the list."""
    try:
        name = raw.get("provider") if isinstance(raw, dict) else getattr(raw, "provider", None)
    except Exception:  # noqa: BLE001 - a record must never raise
        name = None
    if not isinstance(name, str) or not name.strip():
        return dict(NO_HOST)
    only = _only(llm)
    if only is None:
        return {**NO_HOST, "host": name}
    served = [
        e for e in _cache.get(str(getattr(llm, "model", "")), ()) if e[0] == name.strip().lower()
    ]
    in_list = any(_matches(h, e) for h in only for e in served) or name.strip().lower() in {
        h.strip().lower() for h in only
    }
    params = frozenset().union(*(e[2] for e in served)) if served else None
    accepted = None if params is None else {v: v in params for v in _VALUES}
    return {"host": name, "accepted": accepted, "host_in_list": in_list}


def routing_kwargs(allowed_hosts: tuple[str, ...]) -> dict[str, Any] | None:
    """Return the ``provider`` routing field for *allowed_hosts*, or ``None`` for an empty list."""
    if not allowed_hosts:
        return None
    routing = {"only": list(allowed_hosts), "allow_fallbacks": False, "require_parameters": True}
    return {"additional_kwargs": {"extra_body": {"provider": routing}}}


#: The OpenRouter module binds this as its ``HOST_PIN``.
PIN = HostPin(check=check_hosts, record=record_host)
