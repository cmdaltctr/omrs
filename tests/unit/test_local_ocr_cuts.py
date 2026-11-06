"""``ocr_local_cuts``: one confidence cut per local OCR backend (change local-ocr-per-backend-cuts).

Every test points ``OMRS_CONFIG_DIR`` at a temporary folder and clears the
variables it reads. No test reads the real ``~/.config/omrs``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_part_discovery_support import (
    BACKEND_DESCRIPTOR,
    fake_parts_builder,
    run_discovery,
)
from typer.testing import CliRunner

from omrs.config import Settings, provenance
from omrs.config.rules import local_cuts_problem
from omrs.config.settings_file import read_settings_file
from omrs.core import reading_parts
from omrs.core.reading_parts import LocalOcrBackendDescriptor, effective_cut
from omrs.core.settings import EffectiveSettings

_DISCOVERED = LocalOcrBackendDescriptor(
    name="ext-ocr",
    import_path="ext.ocr:BACKEND",
    label="External OCR",
    help_key="local_ocr_backend.ext-ocr",
    producer="ext_ocr",
    min_confidence=0.8,
    calibrated_by="1-external-experiment",
)


@pytest.fixture(autouse=True)
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Path]:
    for name in ("OCR_LOCAL_CUTS", "OCR_LOCAL_BACKENDS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    yield root
    reading_parts.reset_discovered()


def build(tmp_path: Path) -> Settings:
    env_file = tmp_path / "test.env"
    env_file.write_text("", encoding="utf-8")
    return Settings(_env_file=env_file)


def effective(tmp_path: Path) -> EffectiveSettings:
    from omrs.compose_settings import settings_to_effective

    return settings_to_effective(build(tmp_path))


# ── Reading the map ─────────────────────────────────────────────────────


def test_environment_map_sets_one_cut(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCR_LOCAL_BACKENDS", "pp-ocrv6-small,indra")
    monkeypatch.setenv("OCR_LOCAL_CUTS", '{"indra": 0.96}')
    settings = effective(tmp_path)
    assert effective_cut(settings, "indra") == 0.96
    assert effective_cut(settings, "pp-ocrv6-small") == 0.92


def test_file_map_sets_one_cut(folder: Path, tmp_path: Path) -> None:
    (folder / "omrs.jsonc").write_text(
        '{"ocr_local_cuts": {"pp-ocrv6-small": 0.88}}', encoding="utf-8"
    )
    settings = build(tmp_path)
    assert settings.ocr_local_cuts == {"pp-ocrv6-small": 0.88}
    assert settings.setting_sources["ocr_local_cuts"] == "config-file"
    assert effective_cut(effective(tmp_path), "pp-ocrv6-small") == 0.88


def test_entry_for_a_backend_that_is_not_listed_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCR_LOCAL_CUTS", '{"indra": 0.96}')
    settings = effective(tmp_path)
    assert settings.ocr_local_backends == ("pp-ocrv6-small",)
    assert effective_cut(settings, "pp-ocrv6-small") == 0.92


def test_integer_one_is_a_valid_cut(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCR_LOCAL_CUTS", '{"pp-ocrv6-small": 1}')
    assert build(tmp_path).ocr_local_cuts == {"pp-ocrv6-small": 1.0}


def test_default_is_an_empty_map_everywhere(tmp_path: Path) -> None:
    assert Settings.model_fields["ocr_local_cuts"].default == {}
    assert build(tmp_path).ocr_local_cuts == {}
    assert EffectiveSettings().ocr_local_cuts == {}


def test_compose_copies_the_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCR_LOCAL_CUTS", '{"pp-ocrv6-small": 0.7}')
    assert effective(tmp_path).ocr_local_cuts == {"pp-ocrv6-small": 0.7}


# ── Bad values from the environment stop start-up ───────────────────────


@pytest.mark.parametrize(
    "raw",
    [
        '{"tesseract": 0.9}',
        '{"pp-ocrv6-small": 1.2}',
        '{"pp-ocrv6-small": true}',
        '{"pp-ocrv6-small": "0.5"}',
        '{"pp-ocrv6-small": -0.1}',
    ],
)
def test_bad_environment_map_stops_start_up_and_holds_no_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv("OCR_LOCAL_CUTS", raw)
    with pytest.raises(ValueError) as caught:
        build(tmp_path)
    message = str(caught.value)
    assert "OCR_LOCAL_CUTS" in message
    assert "pp-ocrv6-small, indra" in message
    for submitted in ("1.2", "0.5", "-0.1", "0.9", "true"):
        if submitted in raw:
            assert submitted not in message.replace("0.92", "")


def test_discovered_backend_name_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reading_parts.install_discovered([_DISCOVERED])
    monkeypatch.setenv("OCR_LOCAL_CUTS", '{"ext-ocr": 0.85}')
    assert effective_cut(effective(tmp_path), "ext-ocr") == 0.85


def test_broken_discovered_backend_name_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reading_parts.install_discovered(
        [], broken=[("local_ocr_backend", "ext-broken", "ImportError")]
    )
    monkeypatch.setenv("OCR_LOCAL_CUTS", '{"ext-broken": 0.85}')
    assert build(tmp_path).ocr_local_cuts == {"ext-broken": 0.85}


# ── The shared rule ─────────────────────────────────────────────────────


def test_shared_rule_accepts_good_maps_and_empty() -> None:
    assert local_cuts_problem({}) is None
    assert local_cuts_problem({"pp-ocrv6-small": 0, "indra": 1}) is None


@pytest.mark.parametrize(
    "value",
    [
        [("pp-ocrv6-small", 0.9)],
        "pp-ocrv6-small",
        {"nope": 0.9},
        {"pp-ocrv6-small": 1.2},
        {"pp-ocrv6-small": True},
        {"pp-ocrv6-small": "0.9"},
        {"pp-ocrv6-small": None},
        {"pp-ocrv6-small": float("nan")},
        {1: 0.9},
    ],
)
def test_shared_rule_refuses_bad_maps_without_echoing_them(value: Any) -> None:
    problem = local_cuts_problem(value)
    assert problem is not None
    assert "pp-ocrv6-small, indra" in problem
    assert "1.2" not in problem
    assert "nope" not in problem


def test_shared_rule_reads_discovered_backends_at_call_time() -> None:
    assert local_cuts_problem({"ext-ocr": 0.8}) is not None
    reading_parts.install_discovered([_DISCOVERED])
    assert local_cuts_problem({"ext-ocr": 0.8}) is None


def test_shared_rule_takes_extra_descriptors() -> None:
    assert local_cuts_problem({"ext-ocr": 0.8}, extra=(_DISCOVERED,)) is None


# ── The file ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw",
    [
        '{"ocr_local_cuts": {"pp-ocrv6-small": 1.5, "indra": 0.9}}',
        '{"ocr_local_cuts": {"tesseract": 0.9}}',
        '{"ocr_local_cuts": {"pp-ocrv6-small": true}}',
        '{"ocr_local_cuts": [0.9]}',
        '{"ocr_local_cuts": 0.9}',
    ],
)
def test_bad_file_map_is_dropped_whole_and_listed_without_the_value(
    folder: Path, tmp_path: Path, raw: str
) -> None:
    (folder / "omrs.jsonc").write_text(raw, encoding="utf-8")
    file = read_settings_file()
    assert "ocr_local_cuts" not in file.values
    (problem,) = [p for p in file.problems if p.key == "ocr_local_cuts"]
    assert problem.kind == "invalid"
    assert "1.5" not in problem.message
    assert "tesseract" not in problem.message
    assert "pp-ocrv6-small, indra" in problem.message
    assert build(tmp_path).ocr_local_cuts == {}


def test_good_file_map_is_kept(folder: Path) -> None:
    (folder / "omrs.jsonc").write_text(
        '{"ocr_local_cuts": {"pp-ocrv6-small": 0.88, "indra": 1}}', encoding="utf-8"
    )
    file = read_settings_file()
    assert file.values["ocr_local_cuts"] == {"pp-ocrv6-small": 0.88, "indra": 1}
    assert not [p for p in file.problems if p.key == "ocr_local_cuts"]


# ── Where the key shows up ──────────────────────────────────────────────


def test_config_show_prints_an_empty_map_never_null(folder: Path) -> None:
    from omrs.transports.cli import app as cli_app

    result = CliRunner().invoke(cli_app, ["config", "show"])
    assert result.exit_code == 0, result.output
    (line,) = [line for line in result.output.splitlines() if re.match(r"\s+ocr_local_cuts ", line)]
    assert "null" not in line
    assert "= {}" in line


def test_config_init_shows_the_example_and_never_names_indra() -> None:
    from omrs.transports.cli.config_template import build_template

    template = build_template().splitlines()
    key = next(i for i, line in enumerate(template) if '"ocr_local_cuts"' in line)
    text = "\n".join(template[key - 1 : key + 1])
    assert "null" not in text
    assert '"ocr_local_cuts": {"pp-ocrv6-small": 0.92},' in text
    assert "Environment name: OCR_LOCAL_CUTS. Default: {}." in text
    assert "indra" not in text


def test_the_old_key_is_gone_from_both_models() -> None:
    assert "ocr_local_min_confidence" not in Settings.model_fields
    assert "ocr_local_min_confidence" not in EffectiveSettings.model_fields


def test_explicit_default_cut_keeps_the_digest(effective_settings: Any) -> None:
    from types import SimpleNamespace

    from omrs.core.ingestion.source_state import build_index_identity

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
    assert unset == digest(effective_settings(ocr_local_cuts={"pp-ocrv6-small": 0.92}))
    assert unset != digest(effective_settings(ocr_local_cuts={"pp-ocrv6-small": 0.7}))


# ── A discovered descriptor that still passes the removed field ──────────


@pytest.fixture
def fake_parts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    yield from fake_parts_builder(tmp_path, monkeypatch)


def test_a_discovered_descriptor_with_keeps_scripts_loads_broken_and_start_up_goes_on(
    fake_parts: Any,
) -> None:
    old = BACKEND_DESCRIPTOR.replace(
        'calibrated_by="fake-calibration",',
        'calibrated_by="fake-calibration",\n    keeps_scripts=None,',
    )
    fake_parts(
        "oldocr",
        {"omrs.local_ocr_backends": {"fake-ocr": "{mod:desc}:BACKEND"}},
        {"desc": old.replace("{impl}", "{mod:desc}")},
    )

    found = run_discovery()

    [part] = [p for p in found if p.distribution == "oldocr"]
    assert part.broken is True
    assert part.descriptor is None
    assert "TypeError" in (part.problem or "")
    assert "keeps_scripts" in (part.problem or "")
    assert "fake-ocr" in reading_parts.broken(reading_parts.KIND_LOCAL_OCR_BACKEND)
