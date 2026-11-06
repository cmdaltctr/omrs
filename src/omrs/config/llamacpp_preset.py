"""Preset keys of one llama.cpp router model entry (change one-llamacpp-router, design D4).

The router reads one section per listed model from ``models.ini``. This module
holds the only keys an entry's ``preset`` may carry, each with its type and its
range. It is the single source of truth for the value types: the entry check in
``llamacpp_models`` reads :data:`PRESET_KEYS`, and the ``models.ini`` writer (task
3.3) reuses the same table to write each value.

The allow-list is closed. Any other key is refused with the reason
``preset-key-unknown``, which also covers every key the router reserves
(``host``, ``port``, ``api-key``, ``connect``, ``connect-code``, ``models-*``)
and the keys OMRS chooses never to write (``sleep-idle-seconds``, ``hf-repo``,
``log-file``, ``model-url``, ``spec-type``). A rule text names the key and the
range, never the value.

A boolean comes from a JSON boolean only. b11941 accepts any word for a boolean
key in ``models.ini`` without an error (spike 1.5), so llama.cpp cannot catch a
bad one: this module is the only check. ``embeddings`` takes ``true`` only,
because b11941 has no ``--no-embeddings``; an entry without embeddings leaves
the key out.

This module is a leaf: it imports no OMRS code.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, NamedTuple

#: The reason code of a key outside the allow-list.
PRESET_KEY_UNKNOWN = "preset-key-unknown"

PresetKind = Literal["int", "choice", "bool", "true", "int_or_choice"]


@dataclass(frozen=True)
class PresetKey:
    """One allow-listed preset key.

    Attributes:
        name: The key as ``models.ini`` spells it.
        kind: ``int`` (whole number from *low* to *high*), ``choice`` (one of
            *choices*), ``bool`` (a JSON boolean), ``true`` (the JSON value
            ``true`` only) or ``int_or_choice`` (a whole number in range, or
            one of *choices*).
        low: Smallest whole number, for the integer kinds.
        high: Largest whole number, for the integer kinds.
        choices: Accepted words, for the choice kinds.
    """

    name: str
    kind: PresetKind
    low: int = 0
    high: int = 0
    choices: tuple[str, ...] = ()


def _int(name: str, low: int, high: int) -> PresetKey:
    return PresetKey(name, "int", low, high)


def _choice(name: str, *choices: str) -> PresetKey:
    return PresetKey(name, "choice", choices=choices)


_KEYS: tuple[PresetKey, ...] = (
    _int("ctx-size", 512, 262_144),
    _int("batch-size", 32, 65_536),
    _int("ubatch-size", 32, 65_536),
    _int("parallel", 1, 16),
    PresetKey("embeddings", "true"),
    _choice("pooling", "none", "mean", "cls", "last", "rank"),
    _int("embd-normalize", -1, 2),
    PresetKey("kv-unified", "bool"),
    _choice("flash-attn", "on", "off", "auto"),
    PresetKey("n-gpu-layers", "int_or_choice", 0, 999, ("all", "auto")),
    _choice("fit", "on", "off"),
    # A deliberate subset: b11941 also accepts q4_1, iq4_nl, q5_0 and q5_1. Adding
    # one needs a code change and a test, like any key.
    _choice("cache-type-k", "f32", "f16", "bf16", "q8_0", "q4_0"),
    _choice("cache-type-v", "f32", "f16", "bf16", "q8_0", "q4_0"),
    PresetKey("cache-prompt", "bool"),
    _int("cache-reuse", 0, 65_536),
    _int("image-min-tokens", 1, 65_536),
    _int("image-max-tokens", 1, 65_536),
)

#: The allow-list, by key name, in the order of design D4.
PRESET_KEYS: Mapping[str, PresetKey] = {key.name: key for key in _KEYS}

OBJECT_RULE = "The preset must be an object of preset keys."
UBATCH_RULE = "ubatch-size must not be larger than batch-size."


class PresetProblem(NamedTuple):
    """One problem with one preset key.

    Attributes:
        key: The preset key, as the file spells it.
        rule: A plain-English rule. It never holds the submitted value.
        reason: ``preset-key-unknown`` when the key is outside the allow-list,
            else ``None``.
    """

    key: str
    rule: str
    reason: str | None


def _is_whole(value: Any) -> bool:
    """Return whether *value* is a JSON whole number (a boolean is not one)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _quoted(words: tuple[str, ...]) -> str:
    return ", ".join(words)


def preset_value_problem(key: PresetKey, value: Any) -> str | None:
    """Return the rule that *value* breaks for *key*, or ``None`` when it is fine.

    Args:
        key: An entry of :data:`PRESET_KEYS`.
        value: The JSON value as the file or the page holds it.

    Returns:
        The rule, which never holds *value*.
    """
    span = f"from {key.low} to {key.high}"
    if key.kind == "bool":
        return None if isinstance(value, bool) else f"{key.name} must be true or false."
    if key.kind == "true":
        return None if value is True else f"{key.name} must be true. To turn it off, leave it out."
    if key.kind == "choice":
        ok = isinstance(value, str) and value in key.choices
        return None if ok else f"{key.name} must be one of: {_quoted(key.choices)}."
    if key.kind == "int":
        ok = _is_whole(value) and key.low <= value <= key.high
        return None if ok else f"{key.name} must be a whole number {span}."
    in_range = _is_whole(value) and key.low <= value <= key.high
    if in_range or (isinstance(value, str) and value in key.choices):
        return None
    return f"{key.name} must be a whole number {span}, or one of: {_quoted(key.choices)}."


def preset_problems(preset: Any) -> list[PresetProblem]:
    """Return every problem of a ``preset`` object, in key order.

    A key outside the allow-list gives the reason ``preset-key-unknown`` and no
    value check. ``ubatch-size`` larger than ``batch-size`` is a problem of
    ``ubatch-size`` when both are well-formed.

    Args:
        preset: The submitted ``preset`` value.

    Returns:
        The problems. An empty list means the preset is fine.
    """
    if not isinstance(preset, Mapping):
        return [PresetProblem("preset", OBJECT_RULE, None)]
    found: list[PresetProblem] = []
    for name, value in preset.items():
        key = PRESET_KEYS.get(name) if isinstance(name, str) else None
        if key is None:
            found.append(
                PresetProblem(
                    str(name), "This is not a preset key of the router list.", PRESET_KEY_UNKNOWN
                )
            )
            continue
        rule = preset_value_problem(key, value)
        if rule is not None:
            found.append(PresetProblem(key.name, rule, None))
    broken = {problem.key for problem in found}
    batch, ubatch = preset.get("batch-size"), preset.get("ubatch-size")
    if (
        not broken & {"batch-size", "ubatch-size"}
        and _is_whole(batch)
        and _is_whole(ubatch)
        and ubatch > batch
    ):
        found.append(PresetProblem("ubatch-size", UBATCH_RULE, None))
    return found
