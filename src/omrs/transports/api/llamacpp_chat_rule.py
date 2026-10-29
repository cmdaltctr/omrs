"""The rule for a llama.cpp Chat choice while OMRS runs the Chat server (ADR-108 D5, D11).

While ``llamacpp_chat_server`` is ``managed``, OMRS's own ``llama-server`` loads the
Chat model. So a write that makes the Chat choice ``llamacpp`` changes what that
server launches: it needs the ``credentials`` scope and a model that passes the
ADR-084 model rule. ``PUT /v1/settings/chat`` and ``PUT /v1/settings/configuration``
both call :func:`chat_choice_refusal`, so no route can bypass it. A hand edit of
``omrs.jsonc`` is not checked here; the launch check still applies.

:func:`program_refusal` keeps the ADR-084 program rule on the Configuration page
too: changing ``llamacpp_server_binary`` needs ``credentials`` and an executable
named ``llama-server`` (ADR-108 D15).
"""

from __future__ import annotations

from collections.abc import Iterable

from ...core.providers.llm import llamacpp_rules as rules

MODEL_RULE = (
    "The model must be the absolute path of an existing .gguf file, or a Hugging Face id "
    "such as org/name or org/name:tag."
)
BINARY_RULE = (
    "The program must be the absolute path of an executable file named llama-server "
    "(llama-server.exe on Windows)."
)
PROGRAM_CREDENTIALS_RULE = "Changing the program path needs the credentials scope."
CREDENTIALS_RULE = (
    "OMRS's own llama-server loads the Chat model, so a llama.cpp Chat choice needs the "
    "credentials scope."
)


def chat_choice_refusal(
    chat_server: str, provider: str, model: str, scopes: Iterable[str]
) -> tuple[int, str] | None:
    """Return ``(status, message)`` when a Chat choice breaks the managed-server rule.

    Args:
        chat_server: ``llamacpp_chat_server`` in force: ``external`` or ``managed``.
        provider: The Chat provider after the write.
        model: The Chat model after the write.
        scopes: The scopes of the session that writes.

    Returns:
        ``(403, CREDENTIALS_RULE)``, ``(400, MODEL_RULE)`` or ``None`` when the
        write may go ahead. The message never holds the model.
    """
    if chat_server != "managed" or provider.strip() != "llamacpp":
        return None
    if "credentials" not in set(scopes):
        return 403, CREDENTIALS_RULE
    if rules.model_kind(model) is None:
        return 400, MODEL_RULE
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
