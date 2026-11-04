"""The ``ocr_non_latin_routing`` setting (change non-latin-script-routing, task 1.1).

Flat key, env ``OCR_NON_LATIN_ROUTING``, values ``off`` (default), ``detect`` and
``always``. An unknown value stops start-up, because the value feeds the index
identity. Every test points ``OMRS_CONFIG_DIR`` at a temporary folder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omrs.config import Settings
from omrs.config.rules import DOCUMENT_READING_KEYS, document_reading_problem
from omrs.config.settings_file_write import SettingsFileRefused, write_settings
from omrs.core.settings import EffectiveSettings

KEY = "ocr_non_latin_routing"
MODES = ("off", "detect", "always")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    monkeypatch.delenv("OCR_NON_LATIN_ROUTING", raising=False)
    return root


def _settings() -> Settings:
    return Settings(_env_file=None)


def test_default_is_off() -> None:
    assert _settings().ocr_non_latin_routing == "off"
    assert EffectiveSettings().ocr_non_latin_routing == "off"


@pytest.mark.parametrize("mode", MODES)
def test_env_accepts_each_mode(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    monkeypatch.setenv("OCR_NON_LATIN_ROUTING", mode)
    assert _settings().ocr_non_latin_routing == mode


def test_unknown_env_value_stops_startup_naming_the_three(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OCR_NON_LATIN_ROUTING", "arabic")
    with pytest.raises(ValueError, match=r"off.*detect.*always"):
        _settings()


def test_effective_settings_refuse_an_unknown_value() -> None:
    with pytest.raises(ValueError, match=r"off.*detect.*always"):
        EffectiveSettings(ocr_non_latin_routing="arabic")


def test_composition_root_copies_the_value(monkeypatch: pytest.MonkeyPatch) -> None:
    from omrs.compose_settings import settings_to_effective

    monkeypatch.setenv("OCR_NON_LATIN_ROUTING", "always")
    assert settings_to_effective(_settings()).ocr_non_latin_routing == "always"


def test_key_is_a_document_reading_key_after_the_maths_key() -> None:
    assert DOCUMENT_READING_KEYS[-1] == KEY
    assert DOCUMENT_READING_KEYS[-2] == "ocr_maths_routing_enabled"


@pytest.mark.parametrize("mode", MODES)
def test_write_rule_passes_each_mode(mode: str) -> None:
    assert document_reading_problem(KEY, mode) is None


@pytest.mark.parametrize("value", ["arabic", "Detect", True, 3])
def test_write_rule_names_the_three_values(value: object) -> None:
    assert document_reading_problem(KEY, value) == "The value must be one of: off, detect, always."


def test_settings_file_write_refuses_an_unknown_value_and_changes_nothing(
    _isolated: Path,
) -> None:
    before = sorted(p.name for p in _isolated.iterdir())
    with pytest.raises(SettingsFileRefused) as caught:
        write_settings({KEY: "arabic"}, revision=None)
    assert str(caught.value) == f"{KEY}: The value must be one of: off, detect, always."
    assert sorted(p.name for p in _isolated.iterdir()) == before


def test_settings_file_write_saves_always(_isolated: Path) -> None:
    write_settings({KEY: "always"}, revision=None)
    assert '"ocr_non_latin_routing": "always"' in (_isolated / "omrs.jsonc").read_text("utf-8")


def test_starter_file_lists_the_key_with_its_environment_name() -> None:
    from omrs.transports.cli.config_template import build_template

    template = build_template()
    assert f'// "{KEY}": "off"' in template
    assert "OCR_NON_LATIN_ROUTING" in template


def test_documented_env_line_resolves_as_written(monkeypatch: pytest.MonkeyPatch) -> None:
    """The example in the configuration guide sets the value it claims to set."""
    guide = Path(__file__).resolve().parents[1] / "docs" / "guides" / "configuration.md"
    text = guide.read_text(encoding="utf-8")
    section = text.split("#### Non-Latin page routing", 1)[1].split("\n### ", 1)[0]
    lines = [ln for ln in section.splitlines() if ln.startswith("OCR_NON_LATIN_ROUTING=")]
    assert len(lines) == 1
    name, value = lines[0].split("=", 1)
    monkeypatch.setenv(name, value)
    assert _settings().ocr_non_latin_routing == value == "always"
    for mode in MODES:
        assert f"`{mode}`" in section
