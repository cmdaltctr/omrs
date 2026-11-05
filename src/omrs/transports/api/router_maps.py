"""Bodies and checks of the decision model and router routes (ADR-110, task 4.1).

``GET /v1/settings/decision-models`` and ``GET /v1/settings/document-routers``
show the valid ``decision_models`` and ``document_routers`` entries that
``omrs.jsonc`` holds now. Neither body holds a key: a decision model shows only
its key state. Nothing here contacts a model.

The profile walk finds the saved user profiles whose Read document step names a
router, so a delete or rename can be refused while a profile uses the router.
A disabled step counts too, because enabling it again would name a router that
no longer exists.

This module imports no web framework. No message holds a submitted value.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ...config.settings_file import SettingsFile
from ...config.settings_maps import DECISION_MODELS, DOCUMENT_ROUTERS
from ...config.user_config import KEYCHAIN_PREFIX, SECRETS_DIR
from ...core.providers.decision import registry
from ...core.providers.decision.base import is_loopback
from ...core.workspace import PROFILE_SLOTS

#: The Studio operation whose ``document_router`` parameter names a router.
READ_OPERATION = "read.document"
ROUTER_PARAM = "document_router"

#: The plain line of each 409 reason (``transports/api/AGENTS.md`` rule 4).
CONFLICT_REASONS: dict[str, str] = {
    "in-use": "{who} names this {what}. Change it first.",
    "name-taken": "A router of this name exists. Choose another name.",
    "profiles-unreadable": (
        "The saved profiles could not be read, so the app cannot tell whether one "
        "uses this router. Nothing changed. Try again."
    ),
}
NOT_FOUND = "omrs.jsonc holds no {what} of this name."
TEST_NOT_FOUND = "omrs.jsonc holds no valid decision model of this name."

#: The fixed results of the Test route (``DecisionModelTest.result``).
TEST_RESULTS = frozenset(
    {
        "ok",
        "unknown-model",
        "unreachable",
        "quantisation-refused",
        "projector-not-loaded",
        "wrong-build",
        "request-failed",
        "malformed-reply",
    }
)


class ProfilesUnreadable(Exception):
    """The saved profiles could not be read. The message holds no detail."""


def _field(entry: Any, name: str, default: Any = None) -> Any:
    if isinstance(entry, Mapping):
        return entry.get(name, default)
    return getattr(entry, name, default)


def _file_key_found(reference: str, secrets: Path) -> bool:
    """Return whether a ``file://`` reference names a regular file inside *secrets*."""
    raw = os.path.expanduser(reference.removeprefix("file://"))
    if not os.path.isabs(raw):
        return False
    try:
        real = Path(raw).resolve(strict=True)
        return real.is_relative_to(secrets.resolve(strict=True)) and real.is_file()
    except (OSError, RuntimeError):
        return False


def key_state(entry: Any, secrets: Path) -> str:
    """Return the key state of a decision model entry; never the key.

    Args:
        entry: A ``DecisionModelEntry``.
        secrets: The ``secrets/`` folder of the user config folder.

    Returns:
        ``not-needed``, ``not-set``, ``reference-set``, ``resolvable`` or
        ``unresolvable``. A ``keychain://`` reference is not read.
    """
    reference = _field(entry, "key")
    if not reference:
        return "not-needed" if is_loopback(str(_field(entry, "address", ""))) else "not-set"
    if reference.startswith(KEYCHAIN_PREFIX):
        return "reference-set"
    if reference.startswith("env://"):
        found = bool(os.environ.get(reference.removeprefix("env://"), "").strip())
    else:
        found = _file_key_found(reference, secrets)
    return "resolvable" if found else "unresolvable"


def _entries(file: SettingsFile, map_key: str) -> Mapping[str, Any]:
    return file.maps.get(map_key, {})


def decision_model_list(file: SettingsFile) -> dict[str, Any]:
    """Return the body of ``GET /v1/settings/decision-models`` without ``status``."""
    untested = set(registry.not_yet_tested())
    routers = _entries(file, DOCUMENT_ROUTERS)
    secrets = file.directory / SECRETS_DIR
    models = []
    for name, entry in sorted(_entries(file, DECISION_MODELS).items()):
        models.append(
            {
                "name": name,
                **{
                    field: _field(entry, field)
                    for field in (
                        "kind",
                        "address",
                        "model",
                        "images",
                        "server",
                        "model_file",
                        "projector_file",
                        "model_sha256",
                        "projector_sha256",
                    )  # fmt: skip
                },
                "hosted": not is_loopback(str(_field(entry, "address", ""))),
                "key_state": key_state(entry, secrets),
                "not_yet_tested": _field(entry, "kind") in untested,
                "used_by": sorted(r for r, e in routers.items() if _field(e, "model") == name),
            }
        )
    kinds = [{"name": kind, "not_yet_tested": kind in untested} for kind in registry.kinds()]
    return {"revision": file.revision, "kinds": kinds, "models": models}


def _router_item(
    name: str, entry: Any, models: Mapping[str, Any], host: str, users: list[str]
) -> dict[str, Any]:
    model = models.get(_field(entry, "model"))
    hosted = model is not None and not is_loopback(str(_field(model, "address", "")))
    images = bool(_field(entry, "images", False))
    reason = None
    if model is None:
        reason = "unknown-model"
    elif hosted and not _field(entry, "send_off_machine", False):
        reason = "needs-opt-in"
    return {
        "name": name,
        "model": _field(entry, "model"),
        "question": _field(entry, "question"),
        "threshold": _field(entry, "threshold"),
        "images": images,
        "max_chars": _field(entry, "max_chars"),
        "send_off_machine": bool(_field(entry, "send_off_machine", False)),
        "model_kind": None if model is None else _field(model, "kind"),
        "hosted": hosted,
        "experimental": hosted and images,
        "will_run": reason is None,
        "will_not_run_reason": reason,
        "host": host == name,
        "used_by": users,
    }


def router_list(file: SettingsFile, users: Mapping[str, list[str]]) -> dict[str, Any]:
    """Return the body of ``GET /v1/settings/document-routers`` without ``status``.

    Args:
        file: ``omrs.jsonc`` as it is now.
        users: Router name to the titles of the saved profiles that name it.
    """
    models = _entries(file, DECISION_MODELS)
    host = str(file.values.get("document_router") or "")
    routers = [
        _router_item(name, entry, models, host, list(users.get(name, [])))
        for name, entry in sorted(_entries(file, DOCUMENT_ROUTERS).items())
    ]
    return {"revision": file.revision, "routers": routers}


def _named_routers(document: Mapping[str, Any] | None) -> set[str]:
    """Return the router names that the Read document steps of *document* set."""
    found: set[str] = set()
    for node in (document or {}).get("nodes", []):
        if node.get("operation") != READ_OPERATION:
            continue
        value = (node.get("params") or {}).get(ROUTER_PARAM)
        if isinstance(value, str) and value.strip():
            found.add(value.strip())
    return found


def profile_routers(catalogue: Any) -> dict[str, list[str]]:
    """Return router name to the titles of the saved user profiles that name it.

    Args:
        catalogue: A ``ProfileCatalogue`` (``list_profiles``, ``slot_document``),
            or ``None`` when the server has no workspace (no saved profiles).

    Raises:
        ProfilesUnreadable: The profiles could not be read.
    """
    if catalogue is None:
        return {}
    users: dict[str, list[str]] = {}
    try:
        for record in catalogue.list_profiles():
            title = str(record.get("title") or record["profile_id"])
            named: set[str] = set()
            for slot in PROFILE_SLOTS:
                named |= _named_routers(catalogue.slot_document(record["profile_id"], slot))
            for router in named:
                users.setdefault(router, []).append(title)
    except Exception as exc:
        raise ProfilesUnreadable from exc
    return {router: sorted(titles) for router, titles in users.items()}


def decision_test_body(name: str, result: Mapping[str, Any]) -> dict[str, Any]:
    """Return the Test body from ``compose_decision.test_decision_model``'s result.

    Only the four known fields pass, so no key or reply text can leak. A
    result outside the fixed set reads ``request-failed``.
    """
    status = str(result.get("status") or "request-failed")
    projector, build = result.get("projector"), result.get("build")
    return {
        "name": name,
        "result": status if status in TEST_RESULTS else "request-failed",
        "quantisation": str(result.get("quantisation") or ""),
        "projector": None if projector is None else str(projector),
        "build": None if build is None else str(build),
    }
