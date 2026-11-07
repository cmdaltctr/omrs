"""The ``ocr_skip_blank_pages`` setting (change page-routing-panel, task 1.1, design D3).

A flat key, environment ``OCR_SKIP_BLANK_PAGES``, plain ``bool``, default
``True``. Text that is not a boolean stops start-up when it comes from the
environment, and is listed as invalid and ignored when it comes from
``omrs.jsonc``. Every test points ``OMRS_CONFIG_DIR`` at a temporary folder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omrs.config import Settings, provenance
from omrs.config.settings_file import KIND_INVALID, read_settings_file
from omrs.core import reading_parts
from omrs.core.reading_parts import SettingField
from omrs.core.settings import EffectiveSettings

KEY = "ocr_skip_blank_pages"
ENV = "OCR_SKIP_BLANK_PAGES"


@pytest.fixture(autouse=True)
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.delenv(ENV, raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return root


def _settings() -> Settings:
    return Settings(_env_file=None)


def _write(root: Path, text: str) -> None:
    (root / "omrs.jsonc").write_text(text, encoding="utf-8")


def test_the_default_is_true() -> None:
    assert _settings().ocr_skip_blank_pages is True
    assert EffectiveSettings().ocr_skip_blank_pages is True


@pytest.mark.parametrize("text", ["false", "0", "no", "off", "FALSE"])
def test_the_environment_turns_it_off(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    monkeypatch.setenv(ENV, text)
    assert _settings().ocr_skip_blank_pages is False


def test_environment_text_that_is_not_a_boolean_stops_start_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV, "sometimes")
    with pytest.raises(ValueError, match=KEY):
        _settings()


def test_the_file_turns_it_off_with_source_config_file(folder: Path) -> None:
    _write(folder, '{ "ocr_skip_blank_pages": false }')
    settings = _settings()
    assert settings.ocr_skip_blank_pages is False
    assert settings.setting_sources.get(KEY) == "config-file"


def test_a_bad_file_value_is_listed_invalid_and_the_default_stays(folder: Path) -> None:
    _write(folder, '{ "ocr_skip_blank_pages": "sometimes" }')
    problems = [(p.kind, p.key) for p in read_settings_file().problems]
    assert (KIND_INVALID, KEY) in problems
    assert _settings().ocr_skip_blank_pages is True


def test_effective_settings_carry_the_value_from_the_composition_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from omrs.compose_settings import settings_to_effective

    monkeypatch.setenv(ENV, "false")
    assert settings_to_effective(_settings()).ocr_skip_blank_pages is False
    monkeypatch.delenv(ENV)
    assert settings_to_effective(_settings()).ocr_skip_blank_pages is True


def test_the_blank_descriptor_declares_the_one_setting() -> None:
    blank = reading_parts.by_name(reading_parts.PAGE_RULES, "blank")
    assert blank.settings == (SettingField(name=KEY, env=ENV, default=True, enters_identity=True),)
