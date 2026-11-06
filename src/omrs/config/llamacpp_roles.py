"""Roles of the llama.cpp router list, derived from the role settings (one-llamacpp-router, D3).

A role is never stored. An entry of ``llamacpp_models`` holds the role of each
setting that names its ``model``:

* ``embeddings``: ``llamacpp_embed_model``;
* ``classification``: ``llamacpp_chat_model``;
* ``chat``: ``answer.model``, while Chat runs on llama.cpp;
* ``judge``: ``answer.verify_model``, while the claim-check judge runs on llama.cpp;
* ``decision``: each managed ``llamacpp`` decision model entry.

A blank role setting gives no role and no problem ("no Chat model chosen"). A
role setting that names no entry gives the reason ``model-not-listed``. An entry
whose preset has ``embeddings`` true cannot serve a text role (``role-mismatch``),
because its child runs embedding-only. An entry used for embeddings must set its
pooling and sizes (``preset-invalid``). A refused role is not assigned.

This module only derives. It starts nothing and sends nothing.

This module is a leaf: it imports only ``config/`` modules that do not import it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import NamedTuple

from .llamacpp_models import PRESET_INVALID, LlamaCppModelEntry, embedding_preset_problem

ROLE_EMBEDDINGS = "embeddings"
ROLE_CLASSIFICATION = "classification"
ROLE_CHAT = "chat"
ROLE_JUDGE = "judge"
ROLE_DECISION = "decision"
#: Every role, in the order a role list shows them.
ROLES: tuple[str, ...] = (
    ROLE_EMBEDDINGS,
    ROLE_CLASSIFICATION,
    ROLE_CHAT,
    ROLE_JUDGE,
    ROLE_DECISION,
)
#: The roles a text model serves. An embedding entry cannot hold any of them.
TEXT_ROLES: tuple[str, ...] = (ROLE_CLASSIFICATION, ROLE_CHAT, ROLE_JUDGE, ROLE_DECISION)

MODEL_NOT_LISTED = "model-not-listed"
ROLE_MISMATCH = "role-mismatch"


class RoleProblem(NamedTuple):
    """A role that no entry can serve.

    Attributes:
        role: The role (one of :data:`ROLES`).
        model: The model name the role setting holds.
        reason: ``model-not-listed``, ``role-mismatch`` or ``preset-invalid``.
        rule: A plain-English line. It names the role, never the model.
    """

    role: str
    model: str
    reason: str
    rule: str


class RoleReport(NamedTuple):
    """What :func:`derive_roles` found.

    Attributes:
        roles: The roles of each entry, by entry id, in :data:`ROLES` order. An
            entry with no role has an empty tuple.
        problems: The roles that were refused or have no entry, in role order.
    """

    roles: Mapping[str, tuple[str, ...]]
    problems: tuple[RoleProblem, ...]


def derive_roles(
    models: Mapping[str, LlamaCppModelEntry],
    *,
    embed_model: str = "",
    classify_model: str = "",
    chat_model: str = "",
    judge_model: str = "",
    decision_models: Iterable[str] = (),
) -> RoleReport:
    """Map the role settings to the entries that serve them.

    Pass ``chat_model`` only while Chat runs on llama.cpp, and ``judge_model``
    only while the judge does; an empty name gives no role. A name that two
    settings share (the shipped Qwen3-4B for classification and Chat) gives that
    entry both roles.

    Args:
        models: The list in force (``Settings.llamacpp_models``).
        embed_model: ``llamacpp_embed_model``.
        classify_model: ``llamacpp_chat_model``, the classification Text model.
        chat_model: ``answer.model`` while ``answer.provider`` is ``llamacpp``.
        judge_model: ``answer.verify_model`` while the judge runs on llama.cpp.
        decision_models: The ``model`` of each managed ``llamacpp`` decision entry.

    Returns:
        The roles by entry id and the problems.
    """
    by_model = {entry.model: name for name, entry in models.items()}
    held: dict[str, set[str]] = {name: set() for name in models}
    problems: list[RoleProblem] = []
    wanted = [
        (ROLE_EMBEDDINGS, embed_model),
        (ROLE_CLASSIFICATION, classify_model),
        (ROLE_CHAT, chat_model),
        (ROLE_JUDGE, judge_model),
        *((ROLE_DECISION, model) for model in decision_models),
    ]
    for role, model in wanted:
        name = by_model.get(model)
        if not model:
            continue
        if name is None:
            problems.append(
                RoleProblem(role, model, MODEL_NOT_LISTED, f"The {role} model is not in the list.")
            )
            continue
        entry = models[name]
        if role == ROLE_EMBEDDINGS:
            rule = embedding_preset_problem(entry)
            if rule is not None:
                problems.append(RoleProblem(role, model, PRESET_INVALID, rule))
                continue
        elif entry.preset.get("embeddings") is True:
            rule = f"An embedding entry cannot serve the {role} role."
            problems.append(RoleProblem(role, model, ROLE_MISMATCH, rule))
            continue
        held[name].add(role)
    order = {role: place for place, role in enumerate(ROLES)}
    return RoleReport(
        {name: tuple(sorted(roles, key=order.__getitem__)) for name, roles in held.items()},
        tuple(sorted(problems, key=lambda problem: order[problem.role])),
    )
