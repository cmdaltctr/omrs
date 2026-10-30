"""The settings view of OMRS's own llama.cpp server (ADR-108 D4, D5, D6).

A pure function over resolved ``Settings`` and saved values. It shows the Chat
server choice instead of a server model, the Chat model in force and whether
classification shares the owned server.
"""

from __future__ import annotations

from typing import Any

import pytest

from omrs.compose_llamacpp import build_llamacpp_server_view
from omrs.compose_providers import ProviderValues
from omrs.config import Settings
from omrs.core.answer.settings import AnswerSettings

HF_ID = "Qwen/Qwen3-4B-GGUF:Q4_K_M"


def settings(provider: str = "llamacpp", model: str = HF_ID, **extra: Any) -> Settings:
    extra.setdefault("llamacpp_chat_url", "http://127.0.0.1:8081/v1")
    return Settings(
        _env_file=None,
        answer=AnswerSettings(enabled=True, provider=provider, model=model),
        **extra,
    )


def test_the_view_has_the_chat_server_choice_and_no_model() -> None:
    view = build_llamacpp_server_view(settings())
    assert "model" not in view
    choice = view["chat_server"]
    assert (choice["value"], choice["kind"], choice["source"], choice["locked"]) == (
        "external",
        "choice",
        "default",
        False,
    )


def test_a_saved_choice_applies() -> None:
    saved = ProviderValues(values={"llamacpp_chat_server": "managed"})
    choice = build_llamacpp_server_view(settings(), saved)["chat_server"]
    assert choice["value"] == "managed"


def test_a_choice_from_the_environment_is_locked() -> None:
    base = settings(llamacpp_chat_server="managed")
    object.__setattr__(base, "provider_explicit", frozenset({"llamacpp_chat_server"}))
    choice = build_llamacpp_server_view(base)["chat_server"]
    assert choice["locked"] is True
    assert "LLAMACPP_CHAT_SERVER" in (choice["lock_reason"] or "")


@pytest.mark.parametrize(
    ("provider", "model", "usable"),
    [
        ("llamacpp", HF_ID, True),
        ("llamacpp", "qwen3:4b", False),
        ("llamacpp", "", False),
        ("openrouter", HF_ID, False),
    ],
)
def test_the_chat_model_is_usable_only_for_llamacpp_with_an_allowed_model(
    provider: str, model: str, usable: bool
) -> None:
    view = build_llamacpp_server_view(settings(provider, model))
    assert view["chat_model"] == {"provider": provider, "model": model, "usable": usable}


def test_the_launch_model_is_the_chat_model_only_for_llamacpp() -> None:
    assert build_llamacpp_server_view(settings())["launch_model"] == HF_ID
    assert build_llamacpp_server_view(settings("openrouter"))["launch_model"] == ""


@pytest.mark.parametrize(
    ("classify", "shared"),
    [
        ("", True),
        ("http://127.0.0.1:8081/v1/", True),
        ("http://127.0.0.1:9931/v1", False),
    ],
)
def test_a_shared_address_is_reported_while_managed(classify: str, shared: bool) -> None:
    view = build_llamacpp_server_view(
        settings(llamacpp_chat_server="managed", llamacpp_classify_url=classify)
    )
    assert view["shared_with_classification"] is shared


def test_an_external_server_shares_nothing_with_omrs() -> None:
    view = build_llamacpp_server_view(settings(llamacpp_chat_server="external"))
    assert view["shared_with_classification"] is False
