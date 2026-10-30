"""Local server probes for the ``runtime`` block (change integrations-show-runtime-components, D1).

Ollama answers ``GET /api/version``; a llama.cpp server answers
``GET /health`` at its address without ``/v1``. Each probe sends one
request with a 1 second timeout, and all probes run at the same time, so
the block arrives within about 1 second. An address is shown without any
user name or password.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from ...core.settings import classification_url
from .runtime_components import NOT_RUNNING, READY, UNCHECKED, UNKNOWN, RuntimeItem

logger = logging.getLogger(__name__)

PROBE_TIMEOUT = 1.0

OLLAMA_NAME = "Ollama"
LLAMACPP_EMBED_NAME = "llama.cpp embedding server"
LLAMACPP_CHAT_NAME = "llama.cpp chat server"
LLAMACPP_CLASSIFY_NAME = "llama.cpp classification server"

_PURPOSES = {
    OLLAMA_NAME: "Local embedding and chat models served by Ollama.",
    LLAMACPP_EMBED_NAME: "Local embedding model served by llama.cpp.",
    LLAMACPP_CHAT_NAME: "Local chat model served by llama.cpp.",
    LLAMACPP_CLASSIFY_NAME: "Local classification model served by llama.cpp.",
}


def safe_address(address: str) -> str:
    """Return *address* without a user name or password."""
    parts = urlsplit(address.strip())
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    netloc = f"{host}:{parts.port}" if parts.port else host
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _health_url(address: str) -> str:
    base = address.strip().rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return f"{base}/health"


def _backend(name: str, settings: Any) -> str:
    """Resolve a provider alias (``local``, ``cloud``, empty) to its backend name."""
    value = name.strip()
    if value == "local":
        return settings.local_backend
    if value in {"cloud", ""}:
        return settings.cloud_backend
    return value


def _users(settings: Any) -> dict[str, str]:
    """Return the backend each provider setting in force resolves to, by setting."""
    answer = getattr(settings, "answer", None)
    return {
        "embed_provider": _backend(settings.embed_provider, settings),
        "metadata_llm_provider": _backend(settings.metadata_llm_provider, settings),
        "answer.provider": _backend(getattr(answer, "provider", "") or "local", settings),
        "answer.verify_provider": _backend(getattr(answer, "verify_provider", ""), settings),
    }


def _servers(settings: Any) -> list[tuple[str, str, str, tuple[str, ...]]]:
    """Return ``(name, address, health URL, used_by)`` for every local server."""
    users = _users(settings)
    ollama = tuple(key for key, backend in users.items() if backend == "ollama")
    llama = [key for key, backend in users.items() if backend == "llamacpp"]
    embed = tuple(key for key in llama if key == "embed_provider")
    chat = tuple(key for key in llama if key != "embed_provider")
    classify_url = classification_url(settings)
    separate = _bare(classify_url) != _bare(settings.llamacpp_chat_url)
    if separate:  # the metadata user moves to its own item (ADR-108 D12)
        chat = tuple(key for key in chat if key != "metadata_llm_provider")
    ollama_url = settings.ollama_base_url.strip().rstrip("/")
    servers = [
        (OLLAMA_NAME, ollama_url, f"{ollama_url}/api/version", ollama),
        (
            LLAMACPP_EMBED_NAME,
            settings.llamacpp_embed_url,
            _health_url(settings.llamacpp_embed_url),
            embed,
        ),
        (
            LLAMACPP_CHAT_NAME,
            settings.llamacpp_chat_url,
            _health_url(settings.llamacpp_chat_url),
            chat,
        ),
    ]
    if separate:
        classify = tuple(key for key in llama if key == "metadata_llm_provider")
        servers.append((LLAMACPP_CLASSIFY_NAME, classify_url, _health_url(classify_url), classify))
    return servers


def _bare(address: str) -> str:
    return address.strip().rstrip("/")


async def _probe(
    client: httpx.AsyncClient, name: str, address: str, url: str, used_by: tuple[str, ...]
) -> RuntimeItem:
    purpose = _PURPOSES[name]
    shown = safe_address(address)
    try:
        response = await client.get(url)
    except httpx.HTTPError:
        reason = f"No server answers at {shown}."
        return RuntimeItem(name, purpose, NOT_RUNNING, reason, None, used_by)
    except Exception:
        return RuntimeItem(name, purpose, UNKNOWN, UNCHECKED, None, used_by)
    if response.status_code == 200:
        return RuntimeItem(name, purpose, READY, None, None, used_by)
    reason = f"The server at {shown} answered {response.status_code}."
    return RuntimeItem(name, purpose, NOT_RUNNING, reason, None, used_by)


async def local_server_items(settings: Any) -> list[RuntimeItem]:
    """Probe Ollama and the llama.cpp addresses at the same time.

    A failure outside one request (the client itself) gives ``unknown`` for
    every server, never an error response.
    """
    servers = _servers(settings)
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT, follow_redirects=False) as client:
            return list(await asyncio.gather(*(_probe(client, *server) for server in servers)))
    except Exception:
        logger.warning("Local server probes failed.", exc_info=True)
        return [
            RuntimeItem(name, _PURPOSES[name], UNKNOWN, UNCHECKED, None, used_by)
            for name, _, _, used_by in servers
        ]


# ── Provider readiness on two catalogue cards (design D2) ────────────────

LLAMACPP_NAMES = (LLAMACPP_EMBED_NAME, LLAMACPP_CHAT_NAME, LLAMACPP_CLASSIFY_NAME)


def llamacpp_readiness(items: list[RuntimeItem], settings: Any) -> dict[str, Any]:
    """Return the llama.cpp card's readiness from its server items.

    The addresses that a setting uses decide. When no setting uses llama.cpp,
    every llama.cpp address decides, so a module check alone never says "Ready".
    """
    addresses = {
        LLAMACPP_EMBED_NAME: settings.llamacpp_embed_url,
        LLAMACPP_CHAT_NAME: settings.llamacpp_chat_url,
        LLAMACPP_CLASSIFY_NAME: classification_url(settings),
    }
    servers = [item for item in items if item.name in LLAMACPP_NAMES]
    relevant = [item for item in servers if item.used_by] or servers
    down = next((item for item in relevant if item.status != READY), None)
    if down is None:
        return {"ready": True, "line": "Ready"}
    return {"ready": False, "line": f"Not running at {safe_address(addresses[down.name])}"}


def openrouter_readiness(settings: Any) -> dict[str, Any]:
    """Return the OpenRouter card's readiness: a key reference is set. The key is not resolved."""
    if str(getattr(settings, "openrouter_api_key", "") or "").strip():
        return {"ready": True, "line": "Ready"}
    return {"ready": False, "line": "No key set"}
