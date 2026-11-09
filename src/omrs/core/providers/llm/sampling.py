"""Temperature, seed and host pinning shared by the Chat providers (pre-exp35 D2, D3, D11).

Each provider module chooses its own mapping: it binds ``sampling_kwargs``
(constructor keywords for a set temperature and seed) and, when it can pin
hosts, a module-level ``HOST_PIN``. The registry looks both up by attribute,
so dispatch never branches on provider names. An empty value maps to nothing,
so the request stays as it was (LlamaIndex's ``temperature: 0.1`` on the
OpenAI-like classes).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

#: The sampling values a settings read may list as ignored, in display order.
SAMPLING_NAMES: tuple[str, ...] = ("temperature", "seed", "allowed_hosts")

#: Reads one JSON document: ``fetch(url, headers) -> parsed JSON``. Injected so tests fake it.
FetchJson = Callable[[str, Mapping[str, str]], Any]

#: The host part of a sampling record when the provider names no host.
NO_HOST: dict[str, Any] = {"host": None, "accepted": None, "host_in_list": None}


class HostRefused(RuntimeError):
    """No allowed host takes every value the request sets, so no call was made.

    The message names the model, the allowed hosts and the missing values.
    It never holds a key or a reply.
    """


@dataclass(frozen=True)
class HostPin:
    """What a provider that limits its calls to listed hosts supplies.

    Attributes:
        check: ``check(settings, llm, hosts, fetch)`` raises :class:`HostRefused`
            when no host in *hosts* supports every value *llm* sends. It runs
            once per role before the first call; *fetch* reads the endpoint list.
        record: ``record(llm, raw)`` returns ``host``, ``accepted`` and
            ``host_in_list`` for one raw reply. It never raises and never fetches.
    """

    check: Callable[[Any, Any, tuple[str, ...], FetchJson | None], None]
    record: Callable[[Any, Any], dict[str, Any]]


def constructor_kwargs(temperature: float | None, seed: int | None) -> dict[str, Any] | None:
    """Return LlamaIndex constructor keywords for a set temperature and seed, or ``None``.

    The temperature is a constructor field. The seed goes in
    ``additional_kwargs``: the OpenAI-like classes put it at the top of the
    request body, and ``Ollama`` puts it in ``options``, where each server
    reads it.
    """
    found: dict[str, Any] = {}
    if temperature is not None:
        found["temperature"] = temperature
    if seed is not None:
        found["additional_kwargs"] = {"seed": seed}
    return found or None


def merge_kwargs(*parts: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge constructor keyword dicts. ``additional_kwargs`` and its ``extra_body`` merge too."""
    merged: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    body: dict[str, Any] = {}
    for part in parts:
        for key, value in (part or {}).items():
            if key != "additional_kwargs":
                merged[key] = value
                continue
            for name, item in value.items():
                if name == "extra_body":
                    body.update(item)
                else:
                    extra[name] = item
    if body:
        extra["extra_body"] = body
    if extra:
        merged["additional_kwargs"] = extra
    return merged


def split_hosts(text: str) -> tuple[str, ...]:
    """Return the hosts of a comma-separated list, blank entries dropped."""
    return tuple(part.strip() for part in str(text or "").split(",") if part.strip())


def sent_values(llm: Any) -> tuple[float | None, int | None]:
    """Return the temperature and seed a built LLM puts on its requests.

    Read from the object, never re-derived from settings, so a library
    default shows. ``None`` means the request carries no such field.
    """
    temperature = getattr(llm, "temperature", None)
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
        temperature = None
    extra = getattr(llm, "additional_kwargs", None)
    seed = extra.get("seed") if isinstance(extra, dict) else None
    if isinstance(seed, bool) or not isinstance(seed, int):
        seed = None
    return (None if temperature is None else float(temperature)), seed
