"""``ocr_local_min_confidence`` as an optional override (change local-ocr-backends, task 4.4).

Design D9: the cut belongs to the backend. Unset, each listed backend uses
its own calibrated cut. Set, the value replaces the cut of every listed
backend. Every test points ``OMRS_CONFIG_DIR`` at a temporary folder.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from omrs.config import Settings, provenance
from omrs.core import reading_parts
from omrs.core.ingestion.ocr_identity import ocr_routing_payload
from omrs.core.ingestion.source_state import build_index_identity
from omrs.core.reading_parts import LocalOcrBackendDescriptor, effective_cut
from omrs.core.settings import EffectiveSettings

_FAKE = LocalOcrBackendDescriptor(
    name="fake-cut",
    import_path="tests.fake:BACKEND",
    label="Fake with cut",
    help_key="local_ocr_backend.fake-cut",
    producer="fake_cut_ocr",
    min_confidence=0.8,
    calibrated_by="1-fake-experiment",
)


@pytest.fixture(autouse=True)
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.delenv("OCR_LOCAL_MIN_CONFIDENCE", raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return root


def build(tmp_path: Path) -> Settings:
    env_file = tmp_path / "test.env"
    env_file.write_text("", encoding="utf-8")
    return Settings(_env_file=env_file)


def test_unset_is_the_default_everywhere(tmp_path: Path) -> None:
    assert build(tmp_path).ocr_local_min_confidence is None
    assert EffectiveSettings().ocr_local_min_confidence is None
    (setting,) = [
        s
        for s in reading_parts.local_backend("pp-ocrv6-small").settings
        if s.name == "ocr_local_min_confidence"
    ]
    assert setting.default is None


def test_set_value_is_read_and_range_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCR_LOCAL_MIN_CONFIDENCE", "0.7")
    assert build(tmp_path).ocr_local_min_confidence == 0.7
    monkeypatch.setenv("OCR_LOCAL_MIN_CONFIDENCE", "1.5")
    with pytest.raises(ValueError):
        build(tmp_path)


def test_unset_gives_each_backend_its_own_cut(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        reading_parts, "LOCAL_OCR_BACKENDS", (*reading_parts.LOCAL_OCR_BACKENDS, _FAKE)
    )
    settings = EffectiveSettings()
    assert effective_cut(settings, "pp-ocrv6-small") == 0.9
    assert effective_cut(settings, "fake-cut") == 0.8


def test_set_value_replaces_the_cut_of_every_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        reading_parts, "LOCAL_OCR_BACKENDS", (*reading_parts.LOCAL_OCR_BACKENDS, _FAKE)
    )
    settings = EffectiveSettings(ocr_local_min_confidence=0.7)
    assert effective_cut(settings, "pp-ocrv6-small") == 0.7
    assert effective_cut(settings, "fake-cut") == 0.7


def test_compose_maps_unset_and_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from omrs.compose_settings import settings_to_effective

    assert settings_to_effective(build(tmp_path)).ocr_local_min_confidence is None
    monkeypatch.setenv("OCR_LOCAL_MIN_CONFIDENCE", "0.75")
    assert settings_to_effective(build(tmp_path)).ocr_local_min_confidence == 0.75


def test_unset_routing_payload_holds_the_default_cut(effective_settings: Any) -> None:
    """Byte-identical ``local_tier`` for unset and for an explicit 0.9."""
    unset = ocr_routing_payload(effective_settings())
    explicit = ocr_routing_payload(effective_settings(ocr_local_min_confidence=0.9))
    assert unset["local_tier"] == {"min_confidence": 0.9}
    assert unset == explicit


def test_explicit_default_cut_keeps_the_digest(effective_settings: Any) -> None:
    def digest(settings: Any) -> str:
        return build_index_identity(
            settings,
            content_type="application/pdf",
            chunk_size=512,
            chunk_overlap=100,
            pdf_reader_revision=2,
            embed_model=SimpleNamespace(model_name="pinned-embedder"),
        )

    unset = digest(effective_settings())
    assert unset == digest(effective_settings(ocr_local_min_confidence=0.9))
    assert unset != digest(effective_settings(ocr_local_min_confidence=0.7))


def test_config_init_prints_unset_and_never_null() -> None:
    from omrs.transports.cli.config_template import build_template

    lines = [line for line in build_template().splitlines() if "ocr_local_min_confidence" in line]
    text = "\n".join(lines)
    assert "null" not in text
    assert '"ocr_local_min_confidence": 0.9,' in text
    comment = next(
        line
        for line in build_template().splitlines()
        if "Environment name: OCR_LOCAL_MIN_CONFIDENCE." in line
    )
    assert "Default: unset" in comment


def test_config_show_prints_unset_and_never_null(folder: Path) -> None:
    from omrs.transports.cli import app as cli_app

    result = CliRunner().invoke(cli_app, ["config", "show"])
    assert result.exit_code == 0, result.output
    (line,) = [
        line
        for line in result.output.splitlines()
        if re.match(r"\s+ocr_local_min_confidence ", line)
    ]
    assert "null" not in line
    assert "= not set" in line
