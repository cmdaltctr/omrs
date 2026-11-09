"""The ``sampling`` record on an answer result (tasks 1.4 and 7.5, design D3 and D11).

Each answer result holds, for the Chat role and for the claim judge when it
ran, the temperature and seed its requests carried, read from the built LLM
(so LlamaIndex's ``temperature: 0.1`` shows), the host that served the calls,
the host's published support for each value, and whether the host is in the
allowed list. Every request goes to a stub transport; the endpoint list comes
from a fake fetch.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from tests.unit.test_llm_reasoning_providers import OPENROUTER_REPLY
from tests.unit.test_openrouter_allowed_hosts import MODEL, OR_KEY, FakeFetch

from omrs.compose import settings_to_effective
from omrs.config import Settings
from omrs.core.providers.llm import openrouter_hosts
from omrs.engine_answer import (
    ClientCompletion,
    CompletionLedger,
    build_verifier,
    select_completion,
)


@pytest.fixture(autouse=True)
def _fresh_cache() -> Any:
    openrouter_hosts.clear_cache()
    yield
    openrouter_hosts.clear_cache()


def _payload(host: str, parameters: list[str]) -> dict[str, Any]:
    return {
        "data": {
            "id": MODEL,
            "endpoints": [
                {"provider_name": host, "tag": host.lower(), "supported_parameters": parameters}
            ],
        }
    }


def _reply(host: str | None) -> dict[str, Any]:
    reply = dict(OPENROUTER_REPLY)
    reply.pop("provider", None)
    if host is not None:
        reply["provider"] = host
    return reply


def _stubbed(llm: Any, host: str | None = "Z.AI") -> Any:
    """Point *llm* at a stub transport whose replies name *host*."""

    def handler(request: httpx.Request) -> httpx.Response:
        json.loads(request.content)
        return httpx.Response(200, json=_reply(host))

    llm._async_http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return llm


def _settings(**answer: Any) -> Settings:
    block = {"provider": "openrouter", "model": MODEL, "verify_provider": "openrouter"}
    return Settings(_env_file=None, openrouter_api_key=OR_KEY, answer={**block, **answer})


def _chat_llm(settings: Settings, fetch: Any = None, host: str | None = "Z.AI") -> Any:
    from omrs.compose_answer import build_answer_llm

    return _stubbed(build_answer_llm(settings, fetch_endpoints=fetch), host)


def _answer(settings: Settings, llm: Any, *, rounds: int = 1, judge: Any = None) -> dict[str, Any]:
    """Run *rounds* Chat calls and one judge call when *judge* is set; return the result."""
    effective = settings_to_effective(settings)
    ledger = CompletionLedger()
    complete, effective, _ = select_completion(effective, None, lambda: llm, ledger)
    verify, _ = build_verifier(
        effective, (lambda block: judge) if judge is not None else None, str, ledger
    )

    async def run() -> None:
        for _ in range(rounds):
            await complete("question")
        if verify is not None:
            await verify("claim")

    asyncio.run(run())
    return ledger.attach({"status": "ok"})


# ── 1.4 temperature and seed ─────────────────────────────────────────────


def test_the_library_default_temperature_is_recorded() -> None:
    settings = _settings()
    result = _answer(settings, _chat_llm(settings))
    assert result["sampling"]["chat"]["temperature"] == 0.1
    assert result["sampling"]["chat"]["seed"] is None


def test_set_values_are_recorded() -> None:
    settings = _settings(temperature=0, seed=20261101)
    result = _answer(settings, _chat_llm(settings), rounds=2)
    chat = result["sampling"]["chat"]
    assert (chat["temperature"], chat["seed"]) == (0.0, 20261101)


def test_the_judge_record_appears_only_when_the_judge_ran() -> None:
    from omrs.compose_answer import build_verify_llm

    settings = _settings(temperature=0, seed=1)
    assert "judge" not in _answer(settings, _chat_llm(settings))["sampling"]
    settings = _settings(temperature=0, seed=1, verify_claims=True, verify_seed=9)
    judge = _stubbed(
        build_verify_llm(settings, answer_block=settings_to_effective(settings).answer)
    )
    sampling = _answer(settings, _chat_llm(settings), judge=judge)["sampling"]
    assert (sampling["judge"]["temperature"], sampling["judge"]["seed"]) == (0.1, 9)
    assert sampling["chat"]["seed"] == 1


def test_no_model_call_gives_no_record() -> None:
    assert "sampling" not in CompletionLedger().attach({"status": "no_evidence"})


def test_a_client_completion_gives_no_chat_record(effective_settings: Any) -> None:
    async def client(prompt: str) -> str:
        return "text"

    ledger = CompletionLedger()
    completion = ClientCompletion(complete=client, source="client_mrtr", max_rounds=2)
    complete, _, _ = select_completion(effective_settings(), completion, lambda: None, None)
    asyncio.run(complete("q"))
    assert "sampling" not in ledger.attach({"status": "ok"})


# ── 7.5 host, support and the allowed list ───────────────────────────────


def test_the_host_is_recorded_without_a_list() -> None:
    settings = _settings()
    chat = _answer(settings, _chat_llm(settings, host="Fireworks"))["sampling"]["chat"]
    assert chat["host"] == "Fireworks"
    assert chat["accepted"] is None  # no list, so the endpoint list was not read
    assert chat["host_in_list"] is None


def test_host_and_support_are_recorded() -> None:
    settings = _settings(temperature=0, seed=20261101, allowed_hosts="Fireworks")
    fetch = FakeFetch(_payload("Fireworks", ["temperature", "seed"]))
    chat = _answer(settings, _chat_llm(settings, fetch, host="Fireworks"))["sampling"]["chat"]
    assert chat["host"] == "Fireworks"
    assert chat["accepted"] == {"temperature": True, "seed": True}
    assert chat["host_in_list"] is True


def test_a_host_outside_the_list_is_recorded_and_reported() -> None:
    settings = _settings(seed=1, allowed_hosts="Fireworks")
    fetch = FakeFetch(_payload("Fireworks", ["temperature", "seed"]))
    chat = _answer(settings, _chat_llm(settings, fetch, host="Z.AI"))["sampling"]["chat"]
    assert chat["host"] == "Z.AI"
    assert chat["host_in_list"] is False
    assert chat["accepted"] is None  # the endpoint list does not name Z.AI


def test_a_reply_without_a_host_records_none() -> None:
    settings = _settings()
    chat = _answer(settings, _chat_llm(settings, host=None))["sampling"]["chat"]
    assert chat["host"] is None and chat["accepted"] is None


def test_the_record_holds_only_the_declared_keys() -> None:
    settings = _settings()
    chat = _answer(settings, _chat_llm(settings))["sampling"]["chat"]
    assert set(chat) == {"temperature", "seed", "host", "accepted", "host_in_list"}
