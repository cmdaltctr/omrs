"""The single cut override is retired (change local-ocr-per-backend-cuts, design D7).

``OCR_LOCAL_MIN_CONFIDENCE`` and ``OCR__LOCAL_MIN_CONFIDENCE`` stop start-up and
name ``OCR_LOCAL_CUTS``. In ``omrs.jsonc`` the key is ignored and listed as
retired, and the server starts. Every test points ``OMRS_CONFIG_DIR`` at a
temporary folder.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from omrs import config
from omrs.config import Settings, provenance
from omrs.config.settings_file import read_settings_file
from omrs.core import reading_parts


@pytest.fixture(autouse=True)
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    for name in ("OCR_LOCAL_CUTS", "OCR_LOCAL_MIN_CONFIDENCE", "OCR__LOCAL_MIN_CONFIDENCE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    yield root


def build(tmp_path: Path) -> Settings:
    env_file = tmp_path / "test.env"
    env_file.write_text("", encoding="utf-8")
    return Settings(_env_file=env_file)


@pytest.mark.parametrize("name", ["OCR_LOCAL_MIN_CONFIDENCE", "OCR__LOCAL_MIN_CONFIDENCE"])
def test_old_environment_name_stops_start_up_and_names_the_replacement(name: str) -> None:
    with pytest.raises(ValueError) as caught:
        config.check_legacy_env_vars({name: "0.85"})
    message = str(caught.value)
    assert name in message
    assert "OCR_LOCAL_CUTS" in message
    assert "0.85" not in message


def test_old_name_is_in_the_start_up_tables() -> None:
    assert "OCR_LOCAL_MIN_CONFIDENCE" in config.legacy._REMOVED_ENV_VARS
    assert "OCR__LOCAL_MIN_CONFIDENCE" in config.legacy._REMOVED_ENV_VARS
    assert "OCR__LOCAL_MIN_CONFIDENCE" not in config.legacy._NEVER_SHIPPED_ALIASES


def test_old_key_in_the_file_is_ignored_and_listed_as_retired(folder: Path, tmp_path: Path) -> None:
    (folder / "omrs.jsonc").write_text('{"ocr_local_min_confidence": 0.7}', encoding="utf-8")
    file = read_settings_file()
    assert "ocr_local_min_confidence" not in file.values
    (problem,) = [p for p in file.problems if p.key == "ocr_local_min_confidence"]
    assert problem.kind == "retired"
    assert problem.replacement == "ocr_local_cuts"
    assert "ocr_local_cuts" in problem.message
    assert "0.7" not in problem.message
    settings = build(tmp_path)
    assert settings.ocr_local_cuts == {}
    assert reading_parts.effective_cut(settings, "pp-ocrv6-small") == 0.92


def test_bad_cut_in_the_file_starts_with_the_defaults_and_hides_the_value(
    folder: Path, tmp_path: Path
) -> None:
    (folder / "omrs.jsonc").write_text('{"ocr_local_cuts": {"pp-ocrv6-small": 1.5}}', "utf-8")
    file = read_settings_file()
    (problem,) = [p for p in file.problems if p.key == "ocr_local_cuts"]
    assert problem.kind == "invalid"
    assert "1.5" not in problem.message
    assert reading_parts.effective_cut(build(tmp_path), "pp-ocrv6-small") == 0.92
