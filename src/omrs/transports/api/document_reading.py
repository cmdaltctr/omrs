"""The body and the write checks of ``/v1/settings/document-reading`` (design D10).

Settings > Document reading edits server-wide keys in ``omrs.jsonc``. Each
key applies only at the next launch, so a row shows the value in force since
launch (the launch ``Settings``), the valid value the file holds now, the
source, the default and whether a restart is pending. The one exception is
``document_router``, a live value (``ROUTER_LIVE_VALUES``): its row shows the
file value, which the running server follows. A key that ``env`` or ``.env``
sets is locked.

The body reads the launch state on ``app.state.configuration`` (the same
``ConfigurationState`` the Configuration route reads). When that state is
missing, it uses ``compose.get_settings()`` and the file as it is now, so no
row is pending.

This module imports no web framework. No message holds a submitted value.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ... import capabilities
from ...config.field_rules import KIND_RETIRED
from ...config.rules import (
    DOCUMENT_READING_KEYS,
    OLD_READING_KEYS,
    REPLACED_READING_KEYS,
    document_reading_problem,
    replaced_key_reason,
)
from ...config.settings_file import SettingsFile, read_settings_file
from ...config.settings_maps import DOCUMENT_ROUTERS, NO_ROUTER
from ...config.user_config import display_path
from ...core import reading_parts
from ...core.reading_lists import OCR_ENGINES_DEFAULT, expand_ocr_engines, expand_pdf_reader
from ...core.settings import ROUTER_LIVE_VALUES
from ..settings_view import plain, source_word
from .restart_snapshot import capture, pending

if TYPE_CHECKING:
    from ...config import Settings

logger = logging.getLogger(__name__)

#: Source words a row may show. ``init`` and ``yaml`` read ``default``.
_SHOWN_SOURCES = frozenset({"env", "dotenv", "config-file"})
_LOCKING_SOURCES = frozenset({"env", "dotenv"})
NOT_A_READING_KEY = "{key} is not a document reading setting."
UNKNOWN_ROUTER = "document_router: No router of this name is in omrs.jsonc."

#: The reader the running engine uses. It is resolved once per process.
_reader_in_use: list[str] = []


def reset_reader_in_use() -> None:
    """Forget the resolved reader (used by tests)."""
    _reader_in_use.clear()


def reader_in_use(launch: Settings) -> str | None:
    """Return the PDF reader that *launch* resolves to, or ``None`` when that fails."""
    if not _reader_in_use:
        try:
            _reader_in_use.append(capabilities.resolve_pdf_reader(launch))
        except Exception:
            logger.exception("The PDF reader in use could not be resolved.")
            return None
    return _reader_in_use[0]


def lock_reason(key: str, variable: str | None = None) -> str:
    """Return the lock text for *key*, which names its environment variable.

    Args:
        key: The setting key.
        variable: The key whose variable locks the row, when that is an old
            single-value key (``OCR_ENGINE_PRIMARY`` locks ``ocr_engines``).
            Defaults to *key*.
    """
    return f"Remove {(variable or key).upper()} from the environment or .env to edit it here."


def locking_key(key: str) -> str:
    """Return the key whose environment variable locks the row of *key*.

    A list key is locked by its own variable or by the old single-value
    variable that wins in its place. ``Settings`` records the winner under the
    list key, so the variables that are set tell which one it was.
    """
    for candidate in (key, *OLD_READING_KEYS.get(key, ())):
        if os.environ.get(candidate.upper(), "").strip():
            return candidate
    return key


def row_source(launch: Settings, key: str) -> str:
    """Return ``env``, ``dotenv``, ``config-file`` or ``default`` for *key* at launch."""
    word = source_word(launch, key)
    return word if word in _SHOWN_SOURCES else "default"


def _launch_state(state: Any) -> tuple[Settings, SettingsFile, Mapping[str, Any]]:
    """Return the launch ``Settings``, the file now and the launch snapshot."""
    launch = launch_settings(state)
    read_file = getattr(state, "read_file", None) or read_settings_file
    file = read_file()
    snapshot = getattr(state, "snapshot", None)
    return launch, file, capture(file) if snapshot is None else snapshot


def _saved(file: SettingsFile, key: str) -> Any:
    """Return the valid value the file holds for *key*, or ``None``.

    A list key that the file does not set reads as the list that its old
    single-value keys mean, when the file holds a valid one.
    """
    if key in file.values:
        value = file.values[key]
        return None if document_reading_problem(key, value) is not None else plain(value)
    held = {
        old: file.values[old]
        for old in OLD_READING_KEYS.get(key, ())
        if old in file.values and document_reading_problem(old, file.values[old]) is None
    }
    if not held:
        return None
    if key == "pdf_readers":
        return list(expand_pdf_reader(held["pdf_reader"]))
    primary, fallback = OCR_ENGINES_DEFAULT
    return list(
        expand_ocr_engines(
            held.get("ocr_engine_primary", primary), held.get("ocr_engine_fallback", fallback)
        )
    )


def _rows(launch: Settings, file: SettingsFile, snapshot: Mapping[str, Any]) -> list[dict]:
    changed = pending(snapshot, file)
    fields = type(launch).model_fields
    rows = []
    for key in DOCUMENT_READING_KEYS:
        source = row_source(launch, key)
        locked = source in _LOCKING_SOURCES
        saved = _saved(file, key)
        default = plain(fields[key].default)
        value = plain(getattr(launch, key))
        live = key in ROUTER_LIVE_VALUES and not locked
        if live:  # the running server follows the file, so the file is what is in force
            value, source = (default, "default") if saved is None else (saved, "config-file")
        rows.append(
            {
                "key": key,
                "value": value,
                "saved": saved,
                "source": source,
                "locked": locked,
                "lock_reason": lock_reason(key, locking_key(key)) if locked else None,
                "restart_pending": bool(changed & {key, *OLD_READING_KEYS.get(key, ())})
                and not locked
                and not live,
                "default": default,
            }
        )
    return rows


def _readers() -> list[dict[str, Any]]:
    readers: list[dict[str, Any]] = [{"name": "auto", "available": True, "reason": None}]
    for name, reason in capabilities.pdf_reader_options().items():
        readers.append({"name": name, "available": reason is None, "reason": reason})
    return readers


def _local_backends() -> list[dict[str, Any]]:
    """Return each backend a local OCR list can name, with its install probe (design D8).

    The built-in backends come first, then the ones that an installed package adds.
    """
    from ...integrations.pdf.local_ocr import registry

    discovered = reading_parts.discovered(reading_parts.KIND_LOCAL_OCR_BACKEND)
    options = []
    for backend in (*reading_parts.LOCAL_OCR_BACKENDS, *discovered):
        if backend.min_confidence is None:
            continue
        available = registry.BACKENDS.installed(backend.name)
        reason = None if available else "Not installed."
        options.append(
            {
                "name": backend.name,
                "available": available,
                "reason": reason,
                "default_cut": backend.min_confidence,
            }
        )
    return options


def _retired_keys(file: SettingsFile) -> list[str]:
    """Return the keys that ``omrs.jsonc`` holds and OMRS ignores, in file order (design D9)."""
    return list(dict.fromkeys(p.key for p in file.problems if p.kind == KIND_RETIRED))


def _ocr(launch: Settings, rows: list[dict[str, Any]]) -> dict[str, Any]:
    workers_dir = launch.ocr_workers_dir.strip()
    names = [
        str(name)
        for row in rows
        if row["key"] == "ocr_engines"
        for field in ("value", "saved")
        for name in row[field] or ()
    ]
    return {
        "workers_dir": display_path(workers_dir) if workers_dir else None,
        "engines": capabilities.ocr_engine_options(workers_dir, names),
    }


def build_document_reading(state: Any) -> dict[str, Any]:
    """Return the body of ``GET /v1/settings/document-reading`` without ``status``.

    Args:
        state: ``app.state.configuration``, or ``None`` when the launch set none.

    Returns:
        ``revision``, the ``settings`` rows in key order, ``pdf_readers``,
        ``pdf_reader_in_use``, ``local_ocr_backends`` (each with its
        ``default_cut``), ``retired_keys`` and the ``ocr`` block (design D9, D10).
    """
    launch, file, snapshot = _launch_state(state)
    rows = _rows(launch, file, snapshot)
    return {
        "revision": file.revision,
        "settings": rows,
        "pdf_readers": _readers(),
        "pdf_reader_in_use": reader_in_use(launch),
        "local_ocr_backends": _local_backends(),
        "retired_keys": _retired_keys(file),
        "ocr": _ocr(launch, rows),
    }


def launch_settings(state: Any) -> Settings:
    """Return the launch ``Settings`` of *state*, or ``compose.get_settings()``."""
    launch = getattr(state, "launch_settings", None)
    if launch is not None:
        return launch
    from ... import compose

    return compose.get_settings()


def update_refusal(values: Mapping[str, Any], launch: Settings) -> tuple[int, str] | None:
    """Run checks 2 to 4 of a ``PUT`` and return ``(status, message)``, or ``None``.

    The checks run in contract order: a key outside the six (400; an old
    single-value key gets its own message naming the list key that replaces it),
    a locked key (409, the first in key order), then a value that breaks its
    rule (400). The body shape (check 1) is the framework's job; the file
    checks (5 to 7) belong to the writer. A listed PDF reader that is not
    installed is allowed: the row says "Not installed" and start-up falls
    back to the next reader.

    Args:
        values: The ``values`` member of the request.
        launch: The launch ``Settings``, which say where each value came from.
    """
    for key in values:
        if key in REPLACED_READING_KEYS:
            return 400, f"{key}: {replaced_key_reason(key)}"
        if key not in DOCUMENT_READING_KEYS:
            return 400, NOT_A_READING_KEY.format(key=key)
    for key in DOCUMENT_READING_KEYS:
        if key in values and row_source(launch, key) in _LOCKING_SOURCES:
            return 409, lock_reason(key, locking_key(key))
    for key in DOCUMENT_READING_KEYS:
        if key in values:
            rule = document_reading_problem(key, values[key])
            if rule is not None:
                return 400, f"{key}: {rule}"
    return None


def router_refusal(values: Mapping[str, Any], file: SettingsFile) -> tuple[int, str] | None:
    """Refuse a host ``document_router`` that names no router in *file* (ADR-110, D3).

    The host choice applies to the next request, so it must name a router that
    ``omrs.jsonc`` holds now, or ``none``. ``null`` removes the key and passes.

    Args:
        values: The ``values`` member of the request, already checked by
            :func:`update_refusal`.
        file: ``omrs.jsonc`` as it is now.

    Returns:
        ``(400, message)``, or ``None`` when the value is fine. The message
        never holds the value.
    """
    name = values.get("document_router")
    if name is None or name == NO_ROUTER or name in file.maps.get(DOCUMENT_ROUTERS, {}):
        return None
    return 400, UNKNOWN_ROUTER
