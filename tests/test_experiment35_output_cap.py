"""Experiment 35 answer calls send the pinned output cap (2026-11-25 pre-freeze note, item 2).

OMRS uses ``answer.max_output_tokens`` only to size the prompt budget; it never
sends it to the model. Rules under test: the Engine that the Exp 35 harness
builds sends the cap as ``max_tokens`` on every answer request; each reply's
finish reason reaches the saved answer row, so a reply cut at the cap shows as
``length``; the app's own answer model still sends no cap (product unchanged).
Every request goes to a stub transport; no network call is made.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from tests._exp35_fixtures import load
from tests.unit.test_llm_reasoning_providers import OPENROUTER_REPLY
from tests.unit.test_openrouter_allowed_hosts import MODEL, OR_KEY

from omrs.compose import settings_to_effective
from omrs.config import Settings
from omrs.engine_answer import CompletionLedger, select_completion

answers35 = load("answers35")
live35 = load("live35")


def _settings() -> Settings:
    block = {"provider": "openrouter", "model": MODEL, "max_output_tokens": 2048}
    return Settings(_env_file=None, openrouter_api_key=OR_KEY, answer=block)


def _stubbed(llm: Any, bodies: list[dict[str, Any]], finish: str) -> Any:
    reply = json.loads(json.dumps(OPENROUTER_REPLY))
    reply["choices"][0]["finish_reason"] = finish

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=reply)

    llm._async_http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return llm


def _engine(settings: Settings, bodies: list[dict[str, Any]], finish: str) -> Any:
    """A stand-in Engine with the real answer-model factory and the real settings."""
    from omrs.compose_answer import build_answer_llm

    return SimpleNamespace(
        _answer_llm_factory=lambda: _stubbed(build_answer_llm(settings), bodies, finish),
        _effective_settings=settings_to_effective(settings),
    )


def _call(engine: Any, settings: Settings) -> dict[str, Any]:
    """One answer-model call through OMRS's seam, as ``Engine.answer`` makes it."""
    ledger = CompletionLedger()
    llm = engine._answer_llm_factory()
    complete, *_ = select_completion(settings_to_effective(settings), None, lambda: llm, ledger)

    async def run() -> dict[str, Any]:
        await complete("question")
        return ledger.attach({"status": "answered"})

    return asyncio.run(answers35.with_finish_reasons(run))


def test_the_harness_engine_sends_the_pinned_cap_as_max_tokens() -> None:
    settings, bodies = _settings(), []
    engine = _engine(settings, bodies, "stop")
    answers35.cap_answer_output(engine)
    result = _call(engine, settings)
    assert [b.get("max_tokens") for b in bodies] == [2048]
    # The wrapper keeps OMRS's own sampling record working (it reads the built model).
    assert result["sampling"]["chat"]["temperature"] == 0.1


def test_a_reply_cut_at_the_cap_records_its_finish_reason() -> None:
    settings, bodies = _settings(), []
    engine = _engine(settings, bodies, "length")
    answers35.cap_answer_output(engine)
    result = _call(engine, settings)
    assert result["finish_reasons"] == ["length"]


def test_the_app_answer_model_still_sends_no_cap() -> None:
    settings, bodies = _settings(), []
    _call(_engine(settings, bodies, "stop"), settings)
    assert "max_tokens" not in bodies[0]


def test_the_saved_answer_row_holds_the_finish_reasons() -> None:
    ctx = SimpleNamespace(dataset="bioasq", setup="e4b-c512-roff-hoff", run=1)
    question = SimpleNamespace(qid="q1", gold_pages=())
    result = {"status": "answered", "answer": "a", "finish_reasons": ["length"]}
    assert answers35.answer_row(ctx, question, result, 1.0)["finish_reasons"] == ["length"]


def test_live_deps_engine_caps_the_answer_model(monkeypatch: pytest.MonkeyPatch) -> None:
    import omrs.compose

    settings, bodies = _settings(), []
    engine = _engine(settings, bodies, "stop")
    monkeypatch.setattr(omrs.compose, "build_engine", lambda: engine)
    built = live35.LiveDeps.engine(SimpleNamespace())
    _call(built, settings)
    assert [b.get("max_tokens") for b in bodies] == [2048]
