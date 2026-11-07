"""The settings side of the router clients: one address, no per-role addresses.

Change one-llamacpp-router, tasks 2.3 (provider side) and 2.6. The checks cover the
effective settings, the llama.cpp connection descriptor, the shared endpoint read and the
removal of ``classification_url``. The server view is in ``test_compose_llamacpp_view``.
"""

from __future__ import annotations

from typing import Any

import pytest

from omrs import compose_settings
from omrs.config import Settings
from omrs.config.llamacpp_models import SHIPPED_MODELS
from omrs.core import provider_values
from omrs.core.providers.common import get_embed_endpoint
from omrs.core.providers.llm import registry
from omrs.core.providers.llm.llamacpp_rules import LLAMACPP_SERVER_FIELDS
from omrs.core.settings import PROVIDER_ADDRESS_FIELDS, EffectiveSettings

RETIRED = ("llamacpp_embed_url", "llamacpp_chat_url", "llamacpp_classify_url")
ROUTER = "http://127.0.0.1:9931/v1"


def settings(**extra: Any) -> Settings:
    return Settings(_env_file=None, **extra)


# ── EffectiveSettings carries the router, not the role addresses ────────────────────────────


@pytest.mark.parametrize("name", RETIRED)
def test_effective_settings_has_no_role_address(name: str) -> None:
    assert name not in EffectiveSettings.model_fields


def test_effective_settings_carries_the_router_values() -> None:
    effective = compose_settings.settings_to_effective(
        settings(llamacpp_router_url=ROUTER, llamacpp_router_server="external")
    )
    assert effective.llamacpp_router_url == ROUTER
    assert effective.llamacpp_router_server == "external"
    assert {entry.model for entry in effective.llamacpp_models.values()} == {
        entry.model for entry in SHIPPED_MODELS.values()
    }


def test_the_address_fields_hold_the_router_address_once() -> None:
    assert "llamacpp_router_url" in PROVIDER_ADDRESS_FIELDS
    assert not set(RETIRED) & set(PROVIDER_ADDRESS_FIELDS)


# ── The connection descriptor shows one router address ─────────────────────────────────────


def described() -> Any:
    return registry.describe_all()["llamacpp"]


def test_the_card_has_one_editable_address() -> None:
    (field,) = described().fields
    assert (field.id, field.kind, field.settings_field, field.env_var) == (
        "router_url",
        "url",
        "llamacpp_router_url",
        "LLAMACPP_ROUTER_URL",
    )


def test_the_card_reads_the_mode_and_the_role_models_only() -> None:
    rows = {row.label: row.value for row in described().read_only(settings())}
    assert rows == {
        "Router mode": "managed",
        "Embedding model": settings().llamacpp_embed_model,
        "Text model (classification)": settings().llamacpp_chat_model,
    }


def test_the_connection_test_and_the_model_list_read_the_router_address() -> None:
    base = settings(llamacpp_router_url=ROUTER)
    assert described().test_targets(base).urls == (f"{ROUTER}/models",)
    assert described().models_target(base).urls == (f"{ROUTER}/models",)


def test_the_server_fields_are_the_program_and_the_router_mode() -> None:
    assert [(spec.id, spec.settings_field) for spec in LLAMACPP_SERVER_FIELDS] == [
        ("server_binary", "llamacpp_server_binary"),
        ("router_server", "llamacpp_router_server"),
    ]


# ── The endpoint read and the view ─────────────────────────────────────────────────────────


def test_the_embedding_endpoint_is_the_router_address() -> None:
    base = settings(
        llamacpp_router_url=ROUTER,
        embed_provider="llamacpp",
        llamacpp_embed_model="embed",
    )
    assert get_embed_endpoint(base) == (ROUTER, "embed", "no-key")


def test_classification_url_is_gone() -> None:
    assert not hasattr(provider_values, "classification_url")
