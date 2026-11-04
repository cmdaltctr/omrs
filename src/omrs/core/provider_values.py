"""Read provider addresses and API keys from a settings object.

These helpers read ``EffectiveSettings`` fields by name. They live outside
``core/settings.py`` so that module stays pure data and under the file-size
ceiling. ``core/settings.py`` must not import this module.
"""

from __future__ import annotations

from typing import Any

from .settings import PROVIDER_SECRET_FIELDS


def classification_url(settings: Any) -> str:
    """Return the llama.cpp classification address: ``llamacpp_classify_url``, else Chat's.

    A blank classification address follows ``llamacpp_chat_url``, so an install
    that set only the Chat address keeps working (ADR-108 D2). Both
    classification paths, the llama.cpp card and the runtime list call this.
    """
    own = (getattr(settings, "llamacpp_classify_url", "") or "").strip()
    return own or settings.llamacpp_chat_url


def provider_secret_values(settings: object) -> tuple[str, ...]:
    """Return the value of each provider API key on *settings*, in field order.

    A field the object lacks counts as blank. Blank values are kept so the
    position matches :data:`PROVIDER_SECRET_FIELDS`.
    """
    return tuple(str(getattr(settings, name, "") or "") for name in PROVIDER_SECRET_FIELDS)
