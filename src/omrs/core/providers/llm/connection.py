"""Connection descriptors for LLM providers (design D5).

Each LLM provider module declares one :data:`CONNECTION` descriptor: pure
data plus small pure functions. The web workspace builds a provider card
from it, so a new provider needs a new module and one registry line, with
no change to the card code.

Nothing here imports a provider module, a settings singleton or
``omrs.config`` at run time.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from omrs.core.providers.model_sources import ModelSourceKind

#: The block of a provider card that shows a value (ADR-108 D8). ``None`` puts it
#: above the blocks. Only the llama.cpp card sets a group.
CardGroup = Literal["embeddings", "metadata", "answers"]


@dataclass(frozen=True)
class ConnectionField:
    """One editable value of a provider.

    Attributes:
        id: Stable field id within the provider, for example ``base_url``.
        label: Short label for the card.
        kind: ``url`` for an address, ``secret`` for an API key, ``int`` for a
            whole number (``minimum`` and ``maximum`` bound it). ``text`` is
            free text and ``choice`` one of a fixed set of names; only the
            managed llama.cpp server uses them, outside any provider descriptor.
        settings_field: Name of the ``Settings`` field that holds the value.
        env_var: Environment variable that sets the value.
        minimum: Smallest allowed value of an ``int`` field.
        maximum: Largest allowed value of an ``int`` field.
        required: Whether Chat needs a value here to be ready. A secret
            field that is not required (a local server needs no key) does
            not block Chat while empty.
        group: The card block that shows the field, or ``None``.
        follows: The id of the field whose value applies while this one is
            blank, for example ``chat_url`` for the classification address.
    """

    id: str
    label: str
    kind: Literal["url", "secret", "int", "text", "choice"]
    settings_field: str
    env_var: str
    required: bool = True
    minimum: int | None = None
    maximum: int | None = None
    group: CardGroup | None = None
    follows: str | None = None


@dataclass(frozen=True)
class ReadOnlyValue:
    """A labelled value the card shows but the user cannot edit here, and its card block."""

    label: str
    value: str
    group: CardGroup | None = None


@dataclass(frozen=True)
class ConnectionTarget:
    """Requests the server sends to test a provider or list its models.

    Attributes:
        urls: Full request URLs. Empty means the provider is not configured.
        headers: Request headers. They can hold the key, so they stay out
            of ``repr`` and are never returned to a client.
    """

    urls: tuple[str, ...]
    headers: dict[str, str] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class ProviderLookup:
    """One read the server sends to a provider on request, and how to read the answer.

    The transport sends the request; this module never touches the network.

    Attributes:
        target: Returns the request for a settings object. Empty ``urls``
            means nothing is sent.
        parse: Returns the useful part of the decoded JSON answer, or
            ``None`` when the payload has an unexpected shape.
    """

    target: Callable[[Any], ConnectionTarget]
    parse: Callable[[object], Any]


@dataclass(frozen=True)
class ConnectionDescriptor:
    """Everything a provider card needs to know about one provider.

    Attributes:
        display_name: Name shown on the card.
        locality: ``local`` or ``cloud``.
        requires_module: Module that must import for the provider to run.
        extra: ``pyproject.toml`` extra that supplies the module, or
            ``None`` when the base install has it.
        fields: Editable values.
        read_only: Returns the labelled read-only values for a settings object.
        test_targets: Returns the requests of the connection test.
        models_target: Returns the request that lists models.
        parse_models: Returns model names from a decoded model-list payload;
            an empty list when the payload has an unexpected shape.
        reasoning_levels: Optional catalogue read. Its parser returns a map
            of model name to ``{"levels", "default", "mandatory"}``. ``None``
            means the provider publishes no level list.
        credit: Optional read of the key's spending limit. Its parser returns
            ``{"limit_usd", "remaining_usd"}`` or ``None``. ``None`` here
            means the provider publishes no credit figure.
        model_source: Where the app can search for and download a model for this
            provider: ``huggingface-gguf`` (llama.cpp) or ``ollama-pull``
            (Ollama). ``None`` means the provider has no source, so its card shows
            no Get a model panel and the download routes refuse it.
        default_answer_model: Whether the provider has a model setting of its
            own that an empty judge model may use. ``False`` (llama.cpp, whose
            only model setting is the Text model for classification) means an
            empty Chat or judge model is refused, never filled in (ADR-108 D3).
        test_checks_model_list: Whether the Chat test reads ``models_target``
            first and refuses a model the server does not list (ADR-108 D7).
    """

    display_name: str
    locality: Literal["local", "cloud"]
    requires_module: str
    extra: str | None
    fields: tuple[ConnectionField, ...]
    read_only: Callable[[Any], list[ReadOnlyValue]]
    test_targets: Callable[[Any], ConnectionTarget]
    models_target: Callable[[Any], ConnectionTarget]
    parse_models: Callable[[object], list[str]]
    reasoning_levels: ProviderLookup | None = None
    credit: ProviderLookup | None = None
    model_source: ModelSourceKind | None = None
    default_answer_model: bool = True
    test_checks_model_list: bool = False


def join_url(base: str, path: str) -> tuple[str, ...]:
    """Return ``base`` joined to ``path`` as a one-item tuple, or ``()`` for a blank base."""
    base = (base or "").strip().rstrip("/")
    return (f"{base}{path}",) if base else ()


def models_from(payload: object, list_key: str, name_key: str) -> list[str]:
    """Return the string ``name_key`` of each item in ``payload[list_key]``.

    Args:
        payload: Decoded JSON.
        list_key: Key of the item list.
        name_key: Key of the model name in each item.

    Returns:
        Model names in payload order. Any unexpected shape gives ``[]``.
    """
    if not isinstance(payload, dict):
        return []
    items = payload.get(list_key)
    if not isinstance(items, list):
        return []
    return [
        item[name_key]
        for item in items
        if isinstance(item, dict) and isinstance(item.get(name_key), str)
    ]
