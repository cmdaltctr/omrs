"""The llama.cpp router model list: ``llamacpp_models`` in ``omrs.jsonc`` (one-llamacpp-router, D3).

``llamacpp_models`` is a named map keyed by a short id::

    "llamacpp_models": {"qwen3-4b": {"model": "Qwen/Qwen3-4B-GGUF:Q8_0",
                                     "file": "/m/Qwen3-4B-Q8_0.gguf",
                                     "preset": {"ctx-size": 32768, "parallel": 2}}}

It is file-only, like ``decision_models``: no environment variable sets it, and
only ``omrs web`` writes it. A user map replaces the shipped list as a whole.
With no map in the file, :data:`SHIPPED_MODELS` is the list (design D11). An
entry with a broken field is ignored and listed, and the other entries load. No
message holds a value.

This module only checks. The ``models.ini`` writer (task 3.3) and the launch
checks of a file (hash, build) belong to later groups. A file that no longer
exists is a launch-time failure of that entry, so :func:`read_model_map` does not
touch the disk; :func:`file_problem` does when asked.

This module is a leaf: it imports only ``config/`` modules that do not import it.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any, NamedTuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .field_rules import KIND_INVALID, KIND_UNKNOWN, rule_text
from .llamacpp_preset import PRESET_KEY_UNKNOWN, preset_problems

LLAMACPP_MODELS = "llamacpp_models"
#: Models of the shipped list (design D11). The role settings default to them.
EMBED_MODEL = "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0"
CLASSIFY_MODEL = "Qwen/Qwen3-4B-GGUF:Q8_0"

#: The reason code of an embedding entry that breaks its preset rule.
PRESET_INVALID = "preset-invalid"

#: An entry id: 1 to 40 characters from ``a-z``, ``0-9`` and ``-``.
ID_PATTERN = re.compile(r"[a-z0-9-]{1,40}")
ID_RULE = "An id must be 1 to 40 characters from a-z, 0-9 and hyphen."
#: A Hugging Face id with a required quantisation tag. ``config/`` cannot import
#: ``integrations/``, so a test pins this to ``llamacpp_runtime.rules._HF_ID``.
MODEL_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,95}:[A-Za-z0-9._-]{1,64}"
)
MODEL_RULE = "The model must be a Hugging Face id with a quantisation tag, such as org/name:Q8_0."
FILE_RULE = "The file must be an absolute path of a .gguf file. Its name must not hold mmproj."
PROJECTOR_RULE = "The projector must be an absolute path of a .gguf file."
FILE_MISSING_RULE = "The file must be an existing regular file."
SHA256_RULE = "The value must be 64 lower-case hexadecimal characters."
MAP_RULE = "This must be an object of named entries."
ENTRY_RULE = "Each entry must be an object of fields."
REQUIRED_RULE = "This field is required."
UNKNOWN_FIELD_RULE = "This is not a field of the entry."
DUPLICATE_RULE = "Another entry already lists this model."

_SHA256 = re.compile(r"[0-9a-f]{64}")
_MAX_PATH_CHARS = 2048

#: Lists one problem: ``(kind, dotted key, rule)``. ``settings_file`` passes its reader's.
Report = Callable[[str, str, str], None]


class EntryProblem(NamedTuple):
    """One problem with one field of an entry.

    Attributes:
        kind: ``invalid`` or ``unknown`` (the kinds of ``field_rules``).
        field: The field, ``preset.<key>`` for a preset key.
        rule: A plain-English rule. It never holds a value.
        reason: A fixed reason code (``preset-key-unknown``) or ``None``.
    """

    kind: str
    field: str
    rule: str
    reason: str | None = None


class LlamaCppModelEntry(BaseModel):
    """One listed model: what the router serves under one name (design D3).

    Attributes:
        model: Request name and preset section name, ``org/name:QUANT``.
        file: Absolute path of the GGUF file. Blank until the model is downloaded.
        projector: Absolute path of the projector file, for an image model.
        sha256: SHA-256 of the file, recorded when the entry is added.
        projector_sha256: SHA-256 of the projector file.
        preset: Allow-listed preset keys (``llamacpp_preset``).
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    model: str
    file: str | None = None
    projector: str | None = None
    sha256: str | None = None
    projector_sha256: str | None = None
    preset: dict[str, Any] = Field(default_factory=dict)


#: The shipped list: the code default of ``llamacpp_models`` (design D11). Both
#: entries have no file, so each shows "Not downloaded" until it downloads.
SHIPPED_MODELS: Mapping[str, LlamaCppModelEntry] = MappingProxyType(
    {
        "qwen3-embedding-4b": LlamaCppModelEntry(
            model=EMBED_MODEL,
            preset={
                "embeddings": True,
                "pooling": "last",
                "embd-normalize": 2,
                "ctx-size": 8192,
                "batch-size": 8192,
                "ubatch-size": 8192,
                "parallel": 1,
                "kv-unified": False,
            },
        ),
        "qwen3-4b": LlamaCppModelEntry(
            model=CLASSIFY_MODEL, preset={"ctx-size": 32768, "parallel": 2}
        ),
    }
)


def file_problem(path: str, *, projector: bool = False, exists: bool = False) -> str | None:
    """Return the rule that *path* breaks as a model file or projector, or ``None``.

    The path must be absolute, short, free of NUL and end in ``.gguf``. A model
    file name must also hold no ``mmproj``, so a projector cannot stand in for a
    model. With *exists* the file must be a regular file on disk now; reading
    ``omrs.jsonc`` does not ask for it, because a missing file fails that entry
    at launch only.

    Args:
        path: The file path as saved.
        projector: Whether *path* is a projector file.
        exists: Whether to check the disk too.

    Returns:
        The rule, which never holds *path*.
    """
    rule = PROJECTOR_RULE if projector else FILE_RULE
    if not path or len(path) > _MAX_PATH_CHARS or "\x00" in path or not os.path.isabs(path):
        return rule
    name = os.path.basename(path).lower()
    if not name.endswith(".gguf") or (not projector and "mmproj" in name):
        return rule
    return FILE_MISSING_RULE if exists and not os.path.isfile(path) else None


def _value_problem(field: str, value: str) -> str | None:
    """Return the rule a well-typed text *value* of *field* still breaks, or ``None``."""
    if field == "model":
        return None if MODEL_PATTERN.fullmatch(value) else MODEL_RULE
    if field in ("file", "projector"):
        return file_problem(value, projector=field == "projector")
    if field in ("sha256", "projector_sha256"):
        return None if _SHA256.fullmatch(value) else SHA256_RULE
    return None


def check_model_entry(
    data: Mapping[str, Any],
) -> tuple[LlamaCppModelEntry | None, list[EntryProblem]]:
    """Check one entry of ``llamacpp_models``.

    Args:
        data: The entry's fields as the file or the page holds them.

    Returns:
        ``(entry, problems)``. *entry* is ``None`` when a field is broken.
    """
    fields = {str(name): value for name, value in data.items()}
    problems: list[EntryProblem] = []
    for name in fields:
        if name not in LlamaCppModelEntry.model_fields:
            problems.append(EntryProblem(KIND_UNKNOWN, name, UNKNOWN_FIELD_RULE))
    for name, value in fields.items():
        if name in LlamaCppModelEntry.model_fields and isinstance(value, str):
            rule = _value_problem(name, value.strip())
            if rule is not None:
                problems.append(EntryProblem(KIND_INVALID, name, rule))
    if "preset" in fields:
        for key, rule, reason in preset_problems(fields["preset"]):
            kind = KIND_UNKNOWN if reason == PRESET_KEY_UNKNOWN else KIND_INVALID
            field = "preset" if key == "preset" else f"preset.{key}"
            problems.append(EntryProblem(kind, field, rule, reason))
    named = {problem.field.partition(".")[0] for problem in problems}
    try:
        cleaned = {k: v.strip() if isinstance(v, str) else v for k, v in fields.items()}
        entry = LlamaCppModelEntry.model_validate(
            {k: v for k, v in cleaned.items() if k not in named}
        )
    except ValidationError as exc:
        for error in exc.errors(include_input=False, include_url=False):
            field = str(error["loc"][0]) if error["loc"] else "entry"
            if field in named:
                continue
            named.add(field)
            info = LlamaCppModelEntry.model_fields.get(field)
            rule = (
                REQUIRED_RULE
                if error["type"] == "missing"
                else rule_text(info)
                if info is not None
                else ENTRY_RULE
            )
            problems.append(EntryProblem(KIND_INVALID, field, rule))
        return None, problems
    return (None if problems else entry), problems


def embedding_preset_problem(entry: LlamaCppModelEntry) -> str | None:
    """Return the rule that an embedding use of *entry* breaks, or ``None``.

    An entry used for embeddings must set ``embeddings`` to true and set
    ``pooling``, ``ctx-size``, ``batch-size`` and ``ubatch-size`` (reason
    ``preset-invalid``). The size ordering is a general preset rule.
    """
    preset = entry.preset
    if preset.get("embeddings") is not True:
        return "An embedding entry must set embeddings to true."
    missing = [k for k in ("pooling", "ctx-size", "batch-size", "ubatch-size") if k not in preset]
    return f"An embedding entry must set {', '.join(missing)}." if missing else None


def read_model_map(value: Any, report: Report) -> dict[str, LlamaCppModelEntry] | None:
    """Return the valid entries of the file's ``llamacpp_models`` and report every problem.

    Args:
        value: The map as the file holds it.
        report: Lists one problem as ``(kind, dotted key, rule)``.

    Returns:
        The valid entries in file order, or ``None`` when *value* is not an
        object, so the shipped list stays in force.
    """
    if not isinstance(value, Mapping):
        report(KIND_INVALID, LLAMACPP_MODELS, MAP_RULE)
        return None
    found: dict[str, LlamaCppModelEntry] = {}
    listed: set[str] = set()
    for name, data in value.items():
        path = f"{LLAMACPP_MODELS}.{name}"
        rule = None
        if not isinstance(name, str) or not ID_PATTERN.fullmatch(name):
            rule = ID_RULE
        elif not isinstance(data, Mapping):
            rule = ENTRY_RULE
        if rule is not None:
            report(KIND_INVALID, path, rule)
            continue
        entry, problems = check_model_entry(data)
        for kind, field, field_rule, _ in problems:
            report(kind, f"{path}.{field}", field_rule)
        if entry is None:
            continue
        if entry.model in listed:
            report(KIND_INVALID, f"{path}.model", DUPLICATE_RULE)
            continue
        listed.add(entry.model)
        found[name] = entry
    return found
