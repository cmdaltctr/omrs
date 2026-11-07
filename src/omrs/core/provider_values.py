"""Read provider API keys from a settings object.

These helpers read ``EffectiveSettings`` fields by name. They live outside
``core/settings.py`` so that module stays pure data and under the file-size
ceiling. ``core/settings.py`` must not import this module.
"""

from __future__ import annotations

from .settings import PROVIDER_SECRET_FIELDS


def provider_secret_values(settings: object) -> tuple[str, ...]:
    """Return the value of each provider API key on *settings*, in field order.

    A field the object lacks counts as blank. Blank values are kept so the
    position matches :data:`PROVIDER_SECRET_FIELDS`.
    """
    return tuple(str(getattr(settings, name, "") or "") for name in PROVIDER_SECRET_FIELDS)
