"""Value rules shared by ``Settings`` validation and ``omrs.jsonc`` reading.

``omrs.jsonc`` ignores a value that breaks its rule and names the key (task
2.4), so the rules must be checkable before ``Settings`` is built. This
module holds the rules that are not plain types: the accepted names of a
choice field, the shape of an address, and the three file-only keys.

It is a leaf: it imports only pure-data settings models. Messages name a
rule, never a value.
"""

from __future__ import annotations

import re
from collections.abc import Collection
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..core import reading_parts as _reading_parts
from ..core.settings import OCR_NON_LATIN_MODES, OCR_ROUTING_UNITS, PROVIDER_SECRET_FIELDS

METADATA_EXTRACTION_MODES = (
    "disabled",
    "keyword",
    "local",
    "llamaindex",
    "ollama",
    "llamacpp",
    "openrouter",
)

#: Accepted names by setting path. ``Settings`` validators and the file reader
#: both read this table, so they cannot drift apart.
ACCEPTED: dict[str, tuple[str, ...]] = {
    "embed_provider": ("local", "cloud", "ollama", "llamacpp", "openrouter"),
    "metadata_llm_provider": ("local", "cloud"),
    "metadata.extraction_mode": METADATA_EXTRACTION_MODES,
    "local_backend": ("llamacpp", "ollama"),
    "cloud_backend": ("openrouter",),
    "retrieval.rerank_backend": ("onnx", "torch"),
    "chroma_mode": ("local", "cloud"),
    "ocr_routing_unit": OCR_ROUTING_UNITS,
    "ocr_non_latin_routing": OCR_NON_LATIN_MODES,
    "llamacpp_chat_server": ("external", "managed"),
    "llamacpp_embed_server": ("external", "managed"),
}

#: Settings that hold an address; ``omrs.jsonc`` accepts http and https only.
ADDRESS_FIELDS: tuple[str, ...] = (
    "ollama_base_url",
    "llamacpp_chat_url",
    "llamacpp_classify_url",
    "llamacpp_embed_url",
    "ocr_runtime_url",
    "openai_compatible_base_url",
    "azure_doc_intelligence_endpoint",
)
MAX_ADDRESS_CHARS = 2048
ADDRESS_RULE = (
    "The address must be an absolute http or https URL with a host, at most 2,048 "
    "characters, and no user name, password, query or fragment."
)

#: Settings that hold a key. ``omrs.jsonc`` holds a reference to the key, never the key.
SECRET_FIELDS: tuple[str, ...] = (
    *PROVIDER_SECRET_FIELDS,
    "chroma_cloud_api_key",
    "azure_doc_intelligence_key",
)
#: Settings fields that are bookkeeping, not settings. A file key may not name them.
INTERNAL_FIELDS: frozenset[str] = frozenset(
    {
        "config_file_fields",
        "key_file_fields",
        "key_file_paths",
        "keychain_refs",
        "user_config_dir",
        "provider_explicit",
        "setting_sources",
        "vector_store_provenance",
    }
)

#: Keys that only ``omrs.jsonc`` knows (no environment twin): kind, low, high.
FILE_ONLY: dict[str, tuple[str, int, int]] = {
    "web_port": ("int", 1024, 65535),
    "web_max_upload_mib": ("int", 1, 2048),
    "mcp_http_enabled": ("bool", 0, 0),
}


#: Names ``pdf_reader`` accepts. ``Settings`` warns and falls back to ``auto`` for
#: any other name, so ``pdf_reader`` is not in :data:`ACCEPTED` (the file reader
#: would then drop a bad value and use the code default instead). Derived from the
#: PDF reader descriptors (change local-ocr-backends, design D15).
PDF_READER_NAMES: tuple[str, ...] = ("auto", *_reading_parts.names(_reading_parts.PDF_READERS))

#: Engine names are folder names. ``config/`` cannot import ``integrations/``, so a
#: test pins this to ``integrations.ocr_worker.routes._ENGINE_NAME_RE``.
ENGINE_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
MAX_ENGINE_NAME_CHARS = 64
ENGINE_NAME_RULE = (
    "The engine name must start with a letter or digit, hold only letters, digits, dots, "
    "hyphens and underscores, and be at most 64 characters."
)

#: The list keys that hold the reader and engine order (change
#: ordered-reader-and-ocr-lists, D4), and the single-value keys each one replaces.
#: The single-value keys stay readable in every source and are never retired.
READING_LIST_KEYS: tuple[str, ...] = ("pdf_readers", "ocr_engines")
OLD_READING_KEYS: dict[str, tuple[str, ...]] = {
    "pdf_readers": ("pdf_reader",),
    "ocr_engines": ("ocr_engine_primary", "ocr_engine_fallback"),
}
KNOWN_READER_NAMES: tuple[str, ...] = tuple(name for name in PDF_READER_NAMES if name != "auto")
LIST_TYPE_RULE = "The value must be a list of names."
LIST_EMPTY_RULE = "The list must not be empty. Send null to use the default."
LIST_DUPLICATE_RULE = "The list must not name the same item twice."
#: Settings fields the starter ``omrs.jsonc`` leaves out. The old keys stay valid
#: in the file, so they are not in :data:`INTERNAL_FIELDS`, which the reader refuses.
TEMPLATE_SKIPPED_FIELDS: frozenset[str] = frozenset(
    old for olds in OLD_READING_KEYS.values() for old in olds
)
#: The rule for a reader entry that is not a known name, ``auto`` included.
READER_LIST_RULE = f"The value must be one of: {', '.join(KNOWN_READER_NAMES)}."
#: The old key to the list key that replaced it. A page write of an old key is refused.
REPLACED_READING_KEYS: dict[str, str] = {
    old: new for new, olds in OLD_READING_KEYS.items() for old in olds
}


def replaced_key_reason(key: str) -> str:
    """Return why the page does not write the old reading *key*, naming the list key."""
    new = REPLACED_READING_KEYS[key]
    return f"Replaced by {new}. Write {new} instead."


#: The flat settings of the page rules, in rule order (change local-ocr-backends, D15).
PAGE_RULE_KEYS: tuple[str, ...] = tuple(
    field.name for rule in _reading_parts.PAGE_RULES for field in rule.settings
)

#: The ordered list of local OCR backends (change local-ocr-backends, design D8).
LOCAL_BACKENDS_KEY = "ocr_local_backends"

#: The keys of Settings > Document reading, in the order of the HTTP contract.
#: The three old single-value keys left it: the list keys replace them. The page
#: rule keys come from the descriptors. The local OCR backend list comes last:
#: the page groups the rows itself, so the order here only fixes the contract.
DOCUMENT_READING_KEYS: tuple[str, ...] = (
    "pdf_readers",
    "ocr_fallback_enabled",
    "ocr_routing_unit",
    "ocr_engines",
    *PAGE_RULE_KEYS,
    LOCAL_BACKENDS_KEY,
)
_READING_BOOLEANS = frozenset({"ocr_fallback_enabled", "ocr_maths_routing_enabled"})
_READING_ENGINES = frozenset({"ocr_engine_primary", "ocr_engine_fallback"})
BLANK_RULE = "The value must not be blank. Send null to use the default."
BOOL_RULE = "The value must be true or false."


def reading_list_problem(key: str, value: Any) -> str | None:
    """Return the write rule that a reader, engine or local backend list *value* breaks.

    A list holds known names, at least one, with no repeat. A reader list may
    not hold ``auto``, because the order is the choice. An engine name follows
    :data:`ENGINE_NAME_RULE`. A local backend list follows
    :func:`local_backend_problem`. The rule never holds *value*; ``None`` means
    the value is fine.
    """
    if not isinstance(value, (list, tuple)):
        return LIST_TYPE_RULE
    if not value:
        return LIST_EMPTY_RULE
    if not all(isinstance(item, str) for item in value):
        return LIST_TYPE_RULE
    if any(not item.strip() for item in value):
        return BLANK_RULE
    if len(set(value)) != len(value):
        return LIST_DUPLICATE_RULE
    if key == "pdf_readers":
        return _reader_list_problem(value)
    if key == LOCAL_BACKENDS_KEY:
        return local_backend_problem(value, _discovered_backends())
    named = all(
        len(item) <= MAX_ENGINE_NAME_CHARS and re.fullmatch(ENGINE_NAME_PATTERN, item)
        for item in value
    )
    return None if named else ENGINE_NAME_RULE


def _discovered_backends() -> tuple[_reading_parts.LocalOcrBackendDescriptor, ...]:
    """Return the local OCR backends that compose discovered (design D11), at call time."""
    found = _reading_parts.discovered(_reading_parts.KIND_LOCAL_OCR_BACKEND)
    return tuple(d for d in found if isinstance(d, _reading_parts.LocalOcrBackendDescriptor))


def _reader_list_problem(value: Collection[str]) -> str | None:
    """Return the rule a reader list breaks: built-in names first, then discovered readers.

    With nothing discovered the rule is :data:`READER_LIST_RULE`, as before.
    """
    found = tuple(d.name for d in _reading_parts.discovered(_reading_parts.KIND_PDF_READER))
    known = (*KNOWN_READER_NAMES, *found)
    if all(item in known for item in value):
        return None
    return f"The value must be one of: {', '.join(known)}." if found else READER_LIST_RULE


def local_backend_problem(
    names: Collection[str], extra: Collection[_reading_parts.LocalOcrBackendDescriptor] = ()
) -> str | None:
    """Return the rule a local OCR backend list breaks, or ``None`` (design D8).

    Each name must name a backend descriptor with a calibrated cut. A backend
    without a cut is never an accepted value. The rule never holds a name.

    Args:
        names: The ``ocr_local_backends`` list.
        extra: More descriptors to accept beside the built-in table. Discovery
            (group 5, design D11) passes discovered backends here.

    Returns:
        The rule, with the accepted values, or ``None`` when every name is fine.
    """
    table = {d.name: d for d in (*_reading_parts.LOCAL_OCR_BACKENDS, *extra)}
    accepted = ", ".join(name for name, d in table.items() if d.min_confidence is not None)
    if not names:
        return LIST_EMPTY_RULE
    for name in names:
        if name not in table:
            return f"Each name must be a local OCR backend. Accepted values: {accepted}."
        if table[name].min_confidence is None:
            return (
                "A backend with no calibrated confidence cut cannot be listed. "
                f"Accepted values: {accepted}."
            )
    return None


def ignored_old_keys(present: Collection[str]) -> list[tuple[str, str]]:
    """Return ``(old key, list key)`` for each old key that a list key in *present* overrides.

    Within one source the list key wins (design D4), so an old key beside it is
    ignored. *present* holds the keys that one source sets.
    """
    return [
        (old, new)
        for new in READING_LIST_KEYS
        if new in present
        for old in OLD_READING_KEYS[new]
        if old in present
    ]


def document_reading_problem(key: str, value: Any) -> str | None:
    """Return the write rule that a document-reading *value* breaks, or ``None``.

    Only a page write runs this check; startup reading does not. The JSON type
    is strict: a boolean key takes ``true`` or ``false``, a list key takes an
    array of names (:func:`reading_list_problem`) and a text key takes text.
    Blank text is refused, because the writer would read it as "remove the
    key". ``None`` always passes: it removes the key. A key outside the checked
    set passes. The three old single-value keys are still checked here, because
    a Studio Read step accepts them; the settings writer refuses them on their
    own (:func:`replaced_key_reason`).

    Args:
        key: The setting key.
        value: The JSON value the page sent.

    Returns:
        The rule, which never holds *value*, or ``None`` when *value* is fine.
    """
    if value is None or not (key in DOCUMENT_READING_KEYS or key in REPLACED_READING_KEYS):
        return None
    if key in READING_LIST_KEYS or key == LOCAL_BACKENDS_KEY:
        return reading_list_problem(key, value)
    if key in _READING_BOOLEANS:
        return None if isinstance(value, bool) else BOOL_RULE
    if isinstance(value, str) and not value.strip():
        return BLANK_RULE
    if key in _READING_ENGINES:
        ok = isinstance(value, str) and len(value) <= MAX_ENGINE_NAME_CHARS
        return None if ok and re.fullmatch(ENGINE_NAME_PATTERN, value) else ENGINE_NAME_RULE
    accepted = PDF_READER_NAMES if key == "pdf_reader" else ACCEPTED[key]
    return None if value in accepted else f"The value must be one of: {', '.join(accepted)}."


WORKERS_FOLDER_RULE = (
    "The folder must be a full path to an existing folder that holds an engines folder."
)


def workers_folder_problem(key: str, value: Any) -> str | None:
    """Return the rule that an ``ocr_workers_dir`` *value* breaks, or ``None``.

    ``~`` is expanded first. The folder must be absolute, exist and hold
    ``engines/``. ``None`` and blank text pass: they remove the key. Other
    keys pass. The rule never holds *value*.
    """
    if key != "ocr_workers_dir" or value is None:
        return None
    if not isinstance(value, str):
        return WORKERS_FOLDER_RULE
    if not value.strip():
        return None
    try:
        # "~name" with an unknown user raises RuntimeError; a bad path, OSError.
        folder = Path(value.strip()).expanduser()
        ok = folder.is_absolute() and (folder / "engines").is_dir()
    except (RuntimeError, OSError):
        return WORKERS_FOLDER_RULE
    return None if ok else WORKERS_FOLDER_RULE


def address_problem(value: str) -> str | None:
    """Return the rule that address *value* breaks, or ``None`` when it is valid.

    The result never contains *value*.
    """
    if not value or len(value) > MAX_ADDRESS_CHARS:
        return ADDRESS_RULE
    if any(ord(ch) <= 0x20 or ord(ch) == 0x7F for ch in value) or "?" in value or "#" in value:
        return ADDRESS_RULE
    try:
        parts = urlsplit(value)
        parts.port  # noqa: B018 - raises ValueError on a bad port
    except ValueError:
        return ADDRESS_RULE
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ADDRESS_RULE
    if parts.username is not None or parts.password is not None:
        return ADDRESS_RULE
    return None


def accepted_problem(path: str, value: Any) -> str | None:
    """Return the rule that a choice or address *value* breaks, or ``None``.

    Paths with no choice list and no address rule always pass here (their
    type is checked elsewhere).
    """
    if path in READING_LIST_KEYS and not value:
        return LIST_EMPTY_RULE
    if path == LOCAL_BACKENDS_KEY:
        return local_backend_problem(value, _discovered_backends())
    accepted = ACCEPTED.get(path)
    if accepted is not None and value not in accepted:
        return f"The value must be one of: {', '.join(accepted)}."
    if path in ADDRESS_FIELDS and isinstance(value, str):
        return address_problem(value)
    return None


def file_only_problem(key: str, value: Any) -> str | None:
    """Return the rule that a file-only key breaks, or ``None`` when valid."""
    kind, low, high = FILE_ONLY[key]
    if kind == "bool":
        return None if isinstance(value, bool) else "The value must be true or false."
    ok = isinstance(value, int) and not isinstance(value, bool) and low <= value <= high
    return None if ok else f"The value must be a whole number from {low} to {high}."


def provider_of(field: str) -> str:
    """Return the provider name of a secret field (``openrouter_api_key`` gives ``openrouter``)."""
    return field.removesuffix("_api_key").removesuffix("_key")


# ── Provider-selection validation helper ──────────────────────────────


def _validate_provider_value(
    obj: object,
    field: str,
    accepted: tuple[str, ...],
    env_name: str,
) -> None:
    """Strip whitespace, reset empty to default, raise on unrecognised value.

    An empty or whitespace-only value (``SETTING=`` in .env) is how operators
    unset a knob, so it resets to the field's declared default rather than
    raising.  A non-empty value not in ``accepted`` raises ValueError naming
    the offending value and the accepted set.  The stripped value is stored
    so that padded input like ``" auto "`` resolves to ``"auto"``.

    Args:
        obj: The model instance owning the field (``self`` or a nested block).
        field: The field name on ``obj``.
        accepted: The recognised values.
        env_name: The environment variable name for the error message.
    """
    raw = getattr(obj, field)
    if not isinstance(raw, str):
        return
    stripped = raw.strip()
    if not stripped:
        # Empty after strip = operator unset the knob.  Reset to the
        # declared default so "" does not reach runtime code that would
        # probe it (e.g. resolve_sparse_backend on "").
        object.__setattr__(obj, field, type(obj).model_fields[field].default)
        return
    if stripped not in accepted:
        raise ValueError(
            f"{env_name}={raw!r} is not recognised. Accepted values: {', '.join(accepted)}."
        )
    # Store the stripped value so " auto " becomes "auto".
    object.__setattr__(obj, field, stripped)
