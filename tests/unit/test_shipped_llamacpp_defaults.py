"""Shipped local defaults use llama.cpp (one-llamacpp-router, task 2.5).

With no source set, Chat is on the llama.cpp provider with no model chosen,
classification keeps the shipped Qwen3-4B, and no default names Ollama. Chat and the
claim-check judge answer with a setup message that names their own setting when the
model is empty. They never borrow ``llamacpp_chat_model``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from omrs import compose
from omrs.config import Settings, provenance
from omrs.config.llamacpp_models import CLASSIFY_MODEL, EMBED_MODEL
from omrs.core.answer.settings import AnswerSettings
from omrs.core.settings import AnswerBlock

#: Variables that conftest or the host may set and that these tests care about.
VARIABLES = (
    "EMBED_PROVIDER",
    "LOCAL_BACKEND",
    "CLOUD_BACKEND",
    "METADATA_LLM_PROVIDER",
    "EMBED_MODEL",
    "OLLAMA_BASE_URL",
    "ANSWER__PROVIDER",
    "ANSWER__MODEL",
    "ANSWER__VERIFY_PROVIDER",
    "ANSWER__VERIFY_MODEL",
    "METADATA__OLLAMA_CLASSIFY_MODEL",
    "LLAMACPP_EMBED_MODEL",
    "LLAMACPP_CHAT_MODEL",
)
#: An Ollama tag: a name, a colon and a size such as ``4b`` or ``0.6b``.
OLLAMA_TAG = re.compile(r"[a-z][a-z0-9._-]*:\d+(\.\d+)?b")
OLLAMA_CLASSIFY_PATH = ".metadata.ollama_classify_model"
DEFAULTS_YAML = Path(__file__).parents[2] / "src" / "omrs" / "config" / "defaults.yaml"


@pytest.fixture
def shipped(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    """Settings with no environment, no ``.env`` and no ``omrs.jsonc``."""
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return Settings(_env_file=None)


def strings(value: Any, path: str = "") -> list[tuple[str, str]]:
    """Return ``(path, text)`` for every text in a nested value."""
    if isinstance(value, dict):
        return [pair for key, item in value.items() for pair in strings(item, f"{path}.{key}")]
    return [(path, value)] if isinstance(value, str) else []


# ── Defaults ─────────────────────────────────────────────────────────────


def test_fresh_install_chat_choice(shipped: Settings) -> None:
    assert shipped.answer.provider == "llamacpp"
    assert shipped.answer.model == ""
    assert shipped.llamacpp_chat_model == CLASSIFY_MODEL == "Qwen/Qwen3-4B-GGUF:Q8_0"
    assert shipped.llamacpp_embed_model == EMBED_MODEL == "Qwen/Qwen3-Embedding-4B-GGUF:Q8_0"


def test_the_answer_settings_model_ships_the_same_choice() -> None:
    block = AnswerSettings()
    assert (block.provider, block.model) == ("llamacpp", "")


def test_no_ollama_default(shipped: Settings) -> None:
    """No provider default is ``ollama`` and no model default is an Ollama tag."""
    assert "ollama" not in {
        shipped.embed_provider,
        shipped.metadata_llm_provider,
        shipped.local_backend,
        shipped.cloud_backend,
        shipped.answer.provider,
        shipped.answer.verify_provider,
    }
    resolved = strings(shipped.model_dump(exclude={"setting_sources"}))
    shipped_yaml = strings(yaml.safe_load(DEFAULTS_YAML.read_text(encoding="utf-8")))
    tags = [
        (path, text)
        for path, text in (*resolved, *shipped_yaml)
        if OLLAMA_TAG.fullmatch(text) and not path.endswith(OLLAMA_CLASSIFY_PATH)
    ]
    assert tags == []


def test_the_ollama_classification_model_ships_empty(shipped: Settings) -> None:
    assert shipped.metadata.ollama_classify_model == ""


def test_the_defaults_file_names_no_ollama_provider() -> None:
    data = yaml.safe_load(DEFAULTS_YAML.read_text(encoding="utf-8"))
    assert data["answer"]["provider"] == "llamacpp"
    assert data["answer"]["model"] == ""
    assert "ollama" not in {
        str(data.get(k, "")).lower() for k in ("LOCAL_BACKEND", "EMBED_PROVIDER")
    }


def test_ollama_stays_opt_in() -> None:
    """A user who picks Ollama and a tag gets it: the provider stays registered."""
    chosen = AnswerSettings(provider="ollama", model="qwen3:4b")
    assert (chosen.provider, chosen.model) == ("ollama", "qwen3:4b")
    assert AnswerBlock(provider="ollama", model="qwen3:4b").model == "qwen3:4b"


def test_the_tokenizer_default_matches_the_shipped_embedding_model(shipped: Settings) -> None:
    repo = EMBED_MODEL.partition(":")[0].removesuffix("-GGUF")
    assert shipped.embedding.tokenizer_model == repo == "Qwen/Qwen3-Embedding-4B"


def test_the_router_models_are_the_shipped_list(shipped: Settings) -> None:
    assert {entry.model for entry in shipped.llamacpp_models.values()} == {
        shipped.llamacpp_embed_model,
        shipped.llamacpp_chat_model,
    }


# ── Chat and the judge with no model ─────────────────────────────────────


class _NoClient:
    """Records any llama.cpp client that gets built."""

    built: list[dict[str, Any]]

    def __init__(self) -> None:
        self.built = []

    def __call__(self, **kwargs: Any) -> None:
        self.built.append(kwargs)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> _NoClient:
    import llama_index.llms.openai_like as module

    recorder = _NoClient()
    monkeypatch.setattr(module, "OpenAILike", recorder)
    return recorder


def test_chat_with_no_model_gives_a_setup_message_and_builds_nothing(
    shipped: Settings, client: _NoClient
) -> None:
    assert shipped.llamacpp_chat_model  # the classification model is set and must stay unused
    with pytest.raises(ValueError, match=r"answer\.model") as caught:
        compose.build_answer_llm(shipped)
    assert "Settings > Chat" in str(caught.value)
    assert client.built == []


def test_judge_on_llamacpp_with_no_model_gives_a_setup_message_and_builds_nothing(
    shipped: Settings, client: _NoClient
) -> None:
    block = AnswerBlock(
        verify_claims=True,
        verify_provider="llamacpp",
        verify_model="",
        provider="llamacpp",
        model="",
    )
    assert shipped.llamacpp_chat_model
    with pytest.raises(ValueError, match=r"answer\.verify_model") as caught:
        compose.build_verify_llm(shipped, answer_block=block)
    assert "Settings > Chat" in str(caught.value)
    assert client.built == []


def test_the_effective_answer_block_mirrors_the_answer_settings() -> None:
    from omrs.core.answer.settings import AnswerSettings
    from omrs.core.settings import AnswerBlock

    assert (AnswerBlock().provider, AnswerBlock().model) == (
        AnswerSettings().provider,
        AnswerSettings().model,
    )
