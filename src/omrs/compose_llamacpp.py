"""Settings view of the llama.cpp server that ``omrs web`` manages (design D12, ADR-108).

A pure function over resolved ``Settings`` and the saved values. It gives the
program, the Chat server choice, the context window and the idle sleep with
their source and lock, laid out like a provider card field, plus the chat
address the server listens on, the Chat model in force (which the server loads)
and whether classification shares the owned server.
``compose.llamacpp_server_settings`` is the thin entry that reads the settings;
this module sits beside ``compose.py`` because that file is near the 500-line
ceiling.
"""

from __future__ import annotations

from typing import Any

from .compose_connections import _plain_field
from .compose_providers import ProviderValues, apply_provider_values, locked_fields
from .config import Settings
from .core.providers.llm.llamacpp_rules import LLAMACPP_SERVER_FIELDS, model_kind
from .core.settings import classification_url

#: Key of each field in the view (``binary``, ``chat_server``, ``context_window``, ``idle_sleep``).
VIEW_KEYS = {
    "server_binary": "binary",
    "chat_server": "chat_server",
    "context_window": "context_window",
    "idle_sleep": "idle_sleep",
}


def build_llamacpp_server_view(
    settings: Settings, values: ProviderValues | None = None
) -> dict[str, Any]:
    """Return the four server settings, each with value, source and lock, and the Chat model.

    Args:
        settings: Settings as the environment and ``.env`` resolved them.
        values: Saved values from the web workspace, or ``None`` for none.

    Returns:
        ``{"chat_url": str, "binary": field, "chat_server": field, "context_window":
        field, "idle_sleep": field, "chat_model": {"provider", "model", "usable"},
        "launch_model": str, "shared_with_classification": bool}``. A field holds
        ``id``, ``label``, ``kind``, ``value``, ``min``, ``max``, ``source`` (``env``,
        ``dotenv``, ``config-file`` or ``default``), ``locked`` and ``lock_reason``.
        ``launch_model`` is the model a launch uses: the Chat model while the Chat
        provider is ``llamacpp``, else ``""`` (so Start fails with ``not-configured``).
    """
    values = values or ProviderValues()
    applied = apply_provider_values(settings, values)
    locks = locked_fields(applied, applied.provider_explicit)
    view: dict[str, Any] = {"chat_url": applied.llamacpp_chat_url}
    for spec in LLAMACPP_SERVER_FIELDS:
        entry = _plain_field(spec, applied, values, locks)
        view[VIEW_KEYS[spec.id]] = {
            key: entry[key]
            for key in (
                "id",
                "label",
                "kind",
                "value",
                "min",
                "max",
                "source",
                "locked",
                "lock_reason",
            )
        }
    provider, model = applied.answer.provider.strip(), applied.answer.model
    llamacpp = provider == "llamacpp"
    view["chat_model"] = {
        "provider": provider,
        "model": model,
        "usable": llamacpp and model_kind(model) is not None,
    }
    view["launch_model"] = model if llamacpp else ""
    shared = _same_address(classification_url(applied), applied.llamacpp_chat_url)
    view["shared_with_classification"] = view["chat_server"]["value"] == "managed" and shared
    return view


def _same_address(first: str, second: str) -> bool:
    """Return whether two addresses are equal once a trailing ``/`` is removed."""
    return first.strip().rstrip("/") == second.strip().rstrip("/")
