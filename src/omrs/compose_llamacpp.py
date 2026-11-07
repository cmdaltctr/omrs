"""Settings view of the llama.cpp server that ``omrs web`` manages (design D12, ADR-108).

A pure function over resolved ``Settings`` and the saved values. It gives the
program and the router mode with their source and lock, laid out like a provider
card field, plus the router address, the Chat model in force and whether Chat
shares the classification model (one-llamacpp-router D14).
``compose.llamacpp_server_settings`` is the thin entry that reads the settings;
this module sits beside ``compose.py`` because that file is near the 500-line
ceiling.
"""

from __future__ import annotations

from typing import Any

from .compose_connections import _plain_field
from .compose_providers import ProviderValues, apply_provider_values, locked_fields
from .config import Settings
from .core.providers.llm.llamacpp_rules import LLAMACPP_SERVER_FIELDS
from .integrations.llamacpp_runtime.rules import model_kind

#: Key of each field in the view (``binary``, ``router_server``).
VIEW_KEYS = {
    "server_binary": "binary",
    "router_server": "router_server",
}


def build_llamacpp_server_view(
    settings: Settings, values: ProviderValues | None = None
) -> dict[str, Any]:
    """Return the two server settings, each with value, source and lock, and the Chat model.

    Args:
        settings: Settings as the environment and ``.env`` resolved them.
        values: Saved values from the web workspace, or ``None`` for none.

    Returns:
        ``{"router_url": str, "binary": field, "router_server": field,
        "chat_model": {"provider", "model", "usable"},
        "launch_model": str, "shared_with_classification": bool}``. A field holds
        ``id``, ``label``, ``kind``, ``value``, ``min``, ``max``, ``source`` (``env``,
        ``dotenv``, ``config-file`` or ``default``), ``locked`` and ``lock_reason``.
        ``launch_model`` is the model a launch uses: the Chat model while the Chat
        provider is ``llamacpp``, else ``""`` (so Start fails with ``not-configured``).
    """
    values = values or ProviderValues()
    applied = apply_provider_values(settings, values)
    locks = locked_fields(applied, applied.provider_explicit)
    view: dict[str, Any] = {"router_url": applied.llamacpp_router_url}
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
    # Chat on the classification model shares its slots and context size (D14).
    text_model = applied.llamacpp_chat_model.strip()
    view["shared_with_classification"] = (
        llamacpp and bool(text_model) and model.strip() == text_model
    )
    return view
