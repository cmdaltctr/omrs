"""The OpenRouter endpoint check before the first call of a role (task 7.4, design D11).

When ``answer.allowed_hosts`` (Chat) or ``answer.verify_allowed_hosts``
(judge) is set and the provider is OpenRouter, OMRS reads the model's public
endpoint list once per process and refuses, with no completion request, when
no listed host supports every value the request sets. An endpoint list of an
unexpected shape, or one that cannot be read, counts as "support unknown" and
refuses too. The list read goes through an injected fetch callable; no test
here reaches the network.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from omrs.config import Settings
from omrs.core.providers.llm import openrouter_hosts
from omrs.core.providers.llm.sampling import HostRefused

MODEL = "deepseek/deepseek-v4.1-flash-1017"
OR_KEY = "sk-or-v1-0000aaaa1111bbbb2222cccc3333dddd"  # gitleaks:allow
ENDPOINTS_URL = f"https://openrouter.ai/api/v1/models/{MODEL}/endpoints"

#: The endpoint list shape documented for ``GET /models/{author}/{slug}/endpoints``.
PAYLOAD: dict[str, Any] = {
    "data": {
        "id": MODEL,
        "endpoints": [
            {
                "provider_name": "Relace",
                "tag": "relace/fp4",
                "supported_parameters": ["temperature", "max_tokens"],
            },
            {
                "provider_name": "Fireworks",
                "tag": "fireworks",
                "supported_parameters": ["temperature", "seed", "max_tokens"],
            },
            {
                "provider_name": "DeepInfra",
                "tag": "deepinfra/fp8",
                "supported_parameters": ["seed", "max_tokens"],
            },
        ],
    }
}


class FakeFetch:
    """An endpoint-list read that records each call and returns a fixed payload."""

    def __init__(self, payload: Any = PAYLOAD, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str]) -> Any:
        self.calls.append((url, dict(headers)))
        if self.error is not None:
            raise self.error
        return self.payload


def _no_fetch(url: str, headers: dict[str, str]) -> Any:
    raise AssertionError("the endpoint list must not be read")


@pytest.fixture(autouse=True)
def _fresh_cache() -> Any:
    openrouter_hosts.clear_cache()
    yield
    openrouter_hosts.clear_cache()


def _settings(**answer: Any) -> Settings:
    block = {"provider": "openrouter", "model": MODEL, "verify_provider": "openrouter"}
    return Settings(_env_file=None, openrouter_api_key=OR_KEY, answer={**block, **answer})


def _chat(settings: Settings, fetch: Any) -> Any:
    from omrs.compose_answer import build_answer_llm

    return build_answer_llm(settings, fetch_endpoints=fetch)


# ── refusals ─────────────────────────────────────────────────────────────


def test_a_host_without_seed_is_refused_naming_model_host_and_value() -> None:
    fetch = FakeFetch()
    with pytest.raises(HostRefused) as caught:
        _chat(_settings(seed=20261101, allowed_hosts="Relace"), fetch)
    message = str(caught.value)
    assert MODEL in message and "Relace" in message and "seed" in message
    assert fetch.calls[0][0] == ENDPOINTS_URL
    assert fetch.calls[0][1]["Authorization"] == f"Bearer {OR_KEY}"


def test_the_library_temperature_counts_as_a_set_value() -> None:
    with pytest.raises(HostRefused) as caught:
        _chat(_settings(allowed_hosts="DeepInfra"), FakeFetch())
    assert "temperature" in str(caught.value)


@pytest.mark.parametrize(
    "payload",
    [
        {"data": []},
        {"data": {"endpoints": "none"}},
        {"data": {"endpoints": [{"provider_name": "Fireworks"}]}},
        {"endpoints": []},
        "not json",
    ],
)
def test_an_unexpected_endpoint_shape_is_refused(payload: Any) -> None:
    with pytest.raises(HostRefused) as caught:
        _chat(_settings(seed=1, allowed_hosts="Fireworks"), FakeFetch(payload))
    assert MODEL in str(caught.value) and "unknown" in str(caught.value)


def test_an_unreadable_endpoint_list_is_refused() -> None:
    fetch = FakeFetch(error=OSError("no route"))
    with pytest.raises(HostRefused) as caught:
        _chat(_settings(seed=1, allowed_hosts="Fireworks"), fetch)
    assert "unknown" in str(caught.value)
    assert "no route" not in str(caught.value)


def test_a_host_the_model_does_not_use_is_refused() -> None:
    with pytest.raises(HostRefused) as caught:
        _chat(_settings(allowed_hosts="Nowhere"), FakeFetch())
    assert "Nowhere" in str(caught.value)


# ── accepted hosts ───────────────────────────────────────────────────────


@pytest.mark.parametrize("hosts", ["Fireworks", "fireworks", "Relace,Fireworks", "FIREWORKS"])
def test_a_listed_host_with_both_values_is_accepted(hosts: str) -> None:
    llm = _chat(_settings(temperature=0, seed=20261101, allowed_hosts=hosts), FakeFetch())
    assert llm.additional_kwargs["extra_body"]["provider"]["only"] == hosts.split(",")


def test_a_base_slug_matches_its_variant() -> None:
    llm = _chat(_settings(temperature=0, allowed_hosts="relace"), FakeFetch())
    assert llm is not None


def test_the_list_is_read_once_per_model() -> None:
    fetch = FakeFetch()
    _chat(_settings(seed=1, allowed_hosts="Fireworks"), fetch)
    _chat(_settings(seed=2, allowed_hosts="Fireworks"), fetch)
    with pytest.raises(HostRefused):
        _chat(_settings(seed=2, allowed_hosts="Relace"), fetch)
    assert len(fetch.calls) == 1


def test_a_failed_read_is_not_cached() -> None:
    with pytest.raises(HostRefused):
        _chat(_settings(seed=1, allowed_hosts="Fireworks"), FakeFetch(error=OSError("down")))
    assert _chat(_settings(seed=1, allowed_hosts="Fireworks"), FakeFetch()) is not None


def test_no_list_reads_nothing() -> None:
    assert _chat(_settings(seed=1), _no_fetch) is not None


def test_another_provider_reads_nothing() -> None:
    settings = Settings(
        _env_file=None,
        answer={"provider": "llamacpp", "model": "m", "allowed_hosts": "Fireworks", "seed": 1},
        llamacpp_router_server="external",
    )
    assert _chat(settings, _no_fetch) is not None


# ── the answer and judge paths ───────────────────────────────────────────


def test_the_answer_path_makes_no_request_and_reports_the_refusal(effective_settings: Any) -> None:
    from omrs.engine_answer import CompletionLedger, select_completion

    def refuse() -> Any:
        raise HostRefused("OpenRouter has no allowed host for m that takes seed: Relace.")

    complete, _, source = select_completion(effective_settings(), None, refuse, CompletionLedger())
    assert source == "server" and complete is not None
    with pytest.raises(HostRefused, match="Relace"):
        asyncio.run(complete("prompt"))


def test_the_judge_path_skips_verification_naming_the_refusal() -> None:
    from omrs.compose import settings_to_effective
    from omrs.compose_answer import build_verify_llm
    from omrs.engine_answer import build_verifier

    settings = _settings(verify_claims=True, verify_seed=3, verify_allowed_hosts="Relace")
    effective = settings_to_effective(settings)
    fetch = FakeFetch()

    def factory(block: Any) -> Any:
        return build_verify_llm(settings, answer_block=block, fetch_endpoints=fetch)

    complete, reason = build_verifier(effective, factory, lambda text: text)
    assert complete is None
    assert reason is not None and "HostRefused" in reason and "Relace" in reason
    assert "seed" in reason


def test_the_chat_list_never_limits_the_judge() -> None:
    from omrs.compose import settings_to_effective
    from omrs.compose_answer import build_verify_llm

    settings = _settings(verify_claims=True, allowed_hosts="Relace", seed=1)
    llm = build_verify_llm(
        settings, answer_block=settings_to_effective(settings).answer, fetch_endpoints=_no_fetch
    )
    assert "provider" not in llm.additional_kwargs.get("extra_body", {})
