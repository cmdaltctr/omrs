"""Build the claim judge that ``answer.verify_judge`` names (pre-exp35 design D10).

The strategies in ``core/answer/judges/`` import no provider. This module
gives each one the transport its ``NEEDS`` names:

- ``complete`` (the ``chat`` strategy): the judge LLM that
  :func:`omrs.compose_answer.build_verify_llm` builds, unchanged. The call
  record reads the host, temperature and seed of the latest reply.
- ``decide`` (``clef_flash``): one ``noul`` question to ``/v1/systemone``
  through the ``llamacpp`` decision adapter and the router lease. A model
  file below 8-bit is refused before any request (root gotcha 16).
- ``generate`` (``granite_guardian``): one raw completion to the router's
  ``/v1/completions`` through the router lease.

A judge that cannot start keeps a fixed reason, so the answer reports
``verification_skipped`` and sends no claim request. The SHA-256 of a local
model file is read from the router's ``hashes.json`` (ADR-115), never
computed here. Logs hold fixed reasons only: never claim, evidence or reply text.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from .core.answer.judges import registry
from .core.answer.judges.base import DEFAULT_JUDGE, JudgeRequestFailed, JudgeResources

logger = logging.getLogger(__name__)

#: Seconds one local judge request may take (the decision checks use 120 s too).
REQUEST_TIMEOUT = 120.0
NO_MODEL = "no-model"
MODEL_NOT_LISTED = "model-not-listed"
UNREACHABLE = "unreachable"
REQUEST_FAILED = "request-failed"


def judge_name(block: Any) -> str:
    """Return the strategy *block* names; empty (or not text) means the default (``chat``)."""
    value = getattr(block, "verify_judge", "")
    return (value.strip() if isinstance(value, str) else "") or DEFAULT_JUDGE


def validate_verify_judge(settings: Any) -> None:
    """Fail fast at startup on an unknown ``answer.verify_judge`` (spec: unknown strategy).

    Raises:
        ValueError: The name is not registered. The message names every strategy.
    """
    name = judge_name(settings.answer)
    if name not in registry.names():
        raise ValueError(
            f"ANSWER__VERIFY_JUDGE={name!r} is not a registered claim judge. "
            f"Registered: {', '.join(registry.names())}."
        )


def uses_llm(block: Any) -> bool:
    """Return whether the strategy *block* names judges through a chat LLM.

    Raises:
        ValueError: The name is not registered.
    """
    try:
        return "complete" in registry.get(judge_name(block)).NEEDS
    except KeyError as unknown:
        raise ValueError(str(unknown).strip("'\"")) from None


def build_judge_target(
    settings: Any, answer_block: Any, *, transport: httpx.BaseTransport | None = None
) -> Any:
    """Return the judge of *answer_block*: an LLM for a chat strategy, else a claim judge.

    A strategy that needs ``complete`` gets the LLM from ``build_verify_llm``
    (its errors stay loud, ADR-059). A typed strategy is built here; when it
    cannot start it keeps a fixed reason and sends nothing.

    Returns:
        ``None`` when claim checks are off, else the LLM or the claim judge.
    """
    module = registry.get(judge_name(answer_block))
    if "complete" in module.NEEDS:
        from .compose_answer import build_verify_llm

        return build_verify_llm(settings, answer_block=answer_block)
    if not (
        getattr(answer_block, "enabled", True) and getattr(answer_block, "verify_claims", False)
    ):
        return None
    if settings is None:  # the CLI: the settings in force, with the saved web values
        from .compose_runtimes import current_settings

        settings = current_settings()
    return module.build(local_resources(module, settings, answer_block, transport))


def strategy_ready(settings: Any, name: str, block: Any) -> str | None:
    """Return why strategy *name* cannot run on this host, or ``None`` (Studio, task 8.3a).

    Sends nothing and starts nothing. A strategy whose model runs on the
    llama.cpp router needs ``answer.verify_model`` and a ``llamacpp_models``
    entry of that name. A chat strategy is ready: the Judge panel reports
    its own readiness, and an empty model can mean the provider default.
    """
    if name not in registry.names():
        return f"No claim judge of this name is registered ({', '.join(registry.names())})."
    if not registry.get(name).LOCAL_MODEL:
        return None
    model = str(getattr(block, "verify_model", "") or "").strip()
    if not model:
        return f"{name} needs a judge model. Set answer.verify_model in Settings > Chat."
    if _listed(settings, model) is None:
        return (
            f"{name} needs a llama.cpp model, and the router lists no model named "
            f"{model!r} (answer.verify_model). Add it in Settings > Local models, "
            "or change the judge model."
        )
    return None


class JudgeReasons(Mapping[str, str]):
    """Strategy names this host cannot run, and why (the ``verify_judge`` option set).

    Iteration lists the registered strategies that are not ready. A lookup
    also refuses a name the registry does not hold, so admission refuses it.
    """

    def __init__(self, settings: Any) -> None:
        """Work out the not-ready strategies now; nothing is sent."""
        block = settings.answer
        self._settings, self._block = settings, block
        self._known = {
            name: reason
            for name in registry.names()
            if (reason := strategy_ready(settings, name, block)) is not None
        }

    def __getitem__(self, name: str) -> str:
        """Return why *name* cannot run; ``KeyError`` when it can."""
        if name in self._known:
            return self._known[name]
        reason = strategy_ready(self._settings, name, self._block)
        if reason is None:
            raise KeyError(name)
        return reason

    def __iter__(self) -> Any:
        """Iterate over the registered strategies that are not ready."""
        return iter(self._known)

    def __len__(self) -> int:
        """Return how many registered strategies are not ready."""
        return len(self._known)


def judge_option_set(settings: Any) -> Any:
    """Return the host option set of the Verify claims step's ``verify_judge``."""
    from .core.pipelines import HostOptionSet

    remedy = "Set the judge model up on this host, or choose another judge or Inherit."
    return HostOptionSet(judge_name(settings.answer), JudgeReasons(settings), remedy)


def judge_save_problem(settings: Any, graph: Mapping[str, Any]) -> str | None:
    """Return why a graph's claim-judge choice cannot be saved on this host, or ``None``.

    Checks each ``verify.claims`` step's ``verify_judge`` and a graph override
    of ``answer.verify_judge``. An empty choice inherits and always saves.
    """
    chosen = [graph.get("overrides", {}).get("answer.verify_judge")]
    for node in graph.get("nodes", ()):
        if node.get("operation") == "verify.claims":
            chosen.append((node.get("params") or {}).get("verify_judge"))
    for name in chosen:
        if name is None:
            continue
        reason = strategy_ready(settings, str(name), settings.answer)
        if reason is not None:
            return f"The claim judge {name!r} cannot be saved on this host: {reason}"
    return None


# ── Typed strategies: the router transports ─────────────────────────────


def _field(entry: Any, name: str) -> Any:
    return entry.get(name) if isinstance(entry, Mapping) else getattr(entry, name, None)


def _listed(settings: Any, model: str) -> Any:
    models = (getattr(settings, "llamacpp_models", None) or {}).values()
    return next((item for item in models if _field(item, "model") == model), None)


def cached_sha256(path: str | None) -> str | None:
    """Return the SHA-256 of *path* from the router's ``hashes.json``, or ``None``.

    The value counts only while the file's size and ``mtime_ns`` still match.
    Nothing is hashed and nothing is written.
    """
    if not path:
        return None
    from .compose_runtime_manager import runtime_manager
    from .integrations.llamacpp_runtime.router_spec import HASHES_FILE, router_dir

    try:
        items = json.loads((router_dir(runtime_manager().root) / HASHES_FILE).read_text("utf-8"))
        info = os.stat(path)
    except (OSError, ValueError):
        return None
    item = items.get(path) if isinstance(items, dict) else None
    if not isinstance(item, dict) or not isinstance(item.get("sha256"), str):
        return None
    if (item.get("size"), item.get("mtime_ns")) != (info.st_size, info.st_mtime_ns):
        return None
    return str(item["sha256"])


def _refusal(module: Any, settings: Any, model: str, listed: Any) -> str | None:
    """Return the fixed reason a typed judge cannot start, or ``None``."""
    if not model:
        return NO_MODEL
    if listed is None:
        return MODEL_NOT_LISTED
    if getattr(module, "EIGHT_BIT_CHECK", False) and _field(listed, "file"):
        from .core.providers.decision import checks

        if checks.quantisation_from_file(str(_field(listed, "file"))).status == checks.REFUSED:
            return checks.QUANTISATION_REFUSED
    return None


def local_resources(
    module: Any, settings: Any, block: Any, transport: httpx.BaseTransport | None = None
) -> JudgeResources:
    """Return the resources of a typed strategy: router transports and the file's SHA-256."""
    from .compose_runtimes import router_lease_for

    model = str(getattr(block, "verify_model", "") or "").strip()
    listed = _listed(settings, model) if model else None
    refusal = _refusal(module, settings, model, listed)
    lease: Any = None
    if refusal is None:
        lease = router_lease_for(settings)
        refusal = lease if isinstance(lease, str) else None
    sha256 = cached_sha256(_field(listed, "file")) or _field(listed, "sha256")
    values = {
        "temperature": getattr(block, "verify_temperature", None),
        "seed": getattr(block, "verify_seed", None),
    }
    sender = RouterSender(lease, model, transport) if refusal is None else None
    return JudgeResources(
        model=model,
        settings=values,
        decide=sender.decide if sender and "decide" in module.NEEDS else None,
        generate=sender.generate if sender and "generate" in module.NEEDS else None,
        call_facts=lambda: {"sha256": sha256},
        refusal=refusal,
    )


def _failure(error: Exception) -> str:
    """Return the fixed reason of a failed local request; never the error text."""
    reason = getattr(error, "reason", None)
    if isinstance(reason, str) and reason:
        return reason
    return UNREACHABLE if isinstance(error, httpx.TransportError) else REQUEST_FAILED


class RouterSender:
    """Send typed-judge requests for one router model through the router lease."""

    def __init__(self, lease: Any, model: str, transport: httpx.BaseTransport | None) -> None:
        """Keep the lease, the model name and an optional ``httpx`` transport (tests)."""
        self._lease, self._model, self._transport = lease, model, transport

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        def send(address: str) -> Any:
            url = address.rstrip("/").removesuffix("/v1") + path
            with httpx.Client(transport=self._transport, timeout=REQUEST_TIMEOUT) as client:
                response = client.post(url, json=body)
                response.raise_for_status()
                return response.json()

        return self._lease.request_model(self._model, send)

    async def _ask(self, path: str, body: dict[str, Any]) -> Any:
        try:
            return await asyncio.to_thread(self._post, path, body)
        except (ValueError, json.JSONDecodeError):
            return None  # an unreadable body is an unreadable reply
        except Exception as error:  # noqa: BLE001 - any request failure is one fixed reason
            reason = _failure(error)
            logger.warning("A claim judge request failed: %s.", reason)
            raise JudgeRequestFailed(reason) from None

    async def decide(self, question: str, text: str) -> float | None:
        """Return P(yes) for one ``noul`` question, ``None`` for an unreadable reply."""
        from .core.providers.decision import base
        from .core.providers.decision import registry as decision_registry

        adapter = decision_registry.get("llamacpp")
        request = adapter.build_request(
            address="", model=self._model, question=question, text=text, image=None,
            key=None, hosted=False,
        )  # fmt: skip
        reply = await self._ask(base.SYSTEMONE_PATH, request.body)
        try:
            return float(adapter.read_reply(reply))
        except base.MalformedReplyError:
            return None

    async def generate(self, prompt: str, options: Mapping[str, Any]) -> str:
        """Return the text of one raw completion; ``""`` for an unreadable reply."""
        body = {"model": self._model, "prompt": prompt, **options}
        reply = await self._ask("/v1/completions", body)
        try:
            return str(reply["choices"][0]["text"])
        except (KeyError, IndexError, TypeError):
            return ""


# ── The chat strategy: call facts of the latest reply ───────────────────


class _LastReply:
    """Wraps the judge LLM and keeps the raw provider reply of its latest call."""

    def __init__(self, llm: Any) -> None:
        self.llm = llm
        self.raw: Any = None

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self.llm, name)

    async def acomplete(self, prompt: str, **kwargs: Any) -> Any:
        completion = await self.llm.acomplete(prompt, **kwargs)
        self.raw = getattr(completion, "raw", None)
        return completion


def chat_judge(llm: Any, block: Any, provider: str, make_seam: Callable[[Any], Any]) -> Any:
    """Return the ``chat`` strategy over *llm*, recording each call's host and sent values.

    Args:
        llm: The judge LLM from ``build_verify_llm``.
        block: The answer block (model, reasoning, temperature and seed).
        provider: The registry name of the judge provider.
        make_seam: Builds the async seam over an LLM (``engine_answer.server_seam``).
    """
    from .engine_answer import sampling_record

    last = _LastReply(llm)

    def facts() -> dict[str, Any]:
        record = sampling_record(llm, provider, last.raw)
        return {key: record.get(key) for key in ("host", "temperature", "seed")}

    module = registry.get(judge_name(block))
    resources = JudgeResources(
        model=str(getattr(block, "verify_model", "") or "") or str(getattr(llm, "model", "") or ""),
        settings={
            "temperature": getattr(block, "verify_temperature", None),
            "seed": getattr(block, "verify_seed", None),
            "reasoning": str(getattr(block, "verify_reasoning", "") or "") or None,
        },
        complete=make_seam(last),
        call_facts=facts,
    )
    return module.build(resources)
