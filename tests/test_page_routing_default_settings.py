"""Page routing is the default and only unit (change page-routing-default, tasks 1.1-1.2).

``ocr_routing_unit`` keeps one legal value, ``page``. An old ``document`` value
fails start-up from the environment, and is listed as a problem (never used)
from ``omrs.jsonc``. The gate settings and the maths page fraction are gone:
each environment name fails start-up, and each ``omrs.jsonc`` key is listed as
retired. Every test points ``OMRS_CONFIG_DIR`` at a temporary folder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omrs.config import Settings, check_legacy_env_vars
from omrs.config.settings_file import KIND_INVALID, KIND_RETIRED, read_settings_file
from omrs.core.settings import OCR_ROUTING_UNITS, EffectiveSettings

REMOVED = ("ocr_fallback_page_fraction", "ocr_fallback_min_confidence", "ocr_maths_page_fraction")


@pytest.fixture
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    monkeypatch.delenv("OCR_ROUTING_UNIT", raising=False)
    for key in REMOVED:
        monkeypatch.delenv(key.upper(), raising=False)
    return root


def _settings(tmp_path: Path) -> Settings:
    env_file = tmp_path / "none.env"
    env_file.write_text("", encoding="utf-8")
    return Settings(_env_file=env_file)


def test_page_is_the_only_unit() -> None:
    assert OCR_ROUTING_UNITS == ("page",)


def test_the_default_unit_is_page(folder: Path, tmp_path: Path) -> None:
    assert _settings(tmp_path).ocr_routing_unit == "page"
    assert EffectiveSettings().ocr_routing_unit == "page"


def test_a_document_value_in_the_environment_fails_start_up_naming_page(
    folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCR_ROUTING_UNIT", "document")

    with pytest.raises(ValueError) as refused:
        _settings(tmp_path)

    assert "page" in str(refused.value)
    assert "only routing unit" in str(refused.value)


def test_a_document_value_in_the_file_is_listed_and_never_used(
    folder: Path, tmp_path: Path
) -> None:
    (folder / "omrs.jsonc").write_text('{ "ocr_routing_unit": "document" }', encoding="utf-8")

    (problem,) = read_settings_file().problems

    assert (problem.kind, problem.key) == (KIND_INVALID, "ocr_routing_unit")
    assert "page" in problem.message
    assert _settings(tmp_path).ocr_routing_unit == "page"


@pytest.mark.parametrize("key", REMOVED)
def test_a_removed_variable_fails_start_up_naming_it(key: str) -> None:
    with pytest.raises(ValueError) as refused:
        check_legacy_env_vars({key.upper(): "0.2"})

    message = str(refused.value)
    assert key.upper() in message
    assert "0.2" not in message


@pytest.mark.parametrize("key", REMOVED)
def test_a_removed_file_key_is_listed_as_retired_and_never_read(folder: Path, key: str) -> None:
    (folder / "omrs.jsonc").write_text(f'{{ "{key}": 0.2 }}', encoding="utf-8")

    (problem,) = read_settings_file().problems

    assert (problem.kind, problem.key) == (KIND_RETIRED, key)
    assert "0.2" not in problem.message
    assert key not in read_settings_file().values


@pytest.mark.parametrize("key", REMOVED)
def test_neither_settings_model_has_the_removed_field(key: str) -> None:
    assert key not in Settings.model_fields
    assert key not in EffectiveSettings.model_fields


def test_the_starter_file_has_no_removed_key() -> None:
    from omrs.transports.cli.config_template import build_template

    template = build_template()
    for key in REMOVED:
        assert key not in template


@pytest.mark.parametrize("unit", ["document", "", "Page"])
def test_effective_settings_refuse_a_unit_other_than_page(unit: str) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="page"):
        EffectiveSettings(ocr_routing_unit=unit)
