"""Temperature, seed and allowed hosts per Chat provider (tasks 1.3 and 7.3, design D2 and D11).

Each provider module maps the values to its own request fields in
``build()``. An empty value leaves the request as it was before this change:
the OpenAI-like classes keep LlamaIndex's ``temperature: 0.1`` and send no
``seed``. The registry reports which values a provider ignores. Keys in these
tests are fake, and every request goes to a stub transport.
"""

from __future__ import annotations

import json
import sys
import types
from typing import Any

import httpx
import pytest
from tests.unit.test_connection_summary import make_settings
from tests.unit.test_llm_reasoning_providers import OPENROUTER_REPLY

from omrs.core.providers.llm import (
    anthropic,
    llamacpp,
    ollama,
    openai_compatible,
    openrouter,
    registry,
)

OR_KEY = "sk-or-v1-0000aaaa1111bbbb2222cccc3333dddd"  # gitleaks:allow
_LIBRARY_DEFAULT = 0.1


def _sent_body(llm: Any) -> dict[str, Any]:
    """Run one completion against a stub transport and return the JSON body sent."""
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=OPENROUTER_REPLY)

    llm._http_client = httpx.Client(transport=httpx.MockTransport(handler))
    llm.complete("Why is the sky blue?")
    return sent[0]


def _openrouter(**kwargs: Any) -> Any:
    settings = make_settings(openrouter_api_key=OR_KEY)
    return openrouter.build(settings, answer_model="z-ai/glm-5.3-flash", **kwargs)


def _compatible(**kwargs: Any) -> Any:
    settings = make_settings(openai_compatible_base_url="http://localhost:1234/v1")
    return openai_compatible.build(settings, answer_model="m", **kwargs)


def _llamacpp(**kwargs: Any) -> Any:
    return llamacpp.build(make_settings(), answer_model="m", **kwargs)


_OPENAI_LIKE = [_openrouter, _compatible, _llamacpp]


# ── empty values leave the request as it was ─────────────────────────────


@pytest.mark.parametrize("build", _OPENAI_LIKE)
def test_empty_values_keep_the_library_temperature_and_send_no_seed(build: Any) -> None:
    body = _sent_body(build())
    assert body["temperature"] == _LIBRARY_DEFAULT
    assert "seed" not in body
    assert "provider" not in body


@pytest.mark.parametrize("build", _OPENAI_LIKE)
def test_explicit_none_values_change_nothing(build: Any) -> None:
    assert _sent_body(build(temperature=None, seed=None)) == _sent_body(build())


def test_ollama_empty_values_send_no_temperature_and_no_seed() -> None:
    llm = ollama.build(make_settings(), answer_model="qwen3:4b")
    assert llm.temperature is None
    assert "seed" not in llm._model_kwargs


# ── set values reach the request ─────────────────────────────────────────


@pytest.mark.parametrize("build", _OPENAI_LIKE)
def test_set_values_reach_the_request_body(build: Any) -> None:
    body = _sent_body(build(temperature=0.0, seed=20261101))
    assert body["temperature"] == 0.0
    assert body["seed"] == 20261101


@pytest.mark.parametrize("build", _OPENAI_LIKE)
def test_a_seed_alone_keeps_the_library_temperature(build: Any) -> None:
    body = _sent_body(build(seed=7))
    assert (body["temperature"], body["seed"]) == (_LIBRARY_DEFAULT, 7)


def test_ollama_sends_temperature_and_seed_in_options() -> None:
    llm = ollama.build(make_settings(), answer_model="qwen3:4b", temperature=0.0, seed=20261101)
    options = llm._model_kwargs
    assert (options["temperature"], options["seed"]) == (0.0, 20261101)


def test_ollama_keeps_think_beside_the_seed() -> None:
    llm = ollama.build(make_settings(), answer_model="qwen3:4b", reasoning="low", seed=3)
    assert llm.thinking == "low"
    assert llm._model_kwargs["seed"] == 3


@pytest.mark.parametrize("build", [_openrouter, _compatible])
def test_reasoning_and_seed_both_reach_the_body(build: Any) -> None:
    body = _sent_body(build(reasoning="low", seed=20261101, temperature=0.0))
    assert body["seed"] == 20261101
    assert body["temperature"] == 0.0
    assert body.get("reasoning") == {"effort": "low"} or body.get("reasoning_effort") == "low"


def _stub_anthropic(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    class StubAnthropic:
        def __init__(self, **kwargs: Any) -> None:
            seen.update(kwargs)

    stub = types.ModuleType("llama_index.llms.anthropic")
    stub.Anthropic = StubAnthropic  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llama_index.llms.anthropic", stub)
    return seen


def test_anthropic_sends_neither_value(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _stub_anthropic(monkeypatch)
    settings = make_settings(anthropic_api_key="sk-ant-api03-AAAA1111BBBB2222CCCC3333")
    anthropic.build(
        settings,
        timeout=9.0,
        answer_model="claude-x",
        temperature=0.0,
        seed=1,
        allowed_hosts=("x",),
    )
    assert set(seen) == {"model", "api_key", "timeout"}


# ── allowed hosts (OpenRouter only) ──────────────────────────────────────


def test_an_allowed_host_list_pins_the_openrouter_request() -> None:
    body = _sent_body(_openrouter(allowed_hosts=("Fireworks", "deepinfra/fp8")))
    assert body["provider"] == {
        "only": ["Fireworks", "deepinfra/fp8"],
        "allow_fallbacks": False,
        "require_parameters": True,
    }
    assert "extra_body" not in body


def test_reasoning_seed_and_host_list_reach_the_body_together() -> None:
    body = _sent_body(
        _openrouter(reasoning="low", temperature=0.0, seed=20261101, allowed_hosts=("Fireworks",))
    )
    assert body["reasoning"] == {"effort": "low"}
    assert (body["temperature"], body["seed"]) == (0.0, 20261101)
    assert body["provider"]["only"] == ["Fireworks"]


@pytest.mark.parametrize("build", [_compatible, _llamacpp])
def test_other_providers_send_no_host_field(build: Any) -> None:
    body = _sent_body(build(allowed_hosts=("Fireworks",)))
    assert "provider" not in body
    assert "extra_body" not in body


def test_ollama_sends_no_host_field() -> None:
    llm = ollama.build(make_settings(), answer_model="qwen3:4b", allowed_hosts=("Fireworks",))
    assert "provider" not in llm._model_kwargs and llm.additional_kwargs == {}


# ── the registry knows who ignores what ──────────────────────────────────


@pytest.mark.parametrize(
    ("name", "ignored"),
    [
        ("openrouter", set()),
        ("openai_compatible", {"allowed_hosts"}),
        ("llamacpp", {"allowed_hosts"}),
        ("ollama", {"allowed_hosts"}),
        ("anthropic", {"temperature", "seed", "allowed_hosts"}),
        ("no-such-provider", {"temperature", "seed", "allowed_hosts"}),
    ],
)
def test_the_registry_reports_ignored_values(name: str, ignored: set[str]) -> None:
    assert registry.ignored_sampling(name) == ignored


# ── composition root: each role gets its own values ──────────────────────


class _Recorder:
    """A provider ``build()`` that records the keyword arguments it got."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, settings: Any, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        return object()


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    rec = _Recorder()
    monkeypatch.setitem(registry._cache, "llamacpp", rec)
    return rec


def _answer_settings(**answer: Any) -> Any:
    from omrs.config import Settings

    block = {
        "provider": "llamacpp",
        "model": "a",
        "verify_provider": "llamacpp",
        "verify_model": "j",
    }
    return Settings(_env_file=None, answer={**block, **answer})


def test_the_chat_model_gets_the_chat_values(recorder: _Recorder) -> None:
    from omrs.compose_answer import build_answer_llm

    build_answer_llm(_answer_settings(temperature=0, seed=20261101, verify_seed=5))
    call = recorder.calls[-1]
    assert (call["temperature"], call["seed"]) == (0, 20261101)


def test_empty_chat_values_pass_nothing(recorder: _Recorder) -> None:
    from omrs.compose_answer import build_answer_llm

    build_answer_llm(_answer_settings(verify_temperature=0.5, verify_seed=5))
    assert not {"temperature", "seed", "allowed_hosts"} & set(recorder.calls[-1])


def test_chat_values_never_reach_the_judge(recorder: _Recorder) -> None:
    from omrs.compose import settings_to_effective
    from omrs.compose_answer import build_verify_llm

    settings = _answer_settings(
        verify_claims=True, temperature=0, seed=7, allowed_hosts="Fireworks"
    )
    build_verify_llm(settings, answer_block=settings_to_effective(settings).answer)
    assert not {"temperature", "seed", "allowed_hosts"} & set(recorder.calls[-1])


def test_the_judge_gets_its_own_values(recorder: _Recorder) -> None:
    from omrs.compose import settings_to_effective
    from omrs.compose_answer import build_verify_llm

    settings = _answer_settings(verify_claims=True, seed=7, verify_temperature=0, verify_seed=9)
    build_verify_llm(settings, answer_block=settings_to_effective(settings).answer)
    call = recorder.calls[-1]
    assert (call["temperature"], call["seed"]) == (0, 9)


def test_the_chat_host_list_reaches_the_chat_build_only(recorder: _Recorder) -> None:
    from omrs.compose_answer import build_answer_llm

    build_answer_llm(
        _answer_settings(allowed_hosts="Fireworks,DeepInfra", verify_allowed_hosts="Z.AI")
    )
    assert recorder.calls[-1]["allowed_hosts"] == ("Fireworks", "DeepInfra")
