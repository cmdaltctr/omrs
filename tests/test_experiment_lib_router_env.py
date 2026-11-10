"""Tests for ``experiments/_lib/router_env.py`` (change pre-exp35-harness-and-answer-fixes, D4).

The first part adapts the Experiment 48 tests of ``router_config.py`` to a small
inline plan. The sections marked "fix" and "lesson" hold the new behaviour. No
test starts a server or reads a real model file: ``SWEEP_GGUF_DIR`` points at a
tmp folder of empty ``.gguf`` files.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from experiments._lib import router_env as rc

_EMBED_ARGS = {
    "embeddings": True,
    "pooling": "last",
    "embd-normalize": 2,
    "ctx-size": 8192,
    "batch-size": 8192,
    "ubatch-size": 8192,
    "parallel": 1,
    "kv-unified": False,
    "flash-attn": True,
    "n-gpu-layers": "all",
    "fit": False,
    "cache-type-k": "f16",
    "cache-type-v": "f16",
}
_CHAT_ARGS = {
    "ctx-size": 16384,
    "parallel": 1,
    "flash-attn": True,
    "n-gpu-layers": "all",
    "fit": False,
    "cache-type-k": "f16",
    "cache-type-v": "f16",
    "spec-type": "none",
    "cache-prompt": False,
    "cache-reuse": 0,
}
BASELINE_FILE = "Qwen3-Embedding-4B-Q8_0.gguf"
CHAT_FILE = "Qwen3-4B-Q8_0.gguf"
MODELS = [
    {
        "role": "embedding-4b-baseline",
        "repository": "Qwen/Qwen3-Embedding-4B-GGUF",
        "file": BASELINE_FILE,
        "sha256": "b" * 64,
        "server_args": _EMBED_ARGS,
    },
    {
        "role": "embedding-8b",
        "repository": "Qwen/Qwen3-Embedding-8B-GGUF",
        "file": "Qwen3-Embedding-8B-Q8_0.gguf",
        "sha256": "d" * 64,
        "server_args": _EMBED_ARGS,
    },
    {
        "role": "chat-answer",
        "repository": "Qwen/Qwen3-4B-GGUF",
        "file": CHAT_FILE,
        "sha256": "8" * 64,
        "server_args": _CHAT_ARGS,
    },
]
PLAN = {"runtime": {"models": MODELS}}


@pytest.fixture
def gguf_dir(tmp_path, monkeypatch):
    """A tmp ``SWEEP_GGUF_DIR`` with one empty file per plan model."""
    folder = tmp_path / "gguf"
    folder.mkdir()
    for model in MODELS:
        (folder / model["file"]).write_bytes(b"")
    monkeypatch.setenv(rc.GGUF_DIR_ENV, str(folder))
    return folder


def _entries_by_file(values: dict) -> dict[str, dict]:
    return {Path(e["file"]).name: e for e in values["llamacpp_models"].values()}


def _expected_preset(server_args: dict) -> dict:
    """The plan values in the router's spelling: on/off words for flash-attn and fit."""
    expected = {}
    for key, value in server_args.items():
        if key == "spec-type":
            continue  # not a preset key; the b11941 default is none
        if key in ("flash-attn", "fit") and isinstance(value, bool):
            value = "on" if value else "off"
        expected[key] = value
    return expected


# --- entries come from the plan ----------------------------------------------------


def test_one_entry_per_plan_model_with_its_server_args(gguf_dir):
    values = rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE)
    entries = _entries_by_file(values)
    assert sorted(entries) == sorted(m["file"] for m in MODELS)
    for model in MODELS:
        entry = entries[model["file"]]
        assert entry["preset"] == _expected_preset(model["server_args"])
        assert entry["file"] == str(gguf_dir / model["file"])
        assert entry["sha256"] == model["sha256"]
        assert entry["model"] == f"{model['repository']}:Q8_0"


def test_every_entry_passes_the_omrs_entry_checks(gguf_dir):
    from omrs.config.llamacpp_models import (
        LlamaCppModelEntry,
        check_model_entry,
        embedding_preset_problem,
    )

    values = rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE)
    for data in values["llamacpp_models"].values():
        entry, problems = check_model_entry(data)
        assert problems == []
        assert isinstance(entry, LlamaCppModelEntry)
        if data["preset"].get("embeddings"):
            assert embedding_preset_problem(entry) is None


def test_a_spec_type_other_than_none_stops_the_run():
    args = {"ctx-size": 16384, "spec-type": "draft"}
    with pytest.raises(rc.RouterConfigError) as exc:
        rc.preset_from_server_args(args, file="x.gguf")
    assert "spec-type" in str(exc.value)
    assert "x.gguf" in str(exc.value)


def test_missing_model_file_stops_and_names_the_file(gguf_dir):
    missing = gguf_dir / "Qwen3-Embedding-8B-Q8_0.gguf"
    missing.unlink()
    with pytest.raises(rc.RouterConfigError) as exc:
        rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE)
    assert str(missing) in str(exc.value)
    assert "SWEEP_GGUF_DIR" in str(exc.value)


# --- the GGUF folder variable -------------------------------------------------------


def test_unset_gguf_dir_stops_and_names_the_variable(monkeypatch):
    monkeypatch.delenv(rc.GGUF_DIR_ENV, raising=False)
    with pytest.raises(rc.RouterConfigError) as exc:
        rc.gguf_dir()
    assert "SWEEP_GGUF_DIR" in str(exc.value)


def test_blank_gguf_dir_stops_and_names_the_variable(monkeypatch):
    monkeypatch.setenv(rc.GGUF_DIR_ENV, "  ")
    with pytest.raises(rc.RouterConfigError) as exc:
        rc.gguf_dir()
    assert "SWEEP_GGUF_DIR" in str(exc.value)


# --- router settings ----------------------------------------------------------------


def test_router_is_managed_on_loopback_scratch_port(gguf_dir):
    values = rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE)
    assert values["llamacpp_router_server"] == "managed"
    assert values["llamacpp_router_url"] == f"http://127.0.0.1:{rc.ROUTER_PORT}/v1"
    assert rc.ROUTER_PORT == 18080
    assert values["embed_provider"] == "llamacpp"
    assert values["local_backend"] == "llamacpp"
    assert values["metadata_llm_provider"] == "local"
    assert values["answer"]["verify_provider"] == "local"


def test_roles_name_the_listed_models(gguf_dir):
    values = rc.build_settings(PLAN, gguf_dir, embed_file="Qwen3-Embedding-8B-Q8_0.gguf")
    names = {Path(e["file"]).name: e["model"] for e in values["llamacpp_models"].values()}
    assert values["llamacpp_embed_model"] == names["Qwen3-Embedding-8B-Q8_0.gguf"]
    assert values["llamacpp_chat_model"] == names[CHAT_FILE]
    assert values["answer"]["model"] == names[CHAT_FILE]
    assert values["answer"]["verify_model"] == names[CHAT_FILE]


def test_part_b_loads_one_model_at_a_time(gguf_dir):
    values = rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE, part_b=True)
    assert values["llamacpp_router_models_max"] == 1


def test_part_a_leaves_the_model_limit_at_its_default(gguf_dir):
    values = rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE)
    assert "llamacpp_router_models_max" not in values


def test_fast_mode_differs_from_exact_by_the_two_keys_only(gguf_dir):
    exact = _entries_by_file(rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE))
    fast = _entries_by_file(rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE, fast=True))
    for name in exact:
        if name != BASELINE_FILE:
            assert fast[name] == exact[name]
    left, right = exact[BASELINE_FILE]["preset"], fast[BASELINE_FILE]["preset"]
    changed = {k: right[k] for k in right if left.get(k) != right[k]}
    assert changed == {"parallel": 8, "kv-unified": True}
    assert set(left) == set(right)


# --- the written file and the OMRS settings code -------------------------------------


def test_written_file_has_no_omrs_problems_and_settings_load(gguf_dir, tmp_path, monkeypatch):
    config = tmp_path / "config"
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(config))
    monkeypatch.setenv("OMRS_STATE_DIR", str(tmp_path / "state"))
    for name in [k for k in os.environ if k.startswith("LLAMACPP_")]:
        monkeypatch.delenv(name)
    values = rc.build_settings(PLAN, gguf_dir, embed_file=BASELINE_FILE, part_b=True)
    rc.write_settings(values, config)
    rc.check_settings_file(config)  # raises on any problem
    settings = rc.load_settings()
    assert settings.llamacpp_router_url == values["llamacpp_router_url"]
    assert settings.llamacpp_router_server == "managed"
    assert settings.llamacpp_router_models_max == 1


def test_a_problem_in_the_file_stops_and_names_the_key(tmp_path):
    config = tmp_path / "config"
    rc.write_settings({"llamacpp_router_models_max": 99}, config)
    with pytest.raises(rc.RouterConfigError) as exc:
        rc.check_settings_file(config)
    assert "llamacpp_router_models_max" in str(exc.value)


# --- environment set-up ---------------------------------------------------------------


def test_prepare_environment_removes_every_llamacpp_key_and_points_at_the_folders(tmp_path):
    environ = {"LLAMACPP_EMBED_URL": "x", "LLAMACPP_CHAT_MODEL": "y", "HOME": "/h"}
    removed = rc.prepare_environment(
        {"VECTOR_STORE": "lancedb"},
        config_dir=tmp_path / "config",
        state_dir=tmp_path / "state",
        environ=environ,
    )
    assert sorted(removed) == ["LLAMACPP_CHAT_MODEL", "LLAMACPP_EMBED_URL"]
    assert not [k for k in environ if k.startswith("LLAMACPP_")]
    assert environ["OMRS_CONFIG_DIR"] == str(tmp_path / "config")
    assert environ["OMRS_STATE_DIR"] == str(tmp_path / "state")
    assert environ["VECTOR_STORE"] == "lancedb"


# --- lesson: omrs.jsonc values must not be beaten by stray environment overrides -------

_ROUTING_ENV = (
    "EMBED_PROVIDER",
    "EMBED_MODEL",
    "LOCAL_BACKEND",
    "METADATA_LLM_PROVIDER",
    "ANSWER__PROVIDER",
    "ANSWER__MODEL",
    "ANSWER__VERIFY_PROVIDER",
    "ANSWER__VERIFY_MODEL",
)


@pytest.fixture
def clean_env(gguf_dir, tmp_path, monkeypatch):
    """Scratch folders and none of the environment names the sweep file pins."""
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("OMRS_STATE_DIR", str(tmp_path / "state"))
    for name in [k for k in os.environ if k.startswith("LLAMACPP_")] + list(_ROUTING_ENV):
        monkeypatch.delenv(name, raising=False)
    return tmp_path / "config"


def test_configure_passes_when_nothing_overrides_the_file(clean_env):
    rc.configure(PLAN, embed_file=BASELINE_FILE, config_dir=clean_env)


def test_an_environment_embed_provider_stops_the_run_and_names_the_key(clean_env, monkeypatch):
    monkeypatch.setenv("EMBED_PROVIDER", "ollama")
    monkeypatch.setenv("EMBED_MODEL", "qwen3-embedding:8b")  # OMRS needs it with ollama
    with pytest.raises(rc.RouterConfigError) as exc:
        rc.configure(PLAN, embed_file=BASELINE_FILE, config_dir=clean_env)
    text = str(exc.value)
    assert "embed_provider" in text and "ollama" in text and "llamacpp" in text


def test_an_environment_answer_provider_stops_the_run_and_names_the_key(clean_env, monkeypatch):
    monkeypatch.setenv("ANSWER__PROVIDER", "openrouter")
    with pytest.raises(rc.RouterConfigError, match=r"answer\.provider"):
        rc.configure(PLAN, embed_file=BASELINE_FILE, config_dir=clean_env)


# --- fix 3.5: the GGUF folder is resolved to an absolute path when it is read ----------


def test_a_relative_gguf_folder_becomes_absolute_at_read_time(tmp_path, monkeypatch):
    (tmp_path / "models" / "gguf").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(rc.GGUF_DIR_ENV, "models/gguf")
    folder = rc.gguf_dir()
    assert folder.is_absolute()
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)  # a later step runs from another working folder
    assert folder == (tmp_path / "models" / "gguf").resolve()
    assert folder.is_dir()


def test_a_relative_gguf_folder_gives_absolute_model_paths_after_the_folder_changes(
    tmp_path, monkeypatch
):
    folder = tmp_path / "models" / "gguf"
    folder.mkdir(parents=True)
    for model in MODELS:
        (folder / model["file"]).write_bytes(b"")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(rc.GGUF_DIR_ENV, "models/gguf")
    values = rc.build_settings(PLAN, rc.gguf_dir(), embed_file=BASELINE_FILE)
    monkeypatch.chdir(tmp_path / "models")
    for entry in values["llamacpp_models"].values():
        assert Path(entry["file"]).is_absolute()
        assert Path(entry["file"]).is_file()


def test_a_missing_gguf_folder_is_refused_and_names_the_variable_and_the_path(
    tmp_path, monkeypatch
):
    missing = tmp_path / "no-such-folder"
    monkeypatch.setenv(rc.GGUF_DIR_ENV, str(missing))
    with pytest.raises(rc.RouterConfigError) as exc:
        rc.gguf_dir()
    assert "SWEEP_GGUF_DIR" in str(exc.value)
    assert str(missing) in str(exc.value)


def test_a_gguf_path_that_is_a_file_is_refused(tmp_path, monkeypatch):
    not_a_folder = tmp_path / "gguf"
    not_a_folder.write_bytes(b"")
    monkeypatch.setenv(rc.GGUF_DIR_ENV, str(not_a_folder))
    with pytest.raises(rc.RouterConfigError, match="SWEEP_GGUF_DIR"):
        rc.gguf_dir()


def test_configure_with_a_missing_gguf_folder_stops_before_any_settings_are_written(
    tmp_path, monkeypatch
):
    """Nothing is written, so no router can be started from this run's settings."""
    monkeypatch.setenv(rc.GGUF_DIR_ENV, str(tmp_path / "no-such-folder"))
    config = tmp_path / "config"
    with pytest.raises(rc.RouterConfigError, match="SWEEP_GGUF_DIR"):
        rc.configure(PLAN, embed_file=BASELINE_FILE, config_dir=config)
    assert not config.exists()


# --- a key reference is never compared or printed (2026-11-10) ---


def test_resolved_conflicts_never_names_a_resolved_key_value() -> None:
    from types import SimpleNamespace

    from experiments._lib.router_env import resolved_conflicts

    secret = "resolved-secret-value-1234"  # noqa: S105 - test value, not a key
    settings = SimpleNamespace(
        openai_compatible_api_key=secret,
        answer=SimpleNamespace(verify_model="other-model"),
    )
    values = {"openai_compatible_api_key": "env://SOME_KEY", "answer": {"verify_model": "m"}}
    problems = resolved_conflicts(settings, values)
    assert problems == ["answer.verify_model: the sweep needs 'm', OMRS resolved 'other-model'"]
    assert all(secret not in p for p in problems)
