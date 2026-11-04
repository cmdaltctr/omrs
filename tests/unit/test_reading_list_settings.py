"""Ordered reader and engine lists in ``Settings`` (ordered-reader-and-ocr-lists, tasks 1.1 to 1.3).

Every test points ``OMRS_CONFIG_DIR`` at a temporary folder and clears the
variables it cares about. No test reads the real ``~/.config/omrs``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from omrs.config import Settings, check_legacy_env_vars, provenance
from omrs.config.reading_lists import ReadingListMixin
from omrs.config.rules import OLD_READING_KEYS, TEMPLATE_SKIPPED_FIELDS
from omrs.config.setting_shapes import KIND_LIST, is_scalar, setting_shape
from omrs.config.settings_file import KIND_INVALID, KIND_RETIRED, read_settings_file
from omrs.config.settings_file_write import ALLOWED_KEYS, write_settings
from omrs.config.user_config import parse_jsonc
from omrs.core.reading_lists import (
    AUTO_READERS,
    OCR_ENGINES_DEFAULT,
    PDF_READERS_DEFAULT,
    engine_list,
    expand_ocr_engines,
    expand_pdf_reader,
    parse_name_list,
    reader_list,
)

VARIABLES = (
    "PDF_READER",
    "PDF_READERS",
    "OCR_ENGINES",
    "OCR_ENGINE_PRIMARY",
    "OCR_ENGINE_FALLBACK",
)


@pytest.fixture(autouse=True)
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    # conftest sets PDF_READER=pypdf for every test; these tests start from nothing set.
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    root = tmp_path / "omrs-config"
    root.mkdir(mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    return root


def write_config(root: Path, text: str) -> None:
    (root / "omrs.jsonc").write_text(text, encoding="utf-8")


def build(tmp_path: Path, dotenv: str = "") -> Settings:
    env_file = tmp_path / "test.env"
    env_file.write_text(dotenv, encoding="utf-8")
    return Settings(_env_file=env_file)


def source_of(settings: Settings, path: str) -> str:
    return settings.setting_sources.get(path, "default")


# ── 1.1 Where the list keys come from ────────────────────────────────────


def test_defaults_are_the_expansion_of_the_default_single_keys(tmp_path: Path) -> None:
    settings = build(tmp_path)
    assert settings.pdf_readers == PDF_READERS_DEFAULT == ("pdf_inspector", "liteparse", "pypdf")
    assert settings.ocr_engines == OCR_ENGINES_DEFAULT == ("dots-mocr", "paddleocr-vl")
    assert expand_pdf_reader(settings.pdf_reader) == settings.pdf_readers
    assert expand_ocr_engines(settings.ocr_engine_primary, settings.ocr_engine_fallback) == (
        settings.ocr_engines
    )
    assert source_of(settings, "pdf_readers") == source_of(settings, "ocr_engines") == "default"


def test_environment_lists_are_comma_separated_and_trimmed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PDF_READERS", " pypdf , liteparse ,, ")
    monkeypatch.setenv("OCR_ENGINES", "dots-mocr,paddleocr-vl ,third")
    settings = build(tmp_path)
    assert settings.pdf_readers == ("pypdf", "liteparse")
    assert settings.ocr_engines == ("dots-mocr", "paddleocr-vl", "third")


def test_dotenv_lists_are_read_and_report_dotenv(tmp_path: Path) -> None:
    settings = build(tmp_path, "PDF_READERS=liteparse,pypdf\nOCR_ENGINES=paddleocr-vl\n")
    assert settings.pdf_readers == ("liteparse", "pypdf")
    assert settings.ocr_engines == ("paddleocr-vl",)
    assert source_of(settings, "pdf_readers") == source_of(settings, "ocr_engines") == "dotenv"


def test_file_arrays_are_read_and_report_config_file(folder: Path, tmp_path: Path) -> None:
    write_config(
        folder, '{ "pdf_readers": ["pypdfium2", "pypdf"], "ocr_engines": ["a", "b", "c"] }'
    )
    settings = build(tmp_path)
    assert settings.pdf_readers == ("pypdfium2", "pypdf")
    assert settings.ocr_engines == ("a", "b", "c")
    assert source_of(settings, "pdf_readers") == source_of(settings, "ocr_engines") == "config-file"
    assert {"pdf_readers", "ocr_engines"} <= settings.config_file_fields


@pytest.mark.parametrize("key", ["pdf_readers", "ocr_engines"])
@pytest.mark.parametrize("wrong", ['"pypdf"', "7", '{"a": 1}', "[3]", "[]", "true"])
def test_a_wrong_file_type_is_ignored_and_listed(
    folder: Path, tmp_path: Path, key: str, wrong: str
) -> None:
    write_config(folder, f'{{ "{key}": {wrong} }}')
    parsed = read_settings_file()
    assert key not in parsed.values
    assert [(p.kind, p.key) for p in parsed.problems] == [(KIND_INVALID, key)]
    assert wrong not in parsed.problems[0].message
    assert getattr(build(tmp_path), key) == Settings.model_fields[key].default


def test_the_environment_locks_a_list_field(
    folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(folder, '{ "pdf_readers": ["pypdf"] }')
    monkeypatch.setenv("PDF_READERS", "liteparse")
    settings = build(tmp_path)
    assert settings.pdf_readers == ("liteparse",)
    assert source_of(settings, "pdf_readers") == "env"
    assert "pdf_readers" not in settings.config_file_fields


def test_a_blank_environment_list_is_not_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PDF_READERS", "  ")
    settings = build(tmp_path)
    assert settings.pdf_readers == PDF_READERS_DEFAULT
    assert source_of(settings, "pdf_readers") == "default"


def test_the_list_fields_parse_text_in_one_place() -> None:
    """The comma form lives on the field type, so removing it breaks the environment form."""
    assert parse_name_list("a, b") == ("a", "b")
    assert parse_name_list([" a ", "b", ""]) == ("a", "b")
    field = ReadingListMixin.model_fields["pdf_readers"]
    assert any(type(m).__name__ == "BeforeValidator" for m in field.metadata)


# ── 1.2 Old single-value keys ────────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("pdf_inspector", ("pdf_inspector", "liteparse", "pypdf")),
        ("liteparse", ("liteparse",)),
        ("pypdfium2", ("pypdfium2",)),
        ("pypdf", ("pypdf",)),
        ("auto", AUTO_READERS),
        ("pdfminer", AUTO_READERS),  # an unknown name reads as auto, as Settings does
    ],
)
def test_a_single_reader_expands(name: str, expected: tuple[str, ...]) -> None:
    assert expand_pdf_reader(name) == expected


def test_auto_keeps_the_start_up_probe_order() -> None:
    """``capabilities.resolve_pdf_reader`` probes liteparse, then pypdfium2, then pypdf."""
    assert AUTO_READERS == ("liteparse", "pypdfium2", "pypdf")


@pytest.mark.parametrize(
    ("primary", "fallback", "expected"),
    [
        ("dots-mocr", "paddleocr-vl", ("dots-mocr", "paddleocr-vl")),
        ("dots-mocr", "", ("dots-mocr",)),
        ("dots-mocr", "  ", ("dots-mocr",)),
        ("dots-mocr", "dots-mocr", ("dots-mocr", "dots-mocr")),  # today's meaning, same identity
    ],
)
def test_old_engine_keys_build_the_list(
    primary: str, fallback: str, expected: tuple[str, ...]
) -> None:
    assert expand_ocr_engines(primary, fallback) == expected


@pytest.mark.parametrize(
    ("reader", "expected"),
    [("pdf_inspector", PDF_READERS_DEFAULT), ("liteparse", ("liteparse",)), ("pypdf", ("pypdf",))],
)
def test_an_old_reader_key_sets_the_list_from_every_source(
    folder: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reader: str,
    expected: tuple[str, ...],
) -> None:
    monkeypatch.setenv("PDF_READER", reader)
    settings = build(tmp_path)
    assert settings.pdf_readers == expected
    assert settings.pdf_reader == reader
    assert source_of(settings, "pdf_readers") == "env"
    monkeypatch.delenv("PDF_READER")
    write_config(folder, f'{{ "pdf_reader": "{reader}" }}')
    assert build(tmp_path).pdf_readers == expected
    assert source_of(build(tmp_path), "pdf_readers") == "config-file"


def test_old_engine_keys_set_the_list_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCR_ENGINE_PRIMARY", "alpha")
    monkeypatch.setenv("OCR_ENGINE_FALLBACK", "")
    settings = build(tmp_path)
    assert settings.ocr_engines == ("alpha",)
    assert (settings.ocr_engine_primary, settings.ocr_engine_fallback) == ("alpha", "")


def test_an_empty_old_fallback_in_the_file_gives_one_engine(folder: Path, tmp_path: Path) -> None:
    write_config(folder, '{ "ocr_engine_fallback": "" }')
    assert build(tmp_path).ocr_engines == ("dots-mocr", "paddleocr-vl")  # blank file value: not set
    write_config(folder, '{ "ocr_engine_primary": "alpha" }')
    assert build(tmp_path).ocr_engines == ("alpha", "paddleocr-vl")


def test_within_one_file_the_list_key_wins_and_the_old_key_is_listed(
    folder: Path, tmp_path: Path
) -> None:
    write_config(
        folder,
        '{ "pdf_reader": "liteparse", "pdf_readers": ["pypdf"],'
        ' "ocr_engine_primary": "x", "ocr_engine_fallback": "y", "ocr_engines": ["z"] }',
    )
    parsed = read_settings_file()
    assert sorted((p.kind, p.key, p.replacement) for p in parsed.problems) == [
        (KIND_RETIRED, "ocr_engine_fallback", "ocr_engines"),
        (KIND_RETIRED, "ocr_engine_primary", "ocr_engines"),
        (KIND_RETIRED, "pdf_reader", "pdf_readers"),
    ]
    assert not set(OLD_READING_KEYS["ocr_engines"] + OLD_READING_KEYS["pdf_readers"]) & set(
        parsed.values
    )
    settings = build(tmp_path)
    assert settings.pdf_readers == ("pypdf",) and settings.ocr_engines == ("z",)
    assert settings.pdf_reader == "pypdf"  # the old key reads back from the winning list
    assert (settings.ocr_engine_primary, settings.ocr_engine_fallback) == ("z", "")


def test_within_one_environment_the_list_key_wins_and_the_old_key_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("PDF_READER", "liteparse")
    monkeypatch.setenv("PDF_READERS", "pypdf")
    with caplog.at_level(logging.WARNING, logger="omrs.config.reading_lists"):
        settings = build(tmp_path)
    assert settings.pdf_readers == ("pypdf",)
    assert any("Ignoring pdf_reader in the env source" in r.getMessage() for r in caplog.records)


def test_the_higher_source_wins_whichever_form_it_uses(
    folder: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_config(folder, '{ "pdf_readers": ["pypdf"], "ocr_engines": ["a", "b"] }')
    monkeypatch.setenv("PDF_READER", "liteparse")  # env beats the file's list
    monkeypatch.setenv("OCR_ENGINE_PRIMARY", "solo")
    monkeypatch.setenv("OCR_ENGINE_FALLBACK", "")
    settings = build(tmp_path)
    assert settings.pdf_readers == ("liteparse",)
    assert settings.ocr_engines == ("solo",)
    assert source_of(settings, "pdf_readers") == source_of(settings, "ocr_engines") == "env"
    monkeypatch.delenv("PDF_READER")
    write_config(folder, '{ "pdf_reader": "liteparse" }')  # the file's old key, env list above it
    monkeypatch.setenv("PDF_READERS", "pypdfium2")
    assert build(tmp_path).pdf_readers == ("pypdfium2",)


def test_an_explicit_option_counts_as_the_highest_source() -> None:
    assert Settings(_env_file=None, pdf_reader="liteparse").pdf_readers == ("liteparse",)
    assert Settings(_env_file=None, pdf_readers=["pypdf"]).pdf_readers == ("pypdf",)


def test_a_list_shows_back_through_the_old_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PDF_READERS", "pypdfium2,pypdf")
    monkeypatch.setenv("OCR_ENGINES", "one,two,three")
    settings = build(tmp_path)
    assert settings.pdf_reader == "pypdfium2"
    assert (settings.ocr_engine_primary, settings.ocr_engine_fallback) == ("one", "two")


@pytest.mark.parametrize("name", ["PDF_READER", "OCR_ENGINE_PRIMARY", "OCR_ENGINE_FALLBACK"])
def test_the_old_names_are_not_retired(name: str) -> None:
    check_legacy_env_vars({name: "anything"})  # does not raise


def test_an_old_environment_name_does_not_stop_start_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PDF_READER", "liteparse")
    check_legacy_env_vars()
    assert build(tmp_path).pdf_readers == ("liteparse",)


# ── EffectiveSettings readers ────────────────────────────────────────────


def test_reader_and_engine_lists_expand_when_the_list_is_empty() -> None:
    bare = SimpleNamespace(
        pdf_reader="pdf_inspector",
        pdf_readers=(),
        ocr_engine_primary="a",
        ocr_engine_fallback="",
        ocr_engines=(),
    )
    assert reader_list(bare) == PDF_READERS_DEFAULT
    assert engine_list(bare) == ("a",)
    given = SimpleNamespace(**{**vars(bare), "pdf_readers": ("pypdf",), "ocr_engines": ("x", "y")})
    assert reader_list(given) == ("pypdf",) and engine_list(given) == ("x", "y")


def test_compose_threads_the_lists_into_effective_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs.compose_settings import settings_to_effective

    monkeypatch.setenv("PDF_READERS", "pypdf,liteparse")
    monkeypatch.setenv("OCR_ENGINES", "a,b,c")
    effective = settings_to_effective(build(tmp_path))
    assert effective.pdf_readers == ("pypdf", "liteparse")
    assert effective.ocr_engines == ("a", "b", "c")
    assert effective.ocr_engine_primary == "a" and effective.ocr_engine_fallback == "b"


def test_effective_settings_keep_the_single_fields_and_default_the_lists_empty() -> None:
    from omrs.core.settings import EffectiveSettings

    bare = EffectiveSettings(pdf_reader="pypdf")
    assert (bare.pdf_readers, bare.ocr_engines) == ((), ())
    assert reader_list(bare) == ("pypdf",) and engine_list(bare) == OCR_ENGINES_DEFAULT


# ── 1.3 Shapes, writer and template ──────────────────────────────────────


def test_the_list_keys_have_a_list_shape_and_are_writable_by_the_page() -> None:
    assert setting_shape("pdf_readers").kind == KIND_LIST
    assert setting_shape("pdf_readers").choices == (
        "liteparse",
        "pdf_inspector",
        "pypdfium2",
        "pypdf",
    )
    assert setting_shape("ocr_engines").kind == KIND_LIST
    assert not is_scalar("ocr_engines")
    assert {"pdf_readers", "ocr_engines"} <= set(ALLOWED_KEYS)
    assert not set(ALLOWED_KEYS) & {"pdf_reader", "ocr_engine_primary", "ocr_engine_fallback"}


def test_a_list_save_writes_the_array_and_removes_the_old_keys(folder: Path) -> None:
    write_config(folder, '// keep\n{\n  "pdf_reader": "pypdf", // old\n  "web_port": 9100\n}\n')
    write_settings({"pdf_readers": ["liteparse", "pypdf"]}, revision=None, directory=folder)
    text = (folder / "omrs.jsonc").read_text(encoding="utf-8")
    data = parse_jsonc(text)
    assert data["pdf_readers"] == ["liteparse", "pypdf"] and "pdf_reader" not in data
    assert text.startswith("// keep\n") and data["web_port"] == 9100
    assert Settings(_env_file=None).pdf_readers == ("liteparse", "pypdf")


def test_the_starter_file_shows_the_list_keys_and_not_the_old_ones() -> None:
    from omrs.transports.cli.config_template import build_template

    text = build_template()
    assert '// "pdf_readers": ["pdf_inspector", "liteparse", "pypdf"],' in text
    assert '// "ocr_engines": ["dots-mocr", "paddleocr-vl"],' in text
    for old in ("pdf_reader", "ocr_engine_primary", "ocr_engine_fallback"):
        assert f'"{old}"' not in text
    assert TEMPLATE_SKIPPED_FIELDS == {k for olds in OLD_READING_KEYS.values() for k in olds}


def test_the_old_fields_are_still_settings_fields() -> None:
    """They stay readable in every source, so the model keeps them."""
    assert TEMPLATE_SKIPPED_FIELDS <= set(Settings.model_fields)
