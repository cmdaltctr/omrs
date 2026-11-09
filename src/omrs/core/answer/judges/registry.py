"""Lazy registry of claim-judge strategies (design D10, root invariant 11).

Maps a strategy name to its module path. ``get()`` imports the module on
first use. Adding a strategy is one new file plus one ``register()`` line at
the bottom. A strategy module defines:

- ``VERSION``: the prompt-format version its call records carry;
- ``NEEDS``: the :class:`~omrs.core.answer.judges.base.JudgeResources`
  parts it uses (``complete``, ``decide`` or ``generate``);
- ``LOCAL_MODEL``: whether its model is a llama.cpp router model;
- ``build(resources)``: returns the strategy's
  :class:`~omrs.core.answer.judges.base.ClaimJudge`.

The same shape as ``core/providers/decision/registry.py``.
"""

from __future__ import annotations

import importlib
from dataclasses import replace
from types import ModuleType

_registry: dict[str, str] = {}
_cache: dict[str, ModuleType] = {}


def register(name: str, module_path: str) -> None:
    """Register claim-judge strategy *name*, served by the module at *module_path*."""
    _registry[name] = module_path
    _cache.pop(name, None)


def get(name: str) -> ModuleType:
    """Return the module of strategy *name*.

    Raises:
        KeyError: *name* is not registered. The message names the registered strategies.
    """
    if name in _cache:
        return _cache[name]
    if name not in _registry:
        raise KeyError(f"Unknown claim judge {name!r}. Registered: {', '.join(names())}.")
    module = importlib.import_module(_registry[name])
    _cache[name] = module
    return module


def names() -> list[str]:
    """Return the sorted registered strategy names."""
    return sorted(_registry)


def ignored_sampling(name: str) -> tuple[str, ...]:
    """Return the sampling values strategy *name* sends nothing for.

    A strategy module declares them as ``IGNORED_SAMPLING``. A strategy
    without the attribute, or an unknown name, ignores nothing.
    """
    try:
        module = get(name)
    except KeyError:
        return ()
    return tuple(getattr(module, "IGNORED_SAMPLING", ()))


def as_judge(target: object, block: object = None, facts: object = None) -> object:
    """Return *target* when it is a claim judge, else the default strategy over the seam.

    A plain async seam (prompt in, reply out) is today's judge, so callers that
    inject a seam keep their prompt, parsing and verdicts (spec, "Default unchanged").
    With an answer *block*, the call record carries its judge model and settings;
    *facts* (a callable) adds the host and the sent values of the latest call.
    """
    from .base import DEFAULT_JUDGE, ClaimJudge, JudgeResources

    if isinstance(target, ClaimJudge):
        return target
    settings = {
        "temperature": getattr(block, "verify_temperature", None),
        "seed": getattr(block, "verify_seed", None),
        "reasoning": str(getattr(block, "verify_reasoning", "") or "") or None,
    }
    model = str(getattr(block, "verify_model", "") or "")
    resources = JudgeResources(model=model, settings=settings, complete=target)  # type: ignore[arg-type]
    if callable(facts):
        resources = replace(resources, call_facts=facts)
    return get(DEFAULT_JUDGE).build(resources)


# ── Built-in strategies ─────────────────────────────────────────────────
register("chat", "omrs.core.answer.judges.chat")
register("clef_flash", "omrs.core.answer.judges.clef_flash")
register("granite_guardian", "omrs.core.answer.judges.granite_guardian")
