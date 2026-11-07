"""The model-name check that every llama.cpp client makes before it contacts the router.

Every llama.cpp request (embeddings, classification, Chat, judge) goes to
``llamacpp_router_url`` and names a model of the router list in its ``model`` field
(change one-llamacpp-router, D2 and D6). While OMRS runs the router (``managed``), a
request that names a model outside the list, or an embedding entry for a text role, is
refused before any contact. While the router is ``external``, OMRS does not check the
name: the address is another server's.

The roles come from ``config.llamacpp_roles.derive_roles``, the one place that decides
what an entry may serve. This module only asks it about one role.
"""

from __future__ import annotations

from typing import Any, Literal

#: The client roles that name a model.
Role = Literal["embeddings", "classification", "chat"]

#: The keyword of ``derive_roles`` for each client role.
_ROLE_KEYWORD = {
    "embeddings": "embed_model",
    "classification": "classify_model",
    "chat": "chat_model",
}


class RouterRefused(ValueError):
    """A request that the router list cannot serve.

    Attributes:
        reason: ``model-not-listed`` or ``role-mismatch``.
        role: The client role that was refused.
    """

    def __init__(self, reason: str, role: str, text: str) -> None:
        super().__init__(text)
        self.reason = reason
        self.role = role


def check_listed(settings: Any, role: Role, model: str) -> None:
    """Refuse a request whose model the managed router cannot serve.

    Args:
        settings: Effective settings: ``llamacpp_router_server`` and ``llamacpp_models``.
        role: The client role that sends the request.
        model: The model name the request holds.

    Raises:
        RouterRefused: The router is ``managed`` and *model* is not in the list
            (``model-not-listed``), or its entry is an embedding entry used for a text
            role (``role-mismatch``). The message never holds the model name.
    """
    if settings.llamacpp_router_server != "managed":
        return
    from ..config.llamacpp_roles import MODEL_NOT_LISTED, ROLE_MISMATCH, derive_roles

    report = derive_roles(settings.llamacpp_models, **{_ROLE_KEYWORD[role]: model})
    for problem in report.problems:
        if problem.reason in (MODEL_NOT_LISTED, ROLE_MISMATCH):
            raise RouterRefused(problem.reason, role, problem.rule)
