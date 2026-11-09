"""Temperature, seed and allowed hosts in the answer settings (tasks 1.2 and 7.2).

Spec ``answer-sampling``: ``answer.temperature`` and ``answer.seed`` are for
the Chat model, ``answer.verify_temperature`` and ``answer.verify_seed`` for
the claim judge. Each is empty or a value: temperature 0 to 2, seed a whole
number from 0 to 2^31 - 1. ``answer.allowed_hosts`` and
``answer.verify_allowed_hosts`` hold OpenRouter host names separated by
commas; blank entries are dropped. All six resolve through the normal source
order, and the environment or ``.env`` locks each one on its own.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from omrs.compose_providers import ProviderValues, apply_provider_values, locked_fields
from omrs.config import Settings
from omrs.config.settings_file_write import ALLOWED_KEYS, SettingsFileRefused, write_settings
from omrs.core.answer.settings import AnswerSettings
from omrs.core.settings import AnswerBlock

_NUMBERS = ("temperature", "seed", "verify_temperature", "verify_seed")
_HOSTS = ("allowed_hosts", "verify_allowed_hosts")
_ENV = {
    "temperature": "ANSWER__TEMPERATURE",
    "seed": "ANSWER__SEED",
    "verify_temperature": "ANSWER__VERIFY_TEMPERATURE",
    "verify_seed": "ANSWER__VERIFY_SEED",
    "allowed_hosts": "ANSWER__ALLOWED_HOSTS",
    "verify_allowed_hosts": "ANSWER__VERIFY_ALLOWED_HOSTS",
}


def _write_config(directory: Path, answer: dict[str, Any]) -> None:
    (directory / "omrs.jsonc").write_text(json.dumps({"answer": answer}), encoding="utf-8")


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(tmp_path))
    return tmp_path


# ── defaults and ranges ──────────────────────────────────────────────────


@pytest.mark.parametrize("model", [AnswerSettings, AnswerBlock])
@pytest.mark.parametrize("field", _NUMBERS)
def test_a_number_is_empty_by_default(model: type, field: str) -> None:
    assert getattr(model(), field) is None


@pytest.mark.parametrize("model", [AnswerSettings, AnswerBlock])
@pytest.mark.parametrize("field", _HOSTS)
def test_a_host_list_is_empty_by_default(model: type, field: str) -> None:
    assert getattr(model(), field) == ""


@pytest.mark.parametrize("model", [AnswerSettings, AnswerBlock])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature", 0),
        ("temperature", 2),
        ("temperature", 0.7),
        ("verify_temperature", 0),
        ("seed", 0),
        ("seed", 2**31 - 1),
        ("seed", 20261101),
        ("verify_seed", 7),
    ],
)
def test_a_value_in_range_is_kept(model: type, field: str, value: float) -> None:
    assert getattr(model(**{field: value}), field) == value


@pytest.mark.parametrize("model", [AnswerSettings, AnswerBlock])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature", -0.1),
        ("temperature", 2.01),
        ("temperature", 3),
        ("verify_temperature", -1),
        ("seed", -1),
        ("seed", 2**31),
        ("verify_seed", -1),
        ("seed", 1.5),
    ],
)
def test_a_value_out_of_range_is_refused(model: type, field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        model(**{field: value})


@pytest.mark.parametrize("field", _HOSTS)
@pytest.mark.parametrize(
    ("raw", "kept"),
    [
        ("Fireworks", "Fireworks"),
        (" Fireworks , DeepInfra ", "Fireworks,DeepInfra"),
        ("Fireworks,, ,DeepInfra,", "Fireworks,DeepInfra"),
        (" , ", ""),
        ("deepinfra/fp8,google-vertex/us-east5", "deepinfra/fp8,google-vertex/us-east5"),
    ],
)
def test_blank_host_entries_are_dropped(field: str, raw: str, kept: str) -> None:
    assert getattr(AnswerSettings(**{field: raw}), field) == kept


@pytest.mark.parametrize("field", _HOSTS)
@pytest.mark.parametrize("raw", ["Fire;works", "a\nb", "x" * 65, ",".join(["h"] * 17)])
def test_a_bad_host_list_is_refused(field: str, raw: str) -> None:
    with pytest.raises(ValidationError):
        AnswerSettings(**{field: raw})


# ── sources: omrs.jsonc and the environment ──────────────────────────────


def test_values_read_from_omrs_jsonc(config_dir: Path) -> None:
    _write_config(config_dir, {"temperature": 0, "seed": 20261101})
    settings = Settings(_env_file=None)
    assert (settings.answer.temperature, settings.answer.seed) == (0, 20261101)
    assert (settings.answer.verify_temperature, settings.answer.verify_seed) == (None, None)


def test_host_lists_read_from_omrs_jsonc(config_dir: Path) -> None:
    _write_config(
        config_dir, {"allowed_hosts": "Fireworks, ,DeepInfra", "verify_allowed_hosts": ""}
    )
    settings = Settings(_env_file=None)
    assert settings.answer.allowed_hosts == "Fireworks,DeepInfra"
    assert settings.answer.verify_allowed_hosts == ""


@pytest.mark.parametrize(
    ("field", "text", "value"),
    [
        ("temperature", "0", 0.0),
        ("seed", "20261101", 20261101),
        ("verify_temperature", "0.2", 0.2),
        ("verify_seed", "7", 7),
        ("allowed_hosts", "Fireworks,,", "Fireworks"),
        ("verify_allowed_hosts", "Z.AI", "Z.AI"),
    ],
)
def test_the_environment_sets_each_value(
    field: str, text: str, value: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_ENV[field], text)
    assert getattr(Settings(_env_file=None).answer, field) == value


def test_an_out_of_range_environment_value_fails_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANSWER__SEED", "-1")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_the_values_reach_effective_settings() -> None:
    from omrs.compose import settings_to_effective

    answer = {
        "temperature": 0,
        "seed": 1,
        "verify_temperature": 0.5,
        "verify_seed": 2,
        "allowed_hosts": "Fireworks",
        "verify_allowed_hosts": "Z.AI",
    }
    effective = settings_to_effective(Settings(_env_file=None, answer=answer))
    assert {key: getattr(effective.answer, key) for key in answer} == answer


# ── the Settings page may write them; the environment locks each alone ───


@pytest.mark.parametrize("field", (*_NUMBERS, *_HOSTS))
def test_the_page_may_write_the_value(field: str) -> None:
    assert f"answer.{field}" in ALLOWED_KEYS


def test_a_saved_value_is_written(tmp_path: Path) -> None:
    write_settings(
        {"answer.temperature": 0, "answer.seed": 20261101}, revision=None, directory=tmp_path
    )
    text = (tmp_path / "omrs.jsonc").read_text(encoding="utf-8")
    assert '"temperature": 0' in text and '"seed": 20261101' in text


@pytest.mark.parametrize(("key", "value"), [("answer.temperature", 3), ("answer.seed", -1)])
def test_an_out_of_range_save_writes_nothing(key: str, value: int, tmp_path: Path) -> None:
    with pytest.raises(SettingsFileRefused):
        write_settings({key: value}, revision=None, directory=tmp_path)
    assert not (tmp_path / "omrs.jsonc").exists()


@pytest.mark.parametrize("field", (*_NUMBERS, *_HOSTS))
def test_the_environment_locks_only_its_own_value(
    field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(_ENV[field], "1" if field in _NUMBERS else "Fireworks")
    base = Settings(_env_file=None)
    path = f"answer.{field}"
    locked = locked_fields(base, base.provider_explicit)
    assert locked.get(path) == "environment"
    others = {f"answer.{name}" for name in (*_NUMBERS, *_HOSTS)} - {path}
    assert not others & set(locked)
    assert "answer.provider" not in locked and "answer.verify_provider" not in locked


def test_saved_values_apply_typed() -> None:
    saved = ProviderValues(
        {
            "answer.temperature": "0.0",
            "answer.seed": "20261101",
            "answer.verify_temperature": "0.5",
            "answer.allowed_hosts": "Fireworks",
        }
    )
    applied = apply_provider_values(Settings(_env_file=None), saved)
    assert applied.answer.temperature == 0.0 and isinstance(applied.answer.temperature, float)
    assert applied.answer.seed == 20261101 and isinstance(applied.answer.seed, int)
    assert applied.answer.verify_temperature == 0.5
    assert applied.answer.verify_seed is None
    assert applied.answer.allowed_hosts == "Fireworks"


def test_an_unset_saved_value_returns_to_empty() -> None:
    base = Settings(_env_file=None, answer={"temperature": 0.3, "seed": 5})
    saved = ProviderValues(unset=frozenset({"answer.temperature", "answer.seed"}))
    applied = apply_provider_values(base, saved)
    assert (applied.answer.temperature, applied.answer.seed) == (None, None)


def test_a_locked_value_beats_the_saved_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANSWER__SEED", "7")
    base = Settings(_env_file=None)
    applied = apply_provider_values(
        base, ProviderValues({"answer.seed": "9", "answer.temperature": "0"})
    )
    assert (applied.answer.seed, applied.answer.temperature) == (7, 0.0)


def test_config_init_lists_the_values() -> None:
    from omrs.transports.cli.config_template import build_template

    template = build_template()
    for field in (*_NUMBERS, *_HOSTS):
        assert f'"{field}"' in template
