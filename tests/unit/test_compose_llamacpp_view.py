"""The settings view of the llama.cpp router (ADR-108 D4 to D6, one-llamacpp-router D2, D14).

A pure function over resolved ``Settings`` and saved values. It shows the router mode
instead of a server model, the Chat model in force and whether Chat shares the
classification model.
"""

from __future__ import annotations

from typing import Any

import pytest

from omrs.compose_llamacpp import build_llamacpp_server_view
from omrs.compose_providers import ProviderValues
from omrs.config import Settings
from omrs.config.llamacpp_models import CLASSIFY_MODEL
from omrs.core.answer.settings import AnswerSettings

HF_ID = "Qwen/Qwen3-4B-GGUF:Q4_K_M"


def settings(provider: str = "llamacpp", model: str = HF_ID, **extra: Any) -> Settings:
    return Settings(
        _env_file=None,
        answer=AnswerSettings(enabled=True, provider=provider, model=model),
        **extra,
    )


def test_the_view_has_the_router_mode_and_no_model() -> None:
    view = build_llamacpp_server_view(settings())
    assert "model" not in view
    choice = view["router_server"]
    assert (choice["value"], choice["kind"], choice["source"], choice["locked"]) == (
        "managed",
        "choice",
        "default",
        False,
    )


def test_the_view_shows_the_router_address() -> None:
    view = build_llamacpp_server_view(settings(llamacpp_router_url="http://127.0.0.1:9931/v1"))
    assert view["router_url"] == "http://127.0.0.1:9931/v1"


def test_a_saved_choice_applies() -> None:
    saved = ProviderValues(values={"llamacpp_router_server": "external"})
    choice = build_llamacpp_server_view(settings(), saved)["router_server"]
    assert choice["value"] == "external"


def test_a_choice_from_the_environment_is_locked() -> None:
    base = settings(llamacpp_router_server="external")
    object.__setattr__(base, "provider_explicit", frozenset({"llamacpp_router_server"}))
    choice = build_llamacpp_server_view(base)["router_server"]
    assert choice["locked"] is True
    assert "LLAMACPP_ROUTER_SERVER" in (choice["lock_reason"] or "")


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
    ("provider", "model", "shared"),
    [
        ("llamacpp", CLASSIFY_MODEL, True),
        ("llamacpp", HF_ID, False),
        ("llamacpp", "", False),
        ("openrouter", CLASSIFY_MODEL, False),
    ],
)
def test_chat_on_the_classification_model_is_reported_as_shared(
    provider: str, model: str, shared: bool
) -> None:
    view = build_llamacpp_server_view(settings(provider, model))
    assert view["shared_with_classification"] is shared
