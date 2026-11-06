"""The preset allow-list of a router model entry (one-llamacpp-router, task 2.2).

The preset holds the only keys the router list may carry for one model, each typed and
range-checked. These tests cover the keys, the ranges, the reserved keys and the exact
boolean rule. They check values only: the ``models.ini`` writer belongs to task 3.3.

Every test points ``OMRS_CONFIG_DIR`` at a temporary folder.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from omrs.config import Settings, provenance
from omrs.config.llamacpp_models import check_model_entry
from omrs.config.llamacpp_preset import PRESET_KEY_UNKNOWN, PRESET_KEYS, preset_problems
from omrs.config.settings_file import KIND_UNKNOWN, read_settings_file

#: A value that must never appear in a rule text.
SENTINEL = "SENTINEL-VALUE-0000"
QWEN = "Qwen/Qwen3-4B-GGUF:Q8_0"


@pytest.fixture(autouse=True)
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return root


def write_config(root: Path, data: dict[str, Any]) -> None:
    (root / "omrs.jsonc").write_text(json.dumps(data), encoding="utf-8")


def build() -> Settings:
    return Settings(_env_file=None)


def problems_at(prefix: str) -> list[tuple[str, str, str]]:
    return [
        (p.kind, p.key, p.message)
        for p in read_settings_file().problems
        if p.key.startswith(prefix)
    ]


def entry(**fields: Any) -> dict[str, Any]:
    return {"model": QWEN, **fields}


# ── The preset allow-list (spec: The preset file holds allow-listed keys only) ──

GOOD_PRESET: dict[str, Any] = {
    "ctx-size": 8192,
    "batch-size": 4096,
    "ubatch-size": 512,
    "parallel": 2,
    "embeddings": True,
    "pooling": "mean",
    "embd-normalize": 1,
    "kv-unified": False,
    "flash-attn": "auto",
    "n-gpu-layers": 99,
    "fit": "off",
    "cache-type-k": "q8_0",
    "cache-type-v": "bf16",
    "cache-prompt": True,
    "cache-reuse": 256,
    "image-min-tokens": 64,
    "image-max-tokens": 1024,
}


def test_the_allow_list_is_exactly_the_spec_list() -> None:
    assert list(PRESET_KEYS) == list(GOOD_PRESET)


def test_every_allowed_key_with_a_value_in_range_is_accepted(folder: Path) -> None:
    assert preset_problems(GOOD_PRESET) == []
    write_config(folder, {"llamacpp_models": {"mine": entry(preset=GOOD_PRESET)}})
    assert build().llamacpp_models["mine"].preset == GOOD_PRESET
    assert read_settings_file().problems == ()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ctx-size", 512),
        ("ctx-size", 262144),
        ("batch-size", 32),
        ("batch-size", 65536),
        ("ubatch-size", 32),
        ("parallel", 1),
        ("parallel", 16),
        ("embd-normalize", -1),
        ("embd-normalize", 2),
        ("n-gpu-layers", 0),
        ("n-gpu-layers", 999),
        ("n-gpu-layers", "all"),
        ("n-gpu-layers", "auto"),
        ("cache-reuse", 0),
        ("cache-reuse", 65536),
        ("image-min-tokens", 1),
        ("image-max-tokens", 65536),
    ],
)
def test_the_range_edges_are_accepted(key: str, value: object) -> None:
    assert preset_problems({key: value}) == []


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("ctx-size", 511),
        ("ctx-size", 262145),
        ("ctx-size", 0),
        ("batch-size", 31),
        ("batch-size", 65537),
        ("ubatch-size", 31),
        ("parallel", 0),
        ("parallel", 17),
        ("parallel", -1),
        ("embd-normalize", 3),
        ("embd-normalize", -2),
        ("n-gpu-layers", -1),
        ("n-gpu-layers", 1000),
        ("n-gpu-layers", "some"),
        ("cache-reuse", -1),
        ("cache-reuse", 65537),
        ("image-min-tokens", 0),
        ("image-max-tokens", 65537),
        ("pooling", "max"),
        ("pooling", "LAST"),
        ("flash-attn", "true"),
        ("flash-attn", True),
        ("fit", "auto"),
        ("cache-type-k", "q4_1"),
        ("cache-type-v", "iq4_nl"),
        ("cache-type-k", "q5_0"),
        ("ctx-size", "4096"),
        ("ctx-size", 4096.0),
        ("ctx-size", True),
        ("parallel", False),
        ("parallel", True),
        ("cache-reuse", False),
        ("embd-normalize", True),
        ("n-gpu-layers", True),
    ],
)
def test_a_value_outside_its_rule_is_refused(key: str, value: object) -> None:
    (problem,) = preset_problems({key: value})
    assert problem.key == key and problem.reason is None
    assert problem.rule.startswith(key)


@pytest.mark.parametrize(
    "key",
    [
        "sleep-idle-seconds",
        "api-key",
        "api-key-file",
        "host",
        "port",
        "connect",
        "connect-code",
        "models-max",
        "models-preset",
        "models-dir",
        "models-memory-margin",
        "models-autoload",
        "alias",
        "hf-repo",
        "log-file",
        "model-url",
        "ssl-key-file",
        "spec-type",
        "chat-template-kwargs",
        "model",
        "mmproj",
        "no-kv-unified",
        "no-cache-prompt",
        "c",
        "LLAMA_ARG_CTX_SIZE",
        "",
    ],
)
def test_a_reserved_or_unlisted_key_is_refused_as_unknown(key: str, folder: Path) -> None:
    assert key not in PRESET_KEYS
    (problem,) = preset_problems({key: 1})
    assert (problem.key, problem.reason) == (key, PRESET_KEY_UNKNOWN)
    assert preset_problems({key: SENTINEL})[0].rule.count(SENTINEL) == 0
    loaded, problems = check_model_entry(entry(preset={key: 1}))
    assert loaded is None
    assert [(p.kind, p.reason) for p in problems] == [(KIND_UNKNOWN, PRESET_KEY_UNKNOWN)]


def test_a_reserved_key_in_the_file_is_listed_and_the_entry_is_ignored(folder: Path) -> None:
    write_config(folder, {"llamacpp_models": {"mine": entry(preset={"sleep-idle-seconds": 5})}})
    assert dict(build().llamacpp_models) == {}
    assert [(kind, key) for kind, key, _ in problems_at("llamacpp_models")] == [
        (KIND_UNKNOWN, "llamacpp_models.mine.preset.sleep-idle-seconds")
    ]


def test_free_text_in_a_value_is_refused() -> None:
    for key, value in (("pooling", "last --api-key x"), ("flash-attn", "on; rm -rf /")):
        (problem,) = preset_problems({key: value})
        assert value not in problem.rule


@pytest.mark.parametrize("value", ["maybe", 1, 0, "true", "false", None])
def test_a_boolean_takes_a_json_boolean_only(value: object) -> None:
    for key in ("cache-prompt", "kv-unified"):
        assert [p.key for p in preset_problems({key: value})] == [key]


def test_a_json_boolean_is_accepted_both_ways() -> None:
    assert preset_problems({"kv-unified": False, "cache-prompt": True}) == []


@pytest.mark.parametrize("value", [False, "false", 0, "true", 1, None])
def test_embeddings_takes_true_only(value: object) -> None:
    assert [p.key for p in preset_problems({"embeddings": value})] == ["embeddings"]


def test_embeddings_true_is_accepted() -> None:
    assert preset_problems({"embeddings": True}) == []


def test_ubatch_may_not_exceed_batch() -> None:
    (problem,) = preset_problems({"batch-size": 512, "ubatch-size": 1024})
    assert problem.key == "ubatch-size"
    assert preset_problems({"batch-size": 512, "ubatch-size": 512}) == []
    assert preset_problems({"ubatch-size": 1024}) == []  # alone, the router default applies


@pytest.mark.parametrize("preset", [[], "ctx-size", 4, None])
def test_a_preset_that_is_not_an_object_is_refused(preset: object) -> None:
    assert [p.key for p in preset_problems(preset)] == ["preset"]


def test_the_preset_types_are_exposed_for_the_writer() -> None:
    """One table of types: the ``models.ini`` writer reads it instead of repeating it."""
    kinds = {name: key.kind for name, key in PRESET_KEYS.items()}
    assert kinds["embeddings"] == "true"
    assert kinds["kv-unified"] == kinds["cache-prompt"] == "bool"
    assert kinds["ctx-size"] == "int" and (
        PRESET_KEYS["ctx-size"].low,
        PRESET_KEYS["ctx-size"].high,
    ) == (
        512,
        262144,
    )
    assert kinds["n-gpu-layers"] == "int_or_choice"
    assert PRESET_KEYS["pooling"].choices == ("none", "mean", "cls", "last", "rank")
    assert PRESET_KEYS["cache-type-k"].choices == ("f32", "f16", "bf16", "q8_0", "q4_0")
