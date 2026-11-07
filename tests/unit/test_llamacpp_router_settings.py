"""The four llama.cpp router settings (one-llamacpp-router, task 2.1).

``llamacpp_router_server``, ``llamacpp_router_url``, ``llamacpp_router_models_max``
and ``llamacpp_router_memory_margin_mib`` follow the provider source order: the
environment and ``.env`` win and lock, ``omrs.jsonc`` does not lock, then the
default. Every test points ``OMRS_CONFIG_DIR`` at a temporary folder. Addresses
here are fake constants.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from omrs.config import Settings, provenance
from omrs.config.llamacpp_router_rules import LOOPBACK_RULE, router_url_problem
from omrs.config.provider_sources import PROVIDER_FIELDS
from omrs.config.rules import ACCEPTED, ADDRESS_FIELDS
from omrs.config.settings_file import KIND_INVALID, read_settings_file
from omrs.config.settings_file_write import read_only_reason
from omrs.config.user_config import INT_KEY_BOUNDS

KEYS = (
    "llamacpp_router_server",
    "llamacpp_router_url",
    "llamacpp_router_models_max",
    "llamacpp_router_memory_margin_mib",
)
VARIABLES = tuple(key.upper() for key in KEYS)


@pytest.fixture(autouse=True)
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())  # a repo .env must not leak in
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return root


def write_config(root: Path, data: dict[str, Any]) -> None:
    (root / "omrs.jsonc").write_text(json.dumps(data), encoding="utf-8")


def build(tmp_path: Path, dotenv: str = "") -> Settings:
    env_file = tmp_path / "test.env"
    env_file.write_text(dotenv, encoding="utf-8")
    return Settings(_env_file=env_file)


def source_of(settings: Settings, path: str) -> str:
    return settings.setting_sources.get(path, "default")


# ── Defaults ─────────────────────────────────────────────────────────────


def test_defaults(tmp_path: Path) -> None:
    settings = build(tmp_path)
    assert settings.llamacpp_router_server == "managed"
    assert settings.llamacpp_router_url == "http://127.0.0.1:8080/v1"
    assert settings.llamacpp_router_models_max == 4
    assert settings.llamacpp_router_memory_margin_mib == 8192
    assert not any(source_of(settings, key) != "default" for key in KEYS)


def test_the_ranges_have_one_home() -> None:
    """The model ranges are read from ``INT_KEY_BOUNDS`` and listed there only."""
    assert INT_KEY_BOUNDS["llamacpp_router_models_max"] == (1, 16)
    assert INT_KEY_BOUNDS["llamacpp_router_memory_margin_mib"] == (0, 262144)
    for key in ("llamacpp_router_models_max", "llamacpp_router_memory_margin_mib"):
        low, high = INT_KEY_BOUNDS[key]
        bounds = {type(m).__name__: m for m in Settings.model_fields[key].metadata}
        assert (bounds["Ge"].ge, bounds["Le"].le) == (low, high)
        assert key in PROVIDER_FIELDS


def test_the_accepted_modes_and_the_address_rule_are_listed() -> None:
    assert ACCEPTED["llamacpp_router_server"] == ("managed", "external")
    assert "llamacpp_router_url" in ADDRESS_FIELDS
    assert "llamacpp_router_url" in PROVIDER_FIELDS
    assert "llamacpp_router_server" in PROVIDER_FIELDS


# ── Source order ─────────────────────────────────────────────────────────


def test_the_dotenv_value_wins_over_the_file_and_locks(folder: Path, tmp_path: Path) -> None:
    write_config(folder, {"llamacpp_router_url": "http://from-file:1/v1"})
    settings = build(tmp_path, "LLAMACPP_ROUTER_URL=http://from-dotenv:2/v1\n")
    assert settings.llamacpp_router_url == "http://from-dotenv:2/v1"
    assert source_of(settings, "llamacpp_router_url") == "dotenv"
    assert "llamacpp_router_url" in settings.provider_explicit
    assert "llamacpp_router_url" not in settings.config_file_fields


def test_the_environment_wins_over_the_file_and_locks(
    monkeypatch: pytest.MonkeyPatch, folder: Path, tmp_path: Path
) -> None:
    write_config(folder, {"llamacpp_router_server": "managed"})
    monkeypatch.setenv("LLAMACPP_ROUTER_SERVER", "external")
    settings = build(tmp_path)
    assert settings.llamacpp_router_server == "external"
    assert source_of(settings, "llamacpp_router_server") == "env"
    assert "llamacpp_router_server" in settings.provider_explicit


def test_a_file_value_is_used_and_does_not_lock(folder: Path, tmp_path: Path) -> None:
    write_config(
        folder,
        {
            "llamacpp_router_server": "external",
            "llamacpp_router_url": "http://127.0.0.1:9931/v1",
            "llamacpp_router_models_max": 2,
            "llamacpp_router_memory_margin_mib": 0,
        },
    )
    settings = build(tmp_path)
    assert settings.llamacpp_router_server == "external"
    assert settings.llamacpp_router_url == "http://127.0.0.1:9931/v1"
    assert settings.llamacpp_router_models_max == 2
    assert settings.llamacpp_router_memory_margin_mib == 0
    for key in KEYS:
        assert source_of(settings, key) == "config-file"
        assert key not in settings.provider_explicit


def test_a_whole_number_from_the_environment_is_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LLAMACPP_ROUTER_MODELS_MAX", "16")
    monkeypatch.setenv("LLAMACPP_ROUTER_MEMORY_MARGIN_MIB", "262144")
    settings = build(tmp_path)
    assert (settings.llamacpp_router_models_max, settings.llamacpp_router_memory_margin_mib) == (
        16,
        262144,
    )


# ── Refusals ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("llamacpp_router_models_max", 0),
        ("llamacpp_router_models_max", 17),
        ("llamacpp_router_memory_margin_mib", -1),
        ("llamacpp_router_memory_margin_mib", 262145),
        ("llamacpp_router_models_max", True),
    ],
)
def test_an_out_of_range_file_value_is_ignored_and_listed(
    folder: Path, tmp_path: Path, key: str, bad: object
) -> None:
    write_config(folder, {key: bad})
    (problem,) = read_settings_file().problems
    assert (problem.kind, problem.key) == (KIND_INVALID, key)
    assert "whole number" in problem.message
    assert getattr(build(tmp_path), key) == Settings.model_fields[key].default


@pytest.mark.parametrize(
    ("variable", "bad"),
    [
        ("LLAMACPP_ROUTER_MODELS_MAX", "0"),
        ("LLAMACPP_ROUTER_MODELS_MAX", "17"),
        ("LLAMACPP_ROUTER_MEMORY_MARGIN_MIB", "-1"),
        ("LLAMACPP_ROUTER_MEMORY_MARGIN_MIB", "262145"),
    ],
)
def test_an_out_of_range_environment_value_fails_start_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, variable: str, bad: str
) -> None:
    monkeypatch.setenv(variable, bad)
    with pytest.raises(ValidationError):
        build(tmp_path)


def test_an_unknown_mode_is_ignored_and_names_both_words(folder: Path, tmp_path: Path) -> None:
    write_config(folder, {"llamacpp_router_server": "router"})
    (problem,) = read_settings_file().problems
    assert (problem.kind, problem.key) == (KIND_INVALID, "llamacpp_router_server")
    assert "managed" in problem.message and "external" in problem.message
    assert "router" not in problem.message
    assert build(tmp_path).llamacpp_router_server == "managed"


def test_an_unknown_mode_in_the_environment_fails_start_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LLAMACPP_ROUTER_SERVER", "router")
    with pytest.raises(ValueError, match="LLAMACPP_ROUTER_SERVER"):
        build(tmp_path)


def test_a_file_url_for_the_address_is_ignored_and_listed(folder: Path, tmp_path: Path) -> None:
    write_config(folder, {"llamacpp_router_url": "file:///etc/passwd"})
    (problem,) = read_settings_file().problems
    assert (problem.kind, problem.key) == (KIND_INVALID, "llamacpp_router_url")
    assert build(tmp_path).llamacpp_router_url == "http://127.0.0.1:8080/v1"


# ── The loopback rule for a managed router ───────────────────────────────


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:8080/v1", "http://localhost:9000/v1", "http://[::1]:8080/v1"],
)
def test_a_managed_router_accepts_a_loopback_address(url: str) -> None:
    assert router_url_problem("managed", url) is None


@pytest.mark.parametrize(
    "url",
    ["http://192.168.1.5:8080/v1", "https://127.0.0.1:8080/v1", "http://example.test/v1"],
)
def test_a_managed_router_refuses_any_other_address(url: str) -> None:
    assert router_url_problem("managed", url) == LOOPBACK_RULE
    assert url not in LOOPBACK_RULE


def test_an_external_router_accepts_any_http_address() -> None:
    assert router_url_problem("external", "https://llama.example.test/v1") is None
    assert router_url_problem("external", "http://192.168.1.5:8080/v1") is None


@pytest.mark.parametrize("mode", ["managed", "external"])
def test_every_mode_refuses_a_bad_address(mode: str) -> None:
    assert router_url_problem(mode, "ftp://127.0.0.1/v1") is not None
    assert router_url_problem(mode, "") is not None


# ── Page writes ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("key", KEYS)
def test_the_page_may_write_each_router_setting(key: str) -> None:
    assert read_only_reason(key) is None


def test_the_page_never_writes_the_model_list() -> None:
    assert read_only_reason("llamacpp_models") is not None
    assert "llamacpp_models" not in json.dumps(list(PROVIDER_FIELDS))
