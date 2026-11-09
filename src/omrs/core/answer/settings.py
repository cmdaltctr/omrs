"""Answer settings — pure data model, no upward imports.

Declares the configuration knobs and defaults for the ``core/answer``
subpackage (the grounded answering operation).  Consumed by the root
``Settings`` resolver in ``omrs.config``.  MUST NOT import from
``config``, ``compose``, or any other ``core/`` module (enforced by
import-linter).

Mirrors :class:`omrs.core.settings.AnswerBlock` (the frozen
``EffectiveSettings`` block); both models must stay in sync — the
MetadataSettings/MetadataBlock pair established the convention.
"""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _parse_legacy_bool(value: object) -> object:
    """Parse booleans using legacy ``.lower() == "true"`` semantics."""
    if isinstance(value, str):
        return value.lower() == "true"
    return value


LegacyBool = Annotated[bool, BeforeValidator(_parse_legacy_bool)]

#: A reasoning level: empty, or 1 to 32 letters, digits, ``-`` and ``_``.
REASONING_LEVEL_PATTERN = r"^(?:[A-Za-z0-9_-]{1,32})?$"

#: Highest seed. llama.cpp holds the seed as an unsigned 32-bit number and
#: ``-1`` means random, so 0 to 2^31 - 1 fits every provider (design D2).
SEED_MAX = 2**31 - 1
#: Highest temperature any provider takes (OpenRouter and OpenAI: 0 to 2).
TEMPERATURE_MAX = 2.0
#: One OpenRouter host: a provider name (``Fireworks``) or slug (``deepinfra/fp8``).
HOST_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/-]{0,63}$")
#: Most hosts in one allowed list.
MAX_HOSTS = 16


def normalise_hosts(value: object) -> object:
    """Return a comma-separated host list with blank entries dropped (design D11).

    Raises:
        ValueError: An entry is not a host name, or the list is too long.
    """
    if not isinstance(value, str):
        return value
    hosts = [part.strip() for part in value.split(",") if part.strip()]
    if len(hosts) > MAX_HOSTS:
        raise ValueError(f"at most {MAX_HOSTS} hosts")
    if any(not HOST_PATTERN.match(host) for host in hosts):
        raise ValueError("a host is 1 to 64 letters, digits, spaces, '.', '_', '/' or '-'")
    return ",".join(hosts)


#: An OpenRouter host list as one text value, normalised on read.
HostList = Annotated[str, BeforeValidator(normalise_hosts)]


class AnswerSettings(BaseModel):
    """Configuration knobs for the grounded answering operation.

    Every value defaults to something that works with the local-first
    provider configuration: the llama.cpp provider with no Chat model
    chosen, and client sampling preferred when the MCP client offers one.
    """

    model_config = ConfigDict(extra="forbid")

    # ── Availability ────────────────────────────────────────────────
    # When false, ``compose.build_answer_llm`` resolves to ``None`` and
    # the answering tools return an actionable error naming the setting.
    enabled: LegacyBool = True

    # ── Server-side model ───────────────────────────────────────────
    # Provider name resolved through ``core/providers/llm/registry.py``
    # (the same registry metadata extraction uses); validated at startup
    # by ``compose._resolve_active_strategies`` so a bad name fails fast.
    provider: str = "llamacpp"
    # Model handed to the provider builder via the backwards-
    # compatible ``answer_model`` override so answering never silently
    # reuses the metadata classification model. Empty means no Chat model is
    # chosen: Chat returns a setup message that names ``answer.model``
    # (change one-llamacpp-router, D14).
    model: str = ""
    # Seconds to wait for one completion round.
    timeout: float = Field(default=120.0, gt=0)

    # ── Synthesis bounds ────────────────────────────────────────────
    # COMPACT may refine across multiple completion rounds.  Rounds are
    # bounded by ``max_rounds`` (1..8; the MCP client chain is further
    # capped at the resolver-chain depth); ``context_window`` is the
    # per-round context budget in CHARACTERS (a deterministic character
    # count, not a tokenizer estimate).  When the evidence needs more
    # rounds than the bound allows, later rounds absorb the overflow
    # rather than dropping evidence.
    max_rounds: int = Field(default=4, ge=1, le=8)
    context_window: int = Field(default=8192, gt=0)
    # Reserved head-room for the model's reply inside one round's budget.
    max_output_tokens: int = Field(default=2048, gt=0)

    # ── MCP client sampling ─────────────────────────────────────────
    # Prefer the client's model (MRTR resolver on a modern session) over
    # the configured server-side model when the client advertises the
    # sampling capability.
    prefer_client_sampling: LegacyBool = True
    # Allow the deprecated ``ctx.session.create_message`` back-channel
    # ONLY on a negotiated pre-2026-07-28 session (explicit compatibility
    # mode; never attempted on a modern session).
    allow_legacy_sampling: LegacyBool = True

    # ── Claim verification (opt-in cloud judge — ADR-059) ──────────
    # Off by default: the judge needs a cloud model (experiment 20
    # showed a local 4B judge infeasible on consumer hardware),
    # which is an explicit opt-in against ADR-024's local-first policy.
    verify_claims: LegacyBool = False
    # Empty string derives the judge model from the provider's default
    # (e.g. ``openrouter_llm_model``); set to pin a specific judge.
    verify_model: str = ""
    # Alias resolved like ``metadata_llm_provider``: "cloud" (or empty)
    # → the cloud backend, "local" → the local backend, anything else
    # is a literal LLM-registry name validated at startup.
    verify_provider: str = "cloud"
    # The claim-judge strategy (pre-exp35 D10): a name in
    # core/answer/judges/registry.py, validated at startup. ``chat`` is
    # today's judge. Profile-overlaid like the verify fields above.
    verify_judge: str = "chat"

    # ── Reasoning levels (add-chat-reasoning-and-usage D4) ─────────
    # Empty sends no reasoning field, so the provider uses its own
    # default. A set level goes to every call for that role; each
    # provider maps it to its own request field (design D2).
    reasoning: str = Field(default="", pattern=REASONING_LEVEL_PATTERN)
    verify_reasoning: str = Field(default="", pattern=REASONING_LEVEL_PATTERN)

    # ── Sampling (pre-exp35-harness-and-answer-fixes D1, D11) ───────
    # Empty sends nothing, so the request stays as it was: the OpenAI-like
    # providers then send LlamaIndex's temperature 0.1. Chat and judge values
    # never mix. Each provider maps the values to its own request fields.
    temperature: float | None = Field(default=None, ge=0, le=TEMPERATURE_MAX)
    seed: int | None = Field(default=None, ge=0, le=SEED_MAX)
    verify_temperature: float | None = Field(default=None, ge=0, le=TEMPERATURE_MAX)
    verify_seed: int | None = Field(default=None, ge=0, le=SEED_MAX)
    # OpenRouter hosts, separated by commas; only OpenRouter reads them.
    allowed_hosts: HostList = ""
    verify_allowed_hosts: HostList = ""
