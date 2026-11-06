"""Roles of the router list are derived from the role settings (one-llamacpp-router, task 2.3).

An entry holds the role of each setting that names its ``model``. Nothing starts and
nothing is sent: the function is pure, and the settings adapter only reads.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from omrs import compose_answer
from omrs.config import Settings, provenance
from omrs.config.llamacpp_models import (
    CLASSIFY_MODEL,
    EMBED_MODEL,
    SHIPPED_MODELS,
    LlamaCppModelEntry,
)
from omrs.config.llamacpp_roles import (
    MODEL_NOT_LISTED,
    ROLE_MISMATCH,
    ROLES,
    derive_roles,
)
from omrs.config.settings_maps import DecisionModelEntry
from omrs.core.answer.settings import AnswerSettings

CLEF = "Clef/Clef-Flash-GGUF:Q8_0"
OTHER = "Other/Text-GGUF:Q8_0"


def models(**extra: LlamaCppModelEntry) -> Mapping[str, LlamaCppModelEntry]:
    return {**SHIPPED_MODELS, **extra}


def text_entry(model: str, **preset: Any) -> LlamaCppModelEntry:
    return LlamaCppModelEntry(model=model, preset=preset)


def derive(**kwargs: Any) -> Any:
    return derive_roles(kwargs.pop("models", models()), **kwargs)


# ── The function ─────────────────────────────────────────────────────────


def test_the_shipped_defaults_give_embeddings_and_classification_only() -> None:
    report = derive(embed_model=EMBED_MODEL, classify_model=CLASSIFY_MODEL)
    assert report.roles == {"qwen3-embedding-4b": ("embeddings",), "qwen3-4b": ("classification",)}
    assert report.problems == ()


def test_one_entry_can_hold_two_roles() -> None:
    report = derive(
        embed_model=EMBED_MODEL, classify_model=CLASSIFY_MODEL, chat_model=CLASSIFY_MODEL
    )
    assert report.roles["qwen3-4b"] == ("classification", "chat")
    assert report.problems == ()


def test_no_chat_model_chosen_gives_no_chat_role_and_no_problem() -> None:
    report = derive(embed_model=EMBED_MODEL, classify_model=CLASSIFY_MODEL, chat_model="")
    assert all("chat" not in roles for roles in report.roles.values())
    assert report.problems == ()


def test_every_role_at_once_follows_the_role_order() -> None:
    clef = text_entry(CLEF, parallel=1)
    both = text_entry(OTHER)
    report = derive(
        models=models(clef=clef, other=both),
        embed_model=EMBED_MODEL,
        classify_model=OTHER,
        chat_model=OTHER,
        judge_model=OTHER,
        decision_models=[CLEF, OTHER],
    )
    assert report.roles["other"] == ("classification", "chat", "judge", "decision")
    assert report.roles["clef"] == ("decision",)
    assert list(ROLES) == ["embeddings", "classification", "chat", "judge", "decision"]


@pytest.mark.parametrize(
    ("role", "kwarg"),
    [
        ("embeddings", "embed_model"),
        ("classification", "classify_model"),
        ("chat", "chat_model"),
        ("judge", "judge_model"),
    ],
)
def test_a_model_that_no_entry_holds_is_reported_not_listed(role: str, kwarg: str) -> None:
    report = derive(**{kwarg: "Nobody/Listed-GGUF:Q8_0"})
    (problem,) = report.problems
    assert (problem.role, problem.model, problem.reason) == (
        role,
        "Nobody/Listed-GGUF:Q8_0",
        MODEL_NOT_LISTED,
    )
    assert all(not roles for roles in report.roles.values())
    assert "Nobody" not in problem.rule


def test_a_decision_entry_that_no_entry_holds_is_reported_not_listed() -> None:
    (problem,) = derive(decision_models=["Nobody/Listed-GGUF:Q8_0"]).problems
    assert (problem.role, problem.reason) == ("decision", MODEL_NOT_LISTED)


@pytest.mark.parametrize("kwarg", ["classify_model", "chat_model", "judge_model"])
def test_an_embedding_entry_cannot_hold_a_text_role(kwarg: str) -> None:
    report = derive(**{kwarg: EMBED_MODEL})
    (problem,) = report.problems
    assert problem.reason == ROLE_MISMATCH
    assert report.roles["qwen3-embedding-4b"] == ()


def test_an_embedding_entry_cannot_hold_a_decision_role() -> None:
    (problem,) = derive(decision_models=[EMBED_MODEL]).problems
    assert (problem.role, problem.reason) == ("decision", ROLE_MISMATCH)


def test_a_refused_role_does_not_block_the_others() -> None:
    report = derive(embed_model=EMBED_MODEL, classify_model=CLASSIFY_MODEL, chat_model=EMBED_MODEL)
    assert [p.role for p in report.problems] == ["chat"]
    assert report.roles["qwen3-4b"] == ("classification",)
    assert report.roles["qwen3-embedding-4b"] == ("embeddings",)


def test_a_text_entry_cannot_serve_embeddings() -> None:
    (problem,) = derive(embed_model=CLASSIFY_MODEL).problems
    assert (problem.role, problem.reason) == ("embeddings", "preset-invalid")


@pytest.mark.parametrize("missing", ["pooling", "ctx-size", "batch-size", "ubatch-size"])
def test_an_embedding_entry_must_set_its_pooling_and_sizes(missing: str) -> None:
    preset = dict(SHIPPED_MODELS["qwen3-embedding-4b"].preset)
    del preset[missing]
    entry = LlamaCppModelEntry(model=EMBED_MODEL, preset=preset)
    report = derive(models={"qwen3-embedding-4b": entry}, embed_model=EMBED_MODEL)
    (problem,) = report.problems
    assert (problem.role, problem.reason) == ("embeddings", "preset-invalid")
    assert missing in problem.rule
    assert report.roles["qwen3-embedding-4b"] == ()


def test_an_embedding_entry_without_embeddings_true_is_invalid() -> None:
    preset = {
        k: v for k, v in SHIPPED_MODELS["qwen3-embedding-4b"].preset.items() if k != "embeddings"
    }
    entry = LlamaCppModelEntry(model=EMBED_MODEL, preset=preset)
    (problem,) = derive(models={"e": entry}, embed_model=EMBED_MODEL).problems
    assert problem.reason == "preset-invalid"


def test_an_empty_list_reports_every_named_role_as_not_listed() -> None:
    report = derive(models={}, embed_model=EMBED_MODEL, classify_model=CLASSIFY_MODEL)
    assert [(p.role, p.reason) for p in report.problems] == [
        ("embeddings", MODEL_NOT_LISTED),
        ("classification", MODEL_NOT_LISTED),
    ]
    assert report.roles == {}


# ── The settings adapter ─────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))


def settings_with(**fields: Any) -> Settings:
    return Settings(_env_file=None, **fields)


def answer(**fields: Any) -> AnswerSettings:
    return AnswerSettings(enabled=True, **fields)


def test_a_fresh_install_serves_classification_and_embeddings_only() -> None:
    report = compose_answer.llamacpp_roles(settings_with(local_backend="llamacpp"))
    assert report.roles == {"qwen3-embedding-4b": ("embeddings",), "qwen3-4b": ("classification",)}
    assert report.problems == ()


def test_chat_on_llamacpp_names_its_entry() -> None:
    settings = settings_with(answer=answer(provider="llamacpp", model=CLASSIFY_MODEL))
    assert compose_answer.llamacpp_roles(settings).roles["qwen3-4b"] == ("classification", "chat")


def test_an_unlisted_chat_model_is_reported() -> None:
    settings = settings_with(answer=answer(provider="llamacpp", model=OTHER))
    (problem,) = compose_answer.llamacpp_roles(settings).problems
    assert (problem.role, problem.reason) == ("chat", MODEL_NOT_LISTED)


def test_chat_on_another_provider_holds_no_router_role() -> None:
    settings = settings_with(answer=answer(provider="openrouter", model="vendor/model"))
    report = compose_answer.llamacpp_roles(settings)
    assert report.problems == ()
    assert all("chat" not in roles for roles in report.roles.values())


@pytest.mark.parametrize(
    ("verify_provider", "local_backend", "on"),
    [("llamacpp", "ollama", True), ("local", "llamacpp", True), ("local", "ollama", False)]
    + [("cloud", "llamacpp", False), ("openrouter", "llamacpp", False), ("", "llamacpp", False)],
)
def test_the_judge_counts_only_while_it_runs_on_llamacpp(
    verify_provider: str, local_backend: str, on: bool
) -> None:
    settings = settings_with(
        local_backend=local_backend,
        answer=answer(verify_provider=verify_provider, verify_model=CLASSIFY_MODEL),
    )
    roles = compose_answer.llamacpp_roles(settings).roles["qwen3-4b"]
    assert ("judge" in roles) is on


def test_a_judge_with_no_model_holds_no_role() -> None:
    settings = settings_with(answer=answer(verify_provider="llamacpp", verify_model=""))
    report = compose_answer.llamacpp_roles(settings)
    assert report.problems == ()
    assert all("judge" not in roles for roles in report.roles.values())


def test_a_managed_llamacpp_decision_entry_holds_the_decision_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_with()
    clef = text_entry(CLEF, parallel=1)
    monkeypatch.setattr(
        type(settings),
        "llamacpp_models",
        property(lambda self: {**SHIPPED_MODELS, "clef": clef}),
    )
    entries = {
        "managed": DecisionModelEntry(
            kind="llamacpp", address="http://127.0.0.1:8080", model=CLEF, server="managed"
        ),
        "external": DecisionModelEntry(
            kind="llamacpp", address="http://127.0.0.1:9", model=OTHER, server="external"
        ),
        "hosted": DecisionModelEntry(kind="typesafe", address="https://x.test", model=OTHER),
    }
    monkeypatch.setattr(type(settings), "decision_models", property(lambda self: entries))
    report = compose_answer.llamacpp_roles(settings)
    assert report.roles["clef"] == ("decision",)
    assert report.problems == ()
