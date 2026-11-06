"""``.env.example`` assigns no provider, model or URL key (one-llamacpp-router, 9.1).

``omrs.jsonc`` is the single store of settings (ADR-087). A copied ``.env``
that carries a provider, model or URL value would lock the field and hide the
value that Settings shows. The example file therefore keeps secret notes and
developer overrides, and points to ``omrs config init`` for the rest. A commented
assignment counts, because a reader copies it as readily as a live one.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ENV_EXAMPLE = Path(__file__).resolve().parent.parent / ".env.example"

#: Names that choose a provider, a model or an address. API keys are secrets and stay.
CHOICE_NAME = re.compile(r"^(?:[A-Z0-9_]*(?:PROVIDER|MODEL|URL)|(?:LOCAL|CLOUD)_BACKEND)$")
ASSIGNMENT = re.compile(r"^\s*#?\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=", re.MULTILINE)


def choice_keys(text: str) -> list[str]:
    """Return the provider, model and URL names that *text* assigns, live or commented."""
    return [name for name in ASSIGNMENT.findall(text) if CHOICE_NAME.match(name)]


def test_env_example_assigns_no_provider_model_or_url() -> None:
    found = choice_keys(ENV_EXAMPLE.read_text(encoding="utf-8"))
    assert found == [], f".env.example still assigns {sorted(set(found))}; use omrs.jsonc"


def test_env_example_points_to_the_single_store() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "omrs config init" in text
    assert "omrs.jsonc" in text


def test_env_example_keeps_the_secret_notes() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for secret in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_COMPATIBLE_API_KEY"):
        assert secret in text


@pytest.mark.parametrize(
    "line",
    [
        "LOCAL_BACKEND=ollama",
        "# EMBED_MODEL=nomic-embed-text",
        "#LLAMACPP_ROUTER_URL=http://x/v1",
        "export ANSWER__PROVIDER=ollama",
        "METADATA_LLM_PROVIDER=local",
        "  OLLAMA_BASE_URL=http://localhost:11434",
    ],
)
def test_the_scanner_finds_every_assignment_form(line: str) -> None:
    assert choice_keys(f"{line}\n"), line


@pytest.mark.parametrize(
    "line",
    [
        "# OPENROUTER_API_KEY=sk-or-v1-...",
        "VECTOR_STORE=lancedb",
        "# The EMBED_MODEL setting lives in omrs.jsonc.",
        "RETRIEVAL__RERANK_BACKEND=onnx",
    ],
)
def test_the_scanner_ignores_secrets_other_settings_and_prose(line: str) -> None:
    assert choice_keys(f"{line}\n") == [], line
