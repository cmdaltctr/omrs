"""The claim-judge protocol, its call record and the injected resources (design D10).

A judge takes one claim and the evidence texts it cites and returns a
:class:`Judgement`: the verdict and a :class:`JudgeCall` that records what
produced it. The record holds no claim text, no evidence text and no key.

The composition root builds a :class:`JudgeResources` with only the
transport parts a strategy names in its module-level ``NEEDS`` tuple, so a
strategy imports no provider and no top-level ``omrs`` module.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

#: The strategy an empty ``answer.verify_judge`` means (today's judge).
DEFAULT_JUDGE = "chat"

#: The keys of every call record's ``settings`` (``None`` when not used).
SETTING_KEYS = ("temperature", "seed", "reasoning", "threshold", "think")


class JudgeUnavailable(Exception):  # noqa: N818 - reads as a state, like ModelUnavailable
    """The judge cannot start. The text is a fixed reason, never request or reply text."""

    def __init__(self, reason: str) -> None:
        """Carry the fixed *reason*."""
        super().__init__(reason)
        self.reason = reason


class JudgeRequestFailed(Exception):  # noqa: N818 - matches RuntimeRequestFailed
    """The request for one claim failed. The text is a fixed reason (``unreachable``)."""

    def __init__(self, reason: str) -> None:
        """Carry the fixed *reason*."""
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class JudgeCall:
    """What produced one verdict (spec ``claim-judge-strategies``).

    Attributes:
        strategy: The registered strategy name.
        model: The model id the call named.
        host: The host a hosted reply names, else ``None``.
        sha256: The SHA-256 of the local GGUF file, else ``None``.
        version: The prompt-format version of the strategy.
        settings: The call settings, one value per :data:`SETTING_KEYS`.
        p_yes: P(yes) of a decision model, else ``None``.
        error: A fixed reason when the request for this claim failed.
    """

    strategy: str
    model: str
    host: str | None
    sha256: str | None
    version: str
    settings: Mapping[str, Any]
    p_yes: float | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the record as the answer result's ``judge_calls`` entry."""
        return {
            "strategy": self.strategy,
            "model": self.model,
            "host": self.host,
            "sha256": self.sha256,
            "version": self.version,
            "settings": {key: self.settings.get(key) for key in SETTING_KEYS},
            "p_yes": self.p_yes,
            "error": self.error,
        }


@dataclass(frozen=True)
class Judgement:
    """One verdict and the record of the call that produced it."""

    verdict: str
    call: JudgeCall | None = None


@runtime_checkable
class ClaimJudge(Protocol):
    """Judges one claim against the evidence texts it cites."""

    name: str
    version: str

    async def judge(self, claim: str, evidence_texts: Sequence[str]) -> Judgement:
        """Return the verdict for *claim*.

        Raises:
            JudgeUnavailable: The judge cannot start; nothing was sent.
        """
        ...


def _no_facts() -> Mapping[str, Any]:
    return {}


@dataclass(frozen=True)
class JudgeResources:
    """What the composition root injects into a strategy's ``build``.

    Attributes:
        model: The model id the judge names (``answer.verify_model``).
        settings: Call settings the strategy reports (temperature, seed, reasoning).
        complete: Chat seam: prompt in, reply text out.
        decide: Decision call: ``(question, state text)`` in, P(yes) out,
            ``None`` for a reply without a usable P(yes). Raises
            :class:`JudgeRequestFailed` when the request fails.
        generate: Raw completion: ``(prompt, options)`` in, generated text
            out. Raises :class:`JudgeRequestFailed` when the request fails.
        call_facts: Facts of the latest call (``host``, ``sha256``,
            ``temperature``, ``seed``), read after the call.
        refusal: A fixed reason the judge cannot start, else ``None``.
    """

    model: str = ""
    settings: Mapping[str, Any] = field(default_factory=dict)
    complete: Callable[[str], Awaitable[str]] | None = None
    decide: Callable[[str, str], Awaitable[float | None]] | None = None
    generate: Callable[[str, Mapping[str, Any]], Awaitable[str]] | None = None
    call_facts: Callable[[], Mapping[str, Any]] = _no_facts
    refusal: str | None = None


def make_call(
    strategy: str,
    version: str,
    resources: JudgeResources,
    *,
    settings: Mapping[str, Any] | None = None,
    p_yes: float | None = None,
    error: str | None = None,
) -> JudgeCall:
    """Return the record of one call.

    *settings* replaces ``resources.settings`` when given. The latest call's
    facts (``temperature`` and ``seed`` read from the built model) override both.
    """
    facts = resources.call_facts()
    settings = dict(resources.settings if settings is None else settings)
    settings.update({key: facts[key] for key in ("temperature", "seed") if key in facts})
    return JudgeCall(
        strategy=strategy,
        model=resources.model,
        host=facts.get("host"),
        sha256=facts.get("sha256"),
        version=version,
        settings=settings,
        p_yes=p_yes,
        error=error,
    )


def shared_error(calls: Sequence[JudgeCall | None]) -> str | None:
    """Return the skip reason when every call failed with one fixed error, else ``None``."""
    errors = {(call.strategy, call.error) if call is not None else None for call in calls}
    if len(errors) != 1:
        return None
    only = errors.pop()
    if only is None or only[1] is None:
        return None
    return f"claim judge {only[0]} could not run: {only[1]}"
