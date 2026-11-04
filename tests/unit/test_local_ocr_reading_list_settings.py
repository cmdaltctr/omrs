"""The ``ocr_local_backends`` list setting (change local-ocr-backends, task 4.3, design D8).

Every test points ``OMRS_CONFIG_DIR`` at a temporary folder and clears the
variable it reads. No test reads the real ``~/.config/omrs``. A second backend
comes from a fake descriptor patched into the descriptor table.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omrs.config import Settings, provenance
from omrs.config.rules import local_backend_problem
from omrs.config.settings_file import read_settings_file
from omrs.config.user_config import parse_jsonc
from omrs.core import reading_parts
from omrs.core.reading_parts import LocalOcrBackendDescriptor
from omrs.core.settings import EffectiveSettings

_CUT = LocalOcrBackendDescriptor(
    name="fake-cut",
    import_path="tests.fake:BACKEND",
    label="Fake with cut",
    help_key="local_ocr_backend.fake-cut",
    producer="fake_cut_ocr",
    min_confidence=0.8,
    calibrated_by="1-fake-experiment",
)
_NO_CUT = LocalOcrBackendDescriptor(
    name="fake-no-cut",
    import_path="tests.fake:BACKEND",
    label="Fake without cut",
    help_key="local_ocr_backend.fake-no-cut",
    producer="fake_no_cut_ocr",
)


@pytest.fixture(autouse=True)
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.delenv("OCR_LOCAL_BACKENDS", raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return root


@pytest.fixture
def two_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    table = (*reading_parts.LOCAL_OCR_BACKENDS, _CUT, _NO_CUT)
    monkeypatch.setattr(reading_parts, "LOCAL_OCR_BACKENDS", table)


def build(tmp_path: Path, dotenv: str = "") -> Settings:
    env_file = tmp_path / "test.env"
    env_file.write_text(dotenv, encoding="utf-8")
    return Settings(_env_file=env_file)


def test_default_list_is_the_default_descriptor(tmp_path: Path) -> None:
    settings = build(tmp_path)
    assert settings.ocr_local_backends == ("pp-ocrv6-small",)
    assert reading_parts.DEFAULT_LOCAL_OCR_BACKENDS == ("pp-ocrv6-small",)
    assert settings.setting_sources.get("ocr_local_backends", "default") == "default"


def test_effective_settings_default_is_pinned_to_the_descriptor() -> None:
    """``core/settings.py`` imports nothing from ``omrs.core``, so it writes the literal."""
    assert EffectiveSettings().ocr_local_backends == reading_parts.DEFAULT_LOCAL_OCR_BACKENDS


def test_environment_list_is_comma_separated_and_trimmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, two_fakes: None
) -> None:
    monkeypatch.setenv("OCR_LOCAL_BACKENDS", " fake-cut , pp-ocrv6-small ,, ")
    settings = build(tmp_path)
    assert settings.ocr_local_backends == ("fake-cut", "pp-ocrv6-small")
    assert settings.setting_sources["ocr_local_backends"] == "env"


def test_blank_environment_value_means_the_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCR_LOCAL_BACKENDS", " , ")
    assert build(tmp_path).ocr_local_backends == ("pp-ocrv6-small",)


def test_file_array_is_read(folder: Path, tmp_path: Path, two_fakes: None) -> None:
    (folder / "omrs.jsonc").write_text(
        '{"ocr_local_backends": ["pp-ocrv6-small", "fake-cut"]}', encoding="utf-8"
    )
    settings = build(tmp_path)
    assert settings.ocr_local_backends == ("pp-ocrv6-small", "fake-cut")
    assert settings.setting_sources["ocr_local_backends"] == "config-file"


def test_unknown_name_stops_start_up_and_names_accepted_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCR_LOCAL_BACKENDS", "tesseract")
    with pytest.raises(ValueError) as caught:
        build(tmp_path)
    message = str(caught.value)
    assert "OCR_LOCAL_BACKENDS='tesseract' is not valid." in message
    assert "Each name must be a local OCR backend." in message
    assert "Accepted values: pp-ocrv6-small." in message


def test_backend_without_a_cut_stops_start_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, two_fakes: None
) -> None:
    monkeypatch.setenv("OCR_LOCAL_BACKENDS", "pp-ocrv6-small,fake-no-cut")
    with pytest.raises(ValueError) as caught:
        build(tmp_path)
    message = str(caught.value)
    assert "OCR_LOCAL_BACKENDS='pp-ocrv6-small,fake-no-cut' is not valid." in message
    assert "A backend with no calibrated confidence cut cannot be listed." in message
    # A backend without a cut is never offered as an accepted value.
    assert "Accepted values: pp-ocrv6-small, fake-cut." in message


def test_bad_file_value_is_dropped_and_named_without_the_value(folder: Path) -> None:
    (folder / "omrs.jsonc").write_text('{"ocr_local_backends": ["tesseract"]}', encoding="utf-8")
    file = read_settings_file()
    assert "ocr_local_backends" not in file.values
    (problem,) = [p for p in file.problems if p.key == "ocr_local_backends"]
    assert "tesseract" not in problem.message
    assert "pp-ocrv6-small" in problem.message


def test_extra_descriptors_join_the_accepted_set() -> None:
    """Group 5 passes discovered descriptors here; nothing discovered keeps today's set."""
    assert local_backend_problem(("fake-cut",)) is not None
    assert local_backend_problem(("fake-cut",), extra=(_CUT,)) is None
    assert local_backend_problem(("pp-ocrv6-small",)) is None


def test_compose_maps_the_list_into_effective_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, two_fakes: None
) -> None:
    from omrs.compose_settings import settings_to_effective

    monkeypatch.setenv("OCR_LOCAL_BACKENDS", "fake-cut,pp-ocrv6-small")
    effective = settings_to_effective(build(tmp_path))
    assert effective.ocr_local_backends == ("fake-cut", "pp-ocrv6-small")


def test_config_init_lists_the_key() -> None:
    from omrs.transports.cli.config_template import build_template

    text = build_template()
    assert 'Environment name: OCR_LOCAL_BACKENDS. Default: ["pp-ocrv6-small"].' in text
    line = next(line for line in text.splitlines() if '"ocr_local_backends"' in line)
    assert parse_jsonc("{" + line.strip().removeprefix("//").rstrip(",") + "}") == {
        "ocr_local_backends": ["pp-ocrv6-small"]
    }
