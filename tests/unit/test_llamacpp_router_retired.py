"""The per-role llama.cpp settings are retired (one-llamacpp-router, task 2.4).

An environment or ``.env`` value fails start-up with a message that names the variable
and its replacement. An ``omrs.jsonc`` key is ignored and listed as ``retired`` with
its replacement. The decision entry fields that moved to ``llamacpp_models`` are listed
the same way. The retired names are flat, so they persist under the lifetime rule in
``config/legacy.py``.

Every test points ``OMRS_CONFIG_DIR`` at a temporary folder.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from omrs.config import Settings, check_legacy_env_vars, provenance
from omrs.config.legacy import _REMOVED_ENV_VARS, RETIRED_ROUTER_KEYS
from omrs.config.settings_file import KIND_RETIRED, read_settings_file
from omrs.config.settings_maps import RETIRED_DECISION_FIELDS, DecisionModelEntry

#: Retired name, the environment replacement and the file key it names.
RETIRED = [
    ("LLAMACPP_EMBED_URL", "LLAMACPP_ROUTER_URL", "llamacpp_router_url"),
    ("LLAMACPP_CHAT_URL", "LLAMACPP_ROUTER_URL", "llamacpp_router_url"),
    ("LLAMACPP_CLASSIFY_URL", "LLAMACPP_ROUTER_URL", "llamacpp_router_url"),
    ("LLAMACPP_CHAT_SERVER", "LLAMACPP_ROUTER_SERVER", "llamacpp_router_server"),
    ("LLAMACPP_EMBED_SERVER", "LLAMACPP_ROUTER_SERVER", "llamacpp_router_server"),
    ("LLAMACPP_CONTEXT_WINDOW", "llamacpp_models", "llamacpp_models"),
]


@pytest.fixture(autouse=True)
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for name, _, _ in RETIRED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return root


def write_config(root: Path, data: dict[str, Any]) -> None:
    (root / "omrs.jsonc").write_text(json.dumps(data), encoding="utf-8")


# ── Start-up ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("name", "replacement", "_key"), RETIRED)
def test_a_retired_variable_fails_start_up_and_names_its_replacement(
    name: str, replacement: str, _key: str
) -> None:
    with pytest.raises(ValueError) as caught:
        check_legacy_env_vars({name: "x"})
    text = str(caught.value)
    assert name in text and replacement in text


def test_every_retired_name_is_listed_in_the_removed_table() -> None:
    assert set(RETIRED_ROUTER_KEYS) == {name for name, _, _ in RETIRED}
    assert {name for name, _, _ in RETIRED} <= set(_REMOVED_ENV_VARS)


def test_several_retired_variables_are_all_named() -> None:
    env = {name: "x" for name, _, _ in RETIRED}
    with pytest.raises(ValueError) as caught:
        check_legacy_env_vars(env)
    assert all(name in str(caught.value) for name in env)


def test_the_old_chat_model_variable_no_longer_asks_for_a_retired_server_setting() -> None:
    with pytest.raises(ValueError) as caught:
        check_legacy_env_vars({"LLAMACPP_SERVER_MODEL": "x"})
    text = str(caught.value)
    assert "ANSWER__MODEL" in text
    assert "LLAMACPP_CHAT_SERVER" not in text


def test_the_new_names_do_not_trip_the_check() -> None:
    check_legacy_env_vars(
        {
            "LLAMACPP_ROUTER_URL": "http://127.0.0.1:1/v1",
            "LLAMACPP_ROUTER_SERVER": "managed",
            "LLAMACPP_ROUTER_MODELS_MAX": "4",
        }
    )


# ── omrs.jsonc ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(("name", "_replacement", "key"), RETIRED)
def test_a_retired_file_key_is_ignored_and_listed_with_its_replacement(
    folder: Path, name: str, _replacement: str, key: str
) -> None:
    write_config(folder, {name.lower(): "http://127.0.0.1:1/v1"})
    (problem,) = read_settings_file().problems
    assert (problem.kind, problem.key, problem.replacement) == (KIND_RETIRED, name.lower(), key)
    assert key in problem.message


def test_a_retired_file_value_is_never_read(folder: Path) -> None:
    write_config(
        folder,
        {
            "llamacpp_chat_url": "http://from-file:1/v1",
            "llamacpp_chat_server": "managed",
            "llamacpp_context_window": 4096,
        },
    )
    settings = Settings(_env_file=None)
    assert settings.llamacpp_router_url == "http://127.0.0.1:8080/v1"
    assert settings.llamacpp_router_server == "managed"
    assert {p.key for p in read_settings_file().problems} == {
        "llamacpp_chat_url",
        "llamacpp_chat_server",
        "llamacpp_context_window",
    }


def test_settings_has_no_field_for_a_retired_name() -> None:
    for name, _, _ in RETIRED:
        assert name.lower() not in Settings.model_fields
    assert not hasattr(Settings(_env_file=None), "llamacpp_chat_url")


# ── Decision entry fields ────────────────────────────────────────────────

CLEF = {
    "kind": "llamacpp",
    "address": "http://127.0.0.1:8090",
    "model": "Clef/Clef-Flash-GGUF:Q8_0",
    "images": True,
    "server": "managed",
}


@pytest.mark.parametrize("field", sorted(RETIRED_DECISION_FIELDS))
def test_an_old_decision_file_field_is_listed_as_moved_and_the_entry_loads(
    folder: Path, field: str
) -> None:
    value = "a" * 64 if field.endswith("sha256") else "/m/clef.gguf"
    write_config(folder, {"decision_models": {"clef-local": {**CLEF, field: value}}})
    (problem,) = read_settings_file().problems
    assert (problem.kind, problem.key, problem.replacement) == (
        KIND_RETIRED,
        f"decision_models.clef-local.{field}",
        "llamacpp_models",
    )
    assert "llamacpp_models" in problem.message
    assert value not in problem.message
    loaded = Settings(_env_file=None).decision_models["clef-local"]
    assert loaded.model == CLEF["model"] and loaded.server == "managed"


def test_the_decision_entry_no_longer_has_the_moved_fields() -> None:
    assert RETIRED_DECISION_FIELDS == {
        "model_file",
        "projector_file",
        "model_sha256",
        "projector_sha256",
    }
    assert not RETIRED_DECISION_FIELDS & set(DecisionModelEntry.model_fields)


def test_a_really_unknown_decision_field_is_still_unknown(folder: Path) -> None:
    write_config(folder, {"decision_models": {"clef-local": {**CLEF, "weights": "x"}}})
    (problem,) = read_settings_file().problems
    assert (problem.kind, problem.key) == ("unknown", "decision_models.clef-local.weights")
    assert "clef-local" not in Settings(_env_file=None).decision_models
