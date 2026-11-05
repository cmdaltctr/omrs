"""Resolve the key reference of a decision model entry (change document-reading-routers).

Key references resolve through the provider key rules of ``omrs.jsonc``
(ADR-083, gotcha 18): ``env://``, ``file://`` inside ``secrets/`` and
``keychain://``. A literal key is never used. ``compose_decision`` imports
:func:`resolve_key_reference` from here; nothing here logs the key.
"""

from __future__ import annotations

from typing import Any


def resolve_key_reference(reference: str | None, *, keychain: Any = None) -> str | None:
    """Return the key that *reference* names, or ``None``.

    Args:
        reference: ``env://NAME``, ``file://<path inside secrets/>`` or
            ``keychain://<provider>``. A literal key resolves to ``None``.
        keychain: The keychain store to read; ``None`` builds a ``KeychainStore``
            when a ``keychain://`` reference needs one.
    """
    if not reference:
        return None
    from .config.user_config import (
        CONFIG_FILE,
        SECRETS_DIR,
        KeychainRef,
        _resolve_reference,
        user_config_dir,
    )

    folder = user_config_dir()
    resolved, _problem = _resolve_reference(
        "key", reference, folder / SECRETS_DIR, folder / CONFIG_FILE
    )
    if not isinstance(resolved, KeychainRef):
        return resolved
    from .integrations.keychain import KeychainStore, KeychainUnavailableError

    store = keychain if keychain is not None else KeychainStore()
    try:
        secret = store.read(resolved.provider) if store.available else None
    except KeychainUnavailableError:
        return None
    return secret.reveal() if secret is not None else None
