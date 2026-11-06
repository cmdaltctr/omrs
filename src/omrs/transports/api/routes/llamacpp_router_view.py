"""What the router routes read and how they shape it (one-llamacpp-router, D2, D3, D15).

:func:`load_router` gathers the saved values in force: the settings with the
saved provider values applied, ``omrs.jsonc`` as it is now (the model list and
the managed decision models come from the file, so a list saved a moment ago is
seen at once), and the roles that the role settings give each entry.
:func:`status_body` turns that and a :class:`~..llamacpp_server.RouterStatus`
into the body of ``GET /v1/llamacpp/router``.

Nothing here starts a process or writes a file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from ....compose_answer import resolve_verify_provider
from ....compose_providers import locked_fields, provider_settings
from ....config import Settings
from ....config.llamacpp_roles import RoleReport, derive_roles
from ....config.settings_file import SettingsFile
from ....config.settings_maps import DECISION_MODELS
from ....config.user_config import INT_KEY_BOUNDS
from ....core.providers.llm.connection import ConnectionField
from ..llamacpp_chat_rule import model_list
from ..llamacpp_server import RouterConfig, RouterStatus, program_in_force
from .chat_settings import provider_values_of

#: ``(key in the body, Settings field, label, kind)``, in the order the status lists them.
SAVED_FIELDS = (
    ("binary", "llamacpp_server_binary", "Program path", "text"),
    ("router_server", "llamacpp_router_server", "Who runs the llama.cpp router", "choice"),
    ("router_url", "llamacpp_router_url", "Router address", "url"),
    ("models_max", "llamacpp_router_models_max", "Models loaded at once", "int"),
    ("memory_margin_mib", "llamacpp_router_memory_margin_mib", "Free memory margin (MiB)", "int"),
)
#: The ``Settings`` field that each body key writes.
FIELD_IDS = {key: path for key, path, _, _ in SAVED_FIELDS}


def _int_spec(key: str, path: str, label: str) -> ConnectionField:
    low, high = INT_KEY_BOUNDS[path]
    return ConnectionField(key, label, "int", path, path.upper(), minimum=low, maximum=high)


#: The whole-number fields as connection fields, for the shared range check.
INT_SPECS = {
    key: _int_spec(key, path, label) for key, path, label, kind in SAVED_FIELDS if kind == "int"
}
_WORDS = {"yaml": "default", "init": "default"}


@dataclass(frozen=True)
class LoadedRouter:
    """The saved values in force and the file they were read with.

    Attributes:
        settings: ``Settings`` with the saved provider values applied.
        file: ``omrs.jsonc`` as read now.
        config: The router values a start or a status read uses.
        roles: The roles of each list entry and the roles that no entry can serve.
    """

    settings: Settings
    file: SettingsFile
    config: RouterConfig
    roles: RoleReport


def role_arguments(settings: Settings, file: SettingsFile) -> dict[str, Any]:
    """Return the ``derive_roles`` keywords that the role settings in force give.

    Chat counts while ``answer.provider`` is ``llamacpp`` and the judge while its
    provider resolves to ``llamacpp``; a blank model gives no role. A managed
    ``llamacpp`` decision entry of the file names its list entry by ``model``.
    """
    answer = settings.answer
    judge_on = resolve_verify_provider(settings, answer.verify_provider) == "llamacpp"
    decisions = file.maps.get(DECISION_MODELS, {}).values()
    return {
        "embed_model": settings.llamacpp_embed_model.strip(),
        "classify_model": settings.llamacpp_chat_model.strip(),
        "chat_model": answer.model.strip() if answer.provider.strip() == "llamacpp" else "",
        "judge_model": answer.verify_model.strip() if judge_on else "",
        "decision_models": [
            entry.model
            for entry in decisions
            if entry.kind == "llamacpp" and entry.server == "managed"
        ],
    }


def load_router(runtime: Any, store: Any) -> LoadedRouter:
    """Read the saved values in force. Blocks on the file, so call it in a thread.

    Args:
        runtime: The ``WebRuntime`` (its provider values), or a stand-in.
        store: The ``omrs.jsonc`` store.
    """
    settings = provider_settings(provider_values_of(runtime))
    file = store.read()
    entries = model_list(file)
    arguments = role_arguments(settings, file)
    config = RouterConfig(
        mode=settings.llamacpp_router_server,
        binary=settings.llamacpp_server_binary,
        url=settings.llamacpp_router_url,
        models_max=settings.llamacpp_router_models_max,
        memory_margin_mib=settings.llamacpp_router_memory_margin_mib,
        entries=entries,
        decision_models=tuple(arguments["decision_models"]),
    )
    return LoadedRouter(settings, file, config, derive_roles(entries, **arguments))


# ── The status body ─────────────────────────────────────────────────────


def _field(settings: Settings, locks: dict[str, str], path: str, label: str, kind: str) -> dict:
    """Return one saved value with its source, default and lock."""
    locked = locks.get(path) == "environment"
    word = settings.setting_sources.get(path, "default")
    if locked:
        source = word if word in ("env", "dotenv") else "env"
    else:
        source = word if word == "config-file" else _WORDS.get(word, "default")
    bounds = INT_KEY_BOUNDS.get(path)
    return {
        "id": path,
        "label": label,
        "kind": kind,
        "value": getattr(settings, path),
        "default": Settings.model_fields[path].default,
        "min": bounds[0] if bounds else None,
        "max": bounds[1] if bounds else None,
        "source": source,
        "locked": locked,
        "lock_reason": (
            f"Remove {path.upper()} from the environment or .env to edit it here."
            if locked
            else None
        ),
    }


def _address(url: str) -> str | None:
    """Return ``host:port`` of the router address, with no user name and no path."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if not parts.hostname:
        return None
    return f"{parts.hostname}:{port or (443 if parts.scheme == 'https' else 80)}"


def _model_items(loaded: LoadedRouter, status: RouterStatus) -> list[dict[str, Any]]:
    items = []
    for entry_id, entry in loaded.config.entries.items():
        state = status.models.get(entry.model)
        ctx = entry.preset.get("ctx-size")
        items.append(
            {
                "id": entry_id,
                "model": entry.model,
                "roles": list(loaded.roles.roles.get(entry_id, ())),
                "file": entry.file or None,
                "projector": entry.projector or None,
                "ctx_size": ctx if isinstance(ctx, int) else None,
                "preset": dict(entry.preset),
                "state": state.state if state else "unloaded",
                "reason": state.reason if state else None,
                "reason_text": state.reason_text if state else None,
                "note": state.note if state else None,
                "reload_pending": state.reload_pending if state else False,
            }
        )
    return items


def saved_fields(settings: Settings) -> dict[str, dict[str, Any]]:
    """Return the five saved settings by body key, each with source, default and lock."""
    locks = locked_fields(settings, settings.provider_explicit)
    return {
        key: _field(settings, locks, path, label, kind) for key, path, label, kind in SAVED_FIELDS
    }


def status_body(loaded: LoadedRouter, status: RouterStatus) -> dict[str, Any]:
    """Return the body of ``GET /v1/llamacpp/router`` (without ``status``)."""
    return {
        "revision": loaded.file.revision,
        "state": status.state,
        "reason": status.reason,
        "reason_text": status.reason_text,
        "mode": loaded.config.mode,
        "address": _address(loaded.config.url),
        "running_with": status.running_with,
        "pending_restart": status.pending_restart,
        "program": status.program or program_in_force(loaded.config.binary),
        "saved": saved_fields(loaded.settings),
        "models": _model_items(loaded, status),
    }
