"""llama.cpp LLM provider (classification, Chat and the claim check judge).

Constructs ``OpenAILike`` LLM pointed at the one llama.cpp router's OpenAI-
compatible ``/v1`` endpoint.  Requires
``llama-index-llms-openai-like``, which is part of the base install (ADR-083).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...llamacpp_router import check_listed
from ...runtime_gate import http_clients
from .connection import (
    ConnectionDescriptor,
    ConnectionField,
    ConnectionTarget,
    ReadOnlyValue,
    join_url,
    models_from,
)
from .reply import ReplyFacts
from .reply_read import read_openai_reply
from .sampling import constructor_kwargs as sampling_kwargs
from .sampling import merge_kwargs

if TYPE_CHECKING:
    from ....config import Settings
    from ...runtime_gate import Role


def reasoning_kwargs(level: str) -> dict[str, Any] | None:
    """Return ``None``: llama.cpp has no stable request field for a level."""
    return None


def read_reply(raw: Any) -> ReplyFacts:
    """Return reasoning text and tokens from a llama.cpp chat completion."""
    return read_openai_reply(raw)


def build(
    settings: Settings,
    *,
    timeout: float | None = None,
    answer_model: str | None = None,
    reasoning: str = "",
    temperature: float | None = None,
    seed: int | None = None,
    allowed_hosts: tuple[str, ...] = (),
) -> Any:
    """Construct an ``OpenAILike`` LLM for llama.cpp from *settings*.

    Args:
        settings: Resolved settings.
        timeout: Seconds to wait for a response. Defaults to
            ``metadata.classify_timeout``; the llamaindex pipeline passes
            ``metadata.pipeline_timeout`` instead, and the answer
            composition root passes ``answer.timeout``.
        answer_model: The role (ADR-108 D3). ``None`` means classification: the
            Text model ``llamacpp_chat_model``. A string means an answer role
            (Chat, judge, Chat test): that model. A blank string is refused, so
            an answer role never falls back to the Text model. Both go to the
            router address (one-llamacpp-router D2).
        reasoning: Accepted and ignored: llama.cpp has no stable request
            field for a level (add-chat-reasoning-and-usage D2).
        temperature: Sent as ``temperature`` when set (pre-exp35 D2). Empty keeps
            the library default (0.1 on the OpenAI-like classes).
        seed: Sent as ``seed`` when set. Empty sends no seed.
        allowed_hosts: Accepted and ignored: only OpenRouter pins hosts.

    Returns:
        A configured ``OpenAILike`` LLM.

    Raises:
        ValueError: *answer_model* is blank. Nothing is built.
        RouterRefused: The router is managed and the model is not in its list
            (``model-not-listed``), or it is an embedding entry (``role-mismatch``).
            Nothing is built.
    """
    role: Role
    if answer_model is None:
        model, role = settings.llamacpp_chat_model, "classification"
    elif answer_model.strip():
        model, role = answer_model, "chat"
    else:
        raise ValueError("Choose a model for llama.cpp in Settings > Chat.")
    check_listed(settings, role, model)

    from llama_index.llms.openai_like import OpenAILike

    return OpenAILike(
        model=model,
        api_base=settings.llamacpp_router_url,
        api_key="no-key",
        # Without this, LlamaIndex sends raw text to the legacy /completions
        # endpoint: no chat template, no stop token, a run to the context limit.
        is_chat_model=True,
        # OpenAILike names this ``timeout``; ``request_timeout`` is the Ollama
        # spelling and is silently dropped, leaving the 60s default in place.
        timeout=(timeout if timeout is not None else settings.metadata.classify_timeout),
        # OMRS's own server, when managed: each request joins the runtime first.
        **http_clients(role),
        # Empty values add nothing (D2). ``allowed_hosts`` is accepted and ignored.
        **merge_kwargs(sampling_kwargs(temperature, seed)),
    )


def _test_targets(settings: Any) -> ConnectionTarget:
    return ConnectionTarget(join_url(settings.llamacpp_router_url, "/models"))


#: Card data for the llama.cpp provider (design D5). One router address serves every role.
CONNECTION = ConnectionDescriptor(
    display_name="llama.cpp",
    locality="local",
    requires_module="llama_index.llms.openai_like",
    extra="llamacpp",
    fields=(
        ConnectionField(
            "router_url",
            "Router address",
            "url",
            "llamacpp_router_url",
            "LLAMACPP_ROUTER_URL",
        ),
    ),
    read_only=lambda s: [
        ReadOnlyValue("Router mode", s.llamacpp_router_server),
        ReadOnlyValue("Embedding model", s.llamacpp_embed_model),
        # The key keeps its old name; the label says what the model does (ADR-108 D1).
        ReadOnlyValue("Text model (classification)", s.llamacpp_chat_model),
    ],
    test_targets=_test_targets,
    models_target=lambda s: ConnectionTarget(join_url(s.llamacpp_router_url, "/models")),
    parse_models=lambda payload: models_from(payload, "data", "id"),
    model_source="huggingface-gguf",
    default_answer_model=False,
    test_checks_model_list=True,
)
