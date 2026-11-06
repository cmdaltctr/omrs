"""Decision models and document routers: named maps in ``omrs.jsonc`` (ADR-110, D1, D3).

``decision_models`` and ``document_routers`` are objects keyed by entry name::

    "decision_models": {"clef-local": {"kind": "llamacpp", "address": "...", "model": "..."}},
    "document_routers": {"handwriting": {"model": "clef-local", "question": "...",
                                         "threshold": 0.172, "images": true}}

They are file-only. No environment variable and no explicit option sets a map,
so ``Settings`` has no field for them: :class:`SettingsMapsMixin` takes the
entries that ``settings_file`` read and shows them as read-only properties.
``document_router``, the host router name, is a normal flat field.

An entry with an unknown field, a wrong type or a value that breaks its rule is
ignored and listed, and the other entries load. A key field holds a reference
only (``env://``, ``file://`` or ``keychain://``). A literal key is ignored and
listed, and the entry loads without it. No message holds a value.

This module is a leaf: it imports only ``config/`` modules that do not import it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, get_args

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    field_validator,
    model_validator,
)

from .field_rules import KIND_INVALID, KIND_RETIRED, KIND_UNKNOWN, rule_text
from .llamacpp_models import LLAMACPP_MODELS, SHIPPED_MODELS, LlamaCppModelEntry
from .rules import ENTRY_NAME_PATTERN, ENTRY_NAME_RULE, address_problem
from .user_config import REFERENCE_RULE, reference_problem

DECISION_MODELS = "decision_models"
DOCUMENT_ROUTERS = "document_routers"
#: The file-only map keys, in file order.
MAP_KEYS: tuple[str, ...] = (DECISION_MODELS, DOCUMENT_ROUTERS)

DecisionKind = Literal["llamacpp", "typesafe", "cloudflare", "ollama"]
DECISION_KINDS: tuple[str, ...] = get_args(DecisionKind)
#: The router name that means "no router". No router entry may take it.
NO_ROUTER = "none"

RESERVED_NAME_RULE = 'The name "none" means no router, so no router can take it.'
MAP_RULE = "This must be an object of named entries."
ENTRY_RULE = "Each entry must be an object of fields."
REQUIRED_RULE = "This field is required."
UNKNOWN_FIELD_RULE = "This is not a field of the entry."
BLANK_RULE = "The value must not be blank."

#: ``(kind, field, rule)``: one problem with one field of an entry.
FieldProblem = tuple[str, str, str]
#: Lists one problem: ``(kind, dotted key, rule)``, plus the replacement key for a
#: retired field. ``settings_file`` passes its reader's.
Report = Callable[..., None]


class _Entry(BaseModel):
    """Strict, frozen and closed: ``"yes"`` is not true and ``1`` is not ``1.0``-ish text."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class DecisionModelEntry(_Entry):
    """One decision model: where a System One request goes (design D1).

    Attributes:
        kind: ``llamacpp``, ``typesafe``, ``cloudflare`` or ``ollama``.
        address: Base address of the server (http or https).
        model: Model name the request names.
        images: Whether the model takes a page image.
        key: Key reference (``env://``, ``file://`` or ``keychain://``), never a key.
        server: ``llamacpp`` only: ``external`` or ``managed``. A managed entry
            names a ``llamacpp_models`` entry by ``model``; the file, the projector
            and their SHA-256 values live there (change one-llamacpp-router, D3).
    """

    kind: DecisionKind
    address: str
    model: str
    images: bool = False
    key: str | None = None
    server: Literal["external", "managed"] | None = None


class DocumentRouterEntry(_Entry):
    """One router recipe: which model judges a page, with which question (design D3).

    Attributes:
        model: Name of a ``decision_models`` entry.
        question: The question the model answers with yes or no.
        threshold: P(yes) below this rejects the page's text.
        images: Whether the page image goes with the text.
        max_chars: The page text is cut to this many characters.
        send_off_machine: The opt-in for a hosted model. Off by default.
    """

    model: str
    question: str
    threshold: float = Field(ge=0.0, le=1.0)
    images: bool = False
    max_chars: int = Field(default=2000, ge=1)
    send_off_machine: bool = False


ENTRY_TYPES: Mapping[str, type[_Entry]] = {
    DECISION_MODELS: DecisionModelEntry,
    DOCUMENT_ROUTERS: DocumentRouterEntry,
}
_TEXT_FIELDS = frozenset({"address", "model", "question"})
#: Decision entry fields that moved to ``llamacpp_models``. A file that still holds
#: one lists it as retired; the entry loads without it.
RETIRED_DECISION_FIELDS = frozenset(
    {"model_file", "projector_file", "model_sha256", "projector_sha256"}
)
MOVED_RULE = "This field moved to llamacpp_models. The model list holds the file and its SHA-256."
MOVED_TO = LLAMACPP_MODELS


def entry_name_problem(map_key: str, name: Any) -> str | None:
    """Return the rule that entry *name* of *map_key* breaks, or ``None``."""
    if not isinstance(name, str) or not ENTRY_NAME_PATTERN.fullmatch(name):
        return ENTRY_NAME_RULE
    return RESERVED_NAME_RULE if map_key == DOCUMENT_ROUTERS and name == NO_ROUTER else None


def _type_problem(entry_type: type[_Entry], field: str, error_type: str) -> str:
    if error_type == "missing":
        return REQUIRED_RULE
    info = entry_type.model_fields[field]
    choices = [item for item in get_args(info.annotation) if isinstance(item, str)]
    choices += [c for arg in get_args(info.annotation) for c in get_args(arg) if isinstance(c, str)]
    if choices:
        return f"The value must be one of: {', '.join(choices)}."
    return rule_text(info)


def _value_problem(field: str, value: Any) -> str | None:
    """Return the rule a well-typed *value* of *field* still breaks, or ``None``."""
    if not isinstance(value, str):
        return None
    if field in _TEXT_FIELDS and not value.strip():
        return BLANK_RULE
    if field == "address":
        return address_problem(value.strip())
    return None


def check_entry(
    map_key: str, data: Mapping[str, Any], secrets: Path
) -> tuple[_Entry | None, list[FieldProblem]]:
    """Check one entry of *map_key*.

    Args:
        map_key: ``decision_models`` or ``document_routers``.
        data: The entry's fields as the file holds them.
        secrets: The ``secrets/`` folder that a ``file://`` key reference must name.

    Returns:
        ``(entry, problems)``. *entry* is ``None`` when a field is broken. A
        literal key is a problem too, but the entry still loads without it.
    """
    entry_type = ENTRY_TYPES[map_key]
    fields = {str(name): value for name, value in data.items()}
    problems: list[FieldProblem] = []
    key = fields.pop("key", None) if map_key == DECISION_MODELS else None
    if key is not None and not (isinstance(key, str) and not key.strip()):
        if not isinstance(key, str) or reference_problem(key.strip(), secrets) is not None:
            problems.append((KIND_INVALID, "key", REFERENCE_RULE))
        else:
            fields["key"] = key.strip()
    for name in fields:
        if map_key == DECISION_MODELS and name in RETIRED_DECISION_FIELDS:
            problems.append((KIND_RETIRED, name, MOVED_RULE))
        elif name not in entry_type.model_fields:
            problems.append((KIND_UNKNOWN, name, UNKNOWN_FIELD_RULE))
    for name, value in fields.items():
        rule = _value_problem(name, value) if name in entry_type.model_fields else None
        if rule is not None:
            problems.append((KIND_INVALID, name, rule))
    named = {field for _, field, _ in problems}
    try:
        cleaned = {k: v.strip() if isinstance(v, str) else v for k, v in fields.items()}
        entry = entry_type.model_validate({k: v for k, v in cleaned.items() if k not in named})
    except ValidationError as exc:
        for error in exc.errors(include_input=False, include_url=False):
            field = str(error["loc"][0]) if error["loc"] else map_key
            if field not in named and field in entry_type.model_fields:
                named.add(field)
                problems.append(
                    (KIND_INVALID, field, _type_problem(entry_type, field, error["type"]))
                )
        return None, problems
    broken = any(kind != KIND_RETIRED and field != "key" for kind, field, _ in problems)
    return (None if broken else entry), problems


def read_map(map_key: str, value: Any, secrets: Path, report: Report) -> dict[str, _Entry]:
    """Return the valid entries of one map and report every problem.

    Args:
        map_key: ``decision_models`` or ``document_routers``.
        value: The map as the file holds it.
        secrets: The ``secrets/`` folder.
        report: Lists one problem as ``(kind, dotted key, rule)``.
    """
    if not isinstance(value, Mapping):
        report(KIND_INVALID, map_key, MAP_RULE)
        return {}
    found: dict[str, _Entry] = {}
    for name, data in value.items():
        path = f"{map_key}.{name}"
        rule = entry_name_problem(map_key, name)
        if rule is None and not isinstance(data, Mapping):
            rule = ENTRY_RULE
        if rule is not None:
            report(KIND_INVALID, path, rule)
            continue
        entry, problems = check_entry(map_key, data, secrets)
        for kind, field, field_rule in problems:
            extra = (MOVED_TO,) if kind == KIND_RETIRED else ()
            report(kind, f"{path}.{field}", field_rule, *extra)
        if entry is not None:
            found[name] = entry
    return found


class SettingsMapsMixin(BaseModel):
    """The host router name, and the two maps as read-only properties of ``Settings``."""

    #: The host router: a ``document_routers`` entry name. Blank means no router.
    document_router: str = ""
    _maps: dict[str, Mapping[str, Any]] = PrivateAttr(default_factory=dict)

    @field_validator("document_router")
    @classmethod
    def _strip_router(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def _take_file_maps(self) -> SettingsMapsMixin:
        """Take the maps that ``omrs.jsonc`` holds and record ``config-file`` as their source."""
        parsed = getattr(type(self), "_user_file", None)
        maps: Mapping[str, Mapping[str, Any]] = getattr(parsed, "maps", None) or {}
        self._maps = {key: dict(maps.get(key, {})) for key in MAP_KEYS}
        if LLAMACPP_MODELS in maps:  # a map in the file replaces the shipped list whole
            self._maps[LLAMACPP_MODELS] = dict(maps[LLAMACPP_MODELS])
        sources = dict(getattr(self, "setting_sources", {}))
        for key, entries in self._maps.items():
            sources.update(dict.fromkeys((f"{key}.{name}" for name in entries), "config-file"))
        object.__setattr__(self, "setting_sources", sources)
        return self

    @property
    def decision_models(self) -> Mapping[str, DecisionModelEntry]:
        """The valid ``decision_models`` entries of ``omrs.jsonc``, by name."""
        return MappingProxyType(dict(self._maps.get(DECISION_MODELS, {})))

    @property
    def llamacpp_models(self) -> Mapping[str, LlamaCppModelEntry]:
        """The router model list: the valid map of ``omrs.jsonc``, else the shipped list."""
        found = self._maps.get(LLAMACPP_MODELS)
        return MappingProxyType(dict(SHIPPED_MODELS if found is None else found))

    @property
    def document_routers(self) -> Mapping[str, DocumentRouterEntry]:
        """The valid ``document_routers`` entries of ``omrs.jsonc``, by name."""
        return MappingProxyType(dict(self._maps.get(DOCUMENT_ROUTERS, {})))
