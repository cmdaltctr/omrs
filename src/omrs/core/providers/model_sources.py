"""Pure rules for finding and downloading local models (ADR-106, design D1, D5, D6).

Two model sources exist: Hugging Face GGUF files for llama.cpp and the
Ollama pull. This module holds only data and pure functions. It does no
network or file access. The adapters in ``integrations/`` and the routes in
``transports/api/`` call these rules before any value reaches a request or a
file path.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

ModelSourceKind = Literal["huggingface-gguf", "ollama-pull"]

#: Label of the entry that is closest to full quality (root gotcha 16).
FULL_QUALITY_LABEL = "Q8_0"
#: Label the picker preselects when the repo has it.
_DEFAULT_LABEL = "Q4_K_M"
#: Fewest bits per weight that ``preferred_label`` accepts without ``Q4_K_M``.
_MIN_PREFERRED_BITS = 4
#: Longest accepted search text.
_MAX_QUERY_CHARS = 100

_SEGMENT = re.compile(r"[A-Za-z0-9._-]{1,96}")
_LABEL = re.compile(r"[A-Za-z0-9_-]{1,64}")
_OLLAMA_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}")
_HF_PREFIX = "hf.co/"
_REVISION = re.compile(r"[0-9a-f]{40}")

_SPLIT_SUFFIX = re.compile(r"-\d{5}-of-\d{5}$")
_QUANT = (
    r"(?:UD-)?(?:IQ1_(?:S|M)|IQ2_(?:XXS|XS|S|M)|IQ3_(?:XXS|XS|S|M)|IQ4_(?:XS|NL)"
    r"|Q[2-6]_K(?:_(?:S|M|L|XL))?|Q[45]_[01]|Q8_0|TQ[12]_0|MXFP4(?:_MOE)?|BF16|F16|F32)"
)
#: The label is the end of the stem, after the start or one of ``-``, ``_``, ``.``.
_LABEL_AT_END = re.compile(rf"(?:^|[-_.])({_QUANT})$", re.IGNORECASE)
_BITS = re.compile(r"(?:IQ|TQ|Q)?(\d+)")

#: Built-in Ollama library names. Fixed data: Ollama has no public search API.
OLLAMA_LIBRARY_NAMES: tuple[str, ...] = (
    "qwen3",
    "qwen3-embedding",
    "qwen3-coder",
    "gemma3",
    "llama3.2",
    "llama3.1",
    "mistral",
    "phi4",
    "deepseek-r1",
    "nomic-embed-text",
    "mxbai-embed-large",
    "bge-m3",
    "granite-embedding",
)


def _is_segment(value: str) -> bool:
    """Return whether *value* is one safe path segment of a repo id."""
    return (
        _SEGMENT.fullmatch(value) is not None
        and not value.startswith("-")
        and value not in {".", ".."}
    )


def is_valid_repo_id(value: str) -> bool:
    """Return whether *value* is a Hugging Face repo id of the form ``org/name``.

    Each part holds letters, digits, ``.``, ``_`` and ``-``. A part never starts
    with ``-`` and is never ``.`` or ``..``.
    """
    parts = value.split("/")
    return len(parts) == 2 and all(_is_segment(part) for part in parts)


def is_valid_label(value: str) -> bool:
    """Return whether *value* is a quantisation label.

    A label holds letters, digits, ``_`` and ``-``, and never starts with ``-``.
    """
    return _LABEL.fullmatch(value) is not None and not value.startswith("-")


def is_valid_ollama_name(value: str) -> bool:
    """Return whether *value* is an Ollama model name.

    Accepted forms are ``name``, ``name:tag``, ``namespace/name:tag`` and
    ``hf.co/org/name:tag``. The tag is optional in every form.
    """
    name, _, tag = value.partition(":")
    has_tag = ":" in value
    if name.startswith(_HF_PREFIX):
        if not is_valid_repo_id(name[len(_HF_PREFIX) :]):
            return False
        return not has_tag or is_valid_label(tag)
    parts = name.split("/")
    if len(parts) > 2 or not all(_OLLAMA_PART.fullmatch(part) for part in parts):
        return False
    return not has_tag or _OLLAMA_PART.fullmatch(tag) is not None


def is_valid_query(value: str) -> bool:
    """Return whether *value* is a search text of 1 to 100 characters with no control character."""
    if not 1 <= len(value) <= _MAX_QUERY_CHARS:
        return False
    return all(unicodedata.category(char) != "Cc" for char in value)


def is_valid_revision(value: str) -> bool:
    """Return whether *value* is a full commit hash: 40 lower-case hexadecimal characters."""
    return _REVISION.fullmatch(value) is not None


def hf_model_value(repo: str, label: str) -> str:
    """Return the llama.cpp ``-hf`` model value ``repo:label``."""
    return f"{repo}:{label}"


def ollama_hf_name(repo: str, label: str) -> str:
    """Return the Ollama pull name ``hf.co/repo:label`` for a Hugging Face GGUF repo."""
    return f"{_HF_PREFIX}{repo}:{label}"


def parse_quant_label(filename: str) -> str | None:
    """Return the quantisation label of a GGUF file name, or ``None``.

    The label is the end of the file stem after any split suffix
    (``-00001-of-00002``) is removed. A ``UD-`` prefix stays part of the label.
    Projector files (``mmproj``), other file types and unknown labels give
    ``None``.

    Args:
        filename: File name or path inside a repo.

    Returns:
        The label in upper case, for example ``Q4_K_M`` or ``UD-Q4_K_XL``.
    """
    base = filename.rsplit("/", 1)[-1]
    if not base.lower().endswith(".gguf") or "mmproj" in base.lower():
        return None
    stem = _SPLIT_SUFFIX.sub("", base[: -len(".gguf")])
    found = _LABEL_AT_END.search(stem)
    return found.group(1).upper() if found else None


@dataclass(frozen=True)
class QuantEntry:
    """One downloadable choice: a label and the files that form it.

    Attributes:
        label: Quantisation label, for example ``Q4_K_M``.
        files: File paths of the entry, in name order. More than one for a split model.
        size_bytes: Sum of the file sizes.
    """

    label: str
    files: tuple[str, ...]
    size_bytes: int


def group_gguf_files(files: Iterable[tuple[str, int]]) -> list[QuantEntry]:
    """Group GGUF files into one entry per quantisation label.

    Args:
        files: ``(path, size_in_bytes)`` pairs.

    Returns:
        Entries from the smallest to the largest. Projector files and files with no
        known label are left out. Parts of a split model form one entry.
    """
    by_label: dict[str, list[tuple[str, int]]] = {}
    for path, size in files:
        label = parse_quant_label(path)
        if label is not None:
            by_label.setdefault(label, []).append((path, size))
    entries = [
        QuantEntry(
            label=label,
            files=tuple(sorted(path for path, _ in parts)),
            size_bytes=sum(size for _, size in parts),
        )
        for label, parts in by_label.items()
    ]
    return sorted(entries, key=lambda entry: (entry.size_bytes, entry.label))


def _bits(label: str) -> int:
    """Return the nominal bits per weight of a known label."""
    if label in {"BF16", "F16"}:
        return 16
    if label == "F32":
        return 32
    if label.startswith("MXFP"):
        return 4
    found = _BITS.match(label.removeprefix("UD-"))
    return int(found.group(1)) if found else 0


def preferred_label(entries: Sequence[QuantEntry]) -> str | None:
    """Return the label the picker preselects.

    ``Q4_K_M`` when present, else the smallest entry at 4 bits or more, else ``None``.
    """
    labels = {entry.label for entry in entries}
    if _DEFAULT_LABEL in labels:
        return _DEFAULT_LABEL
    big_enough = [e for e in entries if _bits(e.label) >= _MIN_PREFERRED_BITS]
    if not big_enough:
        return None
    return min(big_enough, key=lambda e: (e.size_bytes, e.label)).label


def filter_ollama_names(query: str) -> list[str]:
    """Return the built-in Ollama names that contain *query*, in list order, ignoring case."""
    needle = query.strip().lower()
    return [name for name in OLLAMA_LIBRARY_NAMES if needle in name]
