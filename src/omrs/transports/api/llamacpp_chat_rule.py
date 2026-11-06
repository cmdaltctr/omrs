"""Save-time rules that several llama.cpp routes share (one-llamacpp-router, D3, D14, ADR-108 D15).

* :func:`program_refusal` keeps the ADR-084 program rule on the Configuration
  page too: changing ``llamacpp_server_binary`` needs ``credentials`` and an
  executable named ``llama-server``.
* :func:`mode_refusal` keeps the ``credentials`` scope on the router mode when
  the Configuration page writes ``llamacpp_router_server``.
* :func:`model_list` reads the router list in force from ``omrs.jsonc`` (the
  user map, else the shipped list), and :func:`chat_role_refusal` refuses a
  Chat choice that names an embedding entry (``role-mismatch``). Both
  ``PUT /v1/settings/chat`` and ``PUT /v1/settings/configuration`` call it, so
  no route can bypass it.
* :func:`reasoned` builds an error envelope that carries a fixed ``reason``.

Nothing here starts a process. No message holds a model name or a path.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from fastapi.responses import JSONResponse

from ...config.llamacpp_models import LLAMACPP_MODELS, SHIPPED_MODELS, LlamaCppModelEntry
from ...config.llamacpp_roles import ROLE_MISMATCH, derive_roles
from ...config.settings_file import SettingsFile
from ...integrations.llamacpp_runtime import rules
from .errors import API_HEADERS
from .security import redact

BINARY_RULE = (
    "The program must be the absolute path of an executable file named llama-server "
    "(llama-server.exe on Windows)."
)
PROGRAM_CREDENTIALS_RULE = "Changing the program path needs the credentials scope."
MODE_CREDENTIALS_RULE = "Changing who runs the llama.cpp router needs the credentials scope."


def reasoned(status_code: int, message: str, reason: str) -> JSONResponse:
    """Return an error envelope with a fixed *reason* next to the plain *message*."""
    body = {"status": "error", "message": redact(message), "reason": reason}
    return JSONResponse(body, status_code=status_code, headers=API_HEADERS)


def model_list(file: SettingsFile) -> Mapping[str, LlamaCppModelEntry]:
    """Return the router list in force: the file's map, else the shipped list."""
    saved = file.maps.get(LLAMACPP_MODELS)
    return dict(SHIPPED_MODELS if saved is None else saved)


def chat_role_refusal(file: SettingsFile, provider: str, model: str) -> str | None:
    """Return the rule that a llama.cpp Chat choice breaks, or ``None``.

    Only the provider ``llamacpp`` names an entry of the router list. An entry
    whose preset has ``embeddings`` true cannot answer (``role-mismatch``).

    Args:
        file: ``omrs.jsonc`` as read now.
        provider: The Chat provider after the write.
        model: The Chat model after the write.

    Returns:
        A plain-English line that never holds *model*.
    """
    if provider.strip() != "llamacpp" or not model.strip():
        return None
    report = derive_roles(model_list(file), chat_model=model.strip())
    for problem in report.problems:
        if problem.reason == ROLE_MISMATCH:
            return problem.rule
    return None


def program_refusal(value: object, scopes: Iterable[str]) -> tuple[int, str] | None:
    """Return ``(status, message)`` when a program path write breaks the ADR-084 rule.

    Args:
        value: The new ``llamacpp_server_binary``; ``None`` or blank clears it.
        scopes: The scopes of the session that writes.

    Returns:
        ``(403, PROGRAM_CREDENTIALS_RULE)``, ``(400, BINARY_RULE)`` or ``None``.
        The message never holds the path.
    """
    if "credentials" not in set(scopes):
        return 403, PROGRAM_CREDENTIALS_RULE
    text = "" if value is None else str(value).strip()
    if text and not rules.check_binary(text):
        return 400, BINARY_RULE
    return None


def mode_refusal(scopes: Iterable[str]) -> tuple[int, str] | None:
    """Return ``(403, message)`` when the session lacks ``credentials`` to change the mode."""
    return None if "credentials" in set(scopes) else (403, MODE_CREDENTIALS_RULE)
