"""Write rules of the document-reading keys (document-reading-settings, tasks 1.1 to 1.4).

The rules run only when the Settings page writes ``omrs.jsonc``. Startup
reading stays as it was: an unknown ``pdf_reader`` still warns and falls back
to ``auto``. Every test points ``OMRS_CONFIG_DIR`` at a temporary folder.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from omrs.config import Settings
from omrs.config.rules import (
    DOCUMENT_READING_KEYS,
    ENGINE_NAME_PATTERN,
    MAX_ENGINE_NAME_CHARS,
    PDF_READER_NAMES,
    document_reading_problem,
)
from omrs.config.settings_file_write import SettingsFileRefused, write_settings
from omrs.config.user_config import parse_jsonc

ENGINE_RULE = (
    "The engine name must start with a letter or digit, hold only letters, digits, dots, "
    "hyphens and underscores, and be at most 64 characters."
)
BOOL_RULE = "The value must be true or false."
BLANK_RULE = "The value must not be blank. Send null to use the default."
READER_RULE = "The value must be one of: auto, liteparse, pdf_inspector, pypdfium2, pypdf."
READER_LIST_RULE = "The value must be one of: liteparse, pdf_inspector, pypdfium2, pypdf."
EMPTY_RULE = "The list must not be empty. Send null to use the default."
DUPLICATE_RULE = "The list must not name the same item twice."
LIST_RULE = "The value must be a list of names."
UNIT_RULE = "The value must be one of: page."
REMOVED_KEYS = (
    "ocr_fallback_min_confidence",
    "ocr_fallback_page_fraction",
    "ocr_maths_page_fraction",
)
# page-routing-panel adds the skip-blank switch.
BOOLEANS = ("ocr_fallback_enabled", "ocr_skip_blank_pages", "ocr_maths_routing_enabled")
ENGINES = ("ocr_engine_primary", "ocr_engine_fallback")


# ── 1.1 Reader names ─────────────────────────────────────────────────────


def test_reader_names_match_the_pdf_registry() -> None:
    from omrs.integrations.pdf import registry

    assert PDF_READER_NAMES[0] == "auto"
    assert set(PDF_READER_NAMES) - {"auto"} == set(registry.available())


def test_the_settings_validator_reads_the_shared_reader_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in PDF_READER_NAMES:
        monkeypatch.setenv("PDF_READER", name)
        assert Settings().pdf_reader == name


# ── 1.2 The write rule ───────────────────────────────────────────────────


def test_the_key_order_is_the_contract_order() -> None:
    assert DOCUMENT_READING_KEYS == (
        "pdf_readers",
        "ocr_fallback_enabled",
        "ocr_routing_unit",
        "ocr_engines",
        # page-routing-panel: the blank rule key comes first, in rule order.
        "ocr_skip_blank_pages",
        "ocr_maths_routing_enabled",
        "ocr_non_latin_routing",
        "document_router",
        "ocr_local_backends",
        "ocr_local_cuts",
    )


def test_engine_pattern_matches_the_route_resolver() -> None:
    from omrs.integrations.ocr_worker import routes

    assert ENGINE_NAME_PATTERN == routes._ENGINE_NAME_RE.pattern
    assert MAX_ENGINE_NAME_CHARS == 64


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("pdf_reader", "liteparse"),
        ("pdf_reader", "auto"),
        ("ocr_routing_unit", "page"),
        ("ocr_engine_primary", "dots-mocr"),
        ("ocr_engine_fallback", "my_engine.v2"),
        ("ocr_engine_fallback", "e" * 64),
        ("ocr_fallback_enabled", False),
        ("ocr_maths_routing_enabled", True),
        ("ocr_engine_primary", None),
        ("pdf_reader", None),
    ],
)
def test_valid_values_pass(key: str, value: Any) -> None:
    assert document_reading_problem(key, value) is None


@pytest.mark.parametrize(
    ("key", "value", "rule"),
    [
        ("pdf_reader", "pdfminer", READER_RULE),
        ("pdf_reader", 3, READER_RULE),
        ("pdf_reader", "", BLANK_RULE),
        ("ocr_routing_unit", "document", UNIT_RULE),
        ("ocr_routing_unit", "chapter", UNIT_RULE),
        ("ocr_routing_unit", True, UNIT_RULE),
        ("ocr_routing_unit", "  ", BLANK_RULE),
        ("ocr_engine_primary", "../x", ENGINE_RULE),
        ("ocr_engine_primary", ".hidden", ENGINE_RULE),
        ("ocr_engine_primary", "a/b", ENGINE_RULE),
        ("ocr_engine_primary", "abc\n", ENGINE_RULE),
        ("ocr_engine_primary", "e" * 65, ENGINE_RULE),
        ("ocr_engine_primary", 7, ENGINE_RULE),
        ("ocr_engine_fallback", "", BLANK_RULE),
        ("ocr_engine_fallback", "   ", BLANK_RULE),
        ("ocr_fallback_enabled", "true", BOOL_RULE),
        ("ocr_fallback_enabled", 1, BOOL_RULE),
        ("ocr_maths_routing_enabled", "", BOOL_RULE),
    ],
)
def test_each_rule_has_its_exact_message(key: str, value: Any, rule: str) -> None:
    assert document_reading_problem(key, value) == rule


def test_a_rule_never_holds_the_value() -> None:
    for key in DOCUMENT_READING_KEYS:
        message = document_reading_problem(key, "zz-secret-zz/..") or ""
        assert "zz-secret-zz" not in message


def test_a_key_outside_the_five_passes_unchecked() -> None:
    assert document_reading_problem("ollama_base_url", "") is None


@pytest.mark.parametrize("key", REMOVED_KEYS)
def test_a_removed_fraction_key_is_not_a_reading_key(key: str) -> None:
    """The three deleted gate settings left the contract, so the rule no longer checks them."""
    assert key not in DOCUMENT_READING_KEYS
    assert document_reading_problem(key, 7) is None


# ── 1.3 The writer ───────────────────────────────────────────────────────


@pytest.fixture
def folder(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "cfg" / "omrs"
    root.mkdir(parents=True, mode=0o700)
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(root))
    (root / "omrs.jsonc").write_text(
        '// mine\n{\n  "ocr_engine_fallback": "my-engine", // keep this\n  "web_port": 9100\n}\n',
        encoding="utf-8",
    )
    return root


def text(folder: Path) -> str:
    return (folder / "omrs.jsonc").read_text(encoding="utf-8")


def test_a_valid_reader_is_written_and_every_other_byte_stays(folder: Path) -> None:
    before = text(folder)
    write_settings({"pdf_readers": ["liteparse"]}, revision=None, directory=folder)
    after = text(folder)
    assert parse_jsonc(after)["pdf_readers"] == ["liteparse"]
    assert "// keep this" in after and after.startswith("// mine\n")
    assert '"ocr_engine_fallback": "my-engine", // keep this' in after
    assert len(after) > len(before)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"pdf_readers": ["pdfminer"]}, f"pdf_readers: {READER_LIST_RULE}"),
        ({"pdf_readers": ["auto"]}, f"pdf_readers: {READER_LIST_RULE}"),
        ({"pdf_readers": []}, f"pdf_readers: {EMPTY_RULE}"),
        ({"pdf_readers": ["pypdf", "pypdf"]}, f"pdf_readers: {DUPLICATE_RULE}"),
        ({"pdf_readers": "pypdf"}, f"pdf_readers: {LIST_RULE}"),
        ({"ocr_engines": ["../other"]}, f"ocr_engines: {ENGINE_RULE}"),
        ({"ocr_engines": ["dots-mocr", ""]}, f"ocr_engines: {BLANK_RULE}"),
        ({"ocr_engines": ["a", "a"]}, f"ocr_engines: {DUPLICATE_RULE}"),
        ({"ocr_engines": [3]}, f"ocr_engines: {LIST_RULE}"),
        ({"ocr_fallback_enabled": "true"}, f"ocr_fallback_enabled: {BOOL_RULE}"),
        ({"ocr_routing_unit": "document"}, f"ocr_routing_unit: {UNIT_RULE}"),
        (
            {"ocr_routing_unit": "page", "ocr_fallback_enabled": 1},
            f"ocr_fallback_enabled: {BOOL_RULE}",
        ),
    ],
)
def test_a_refused_value_writes_nothing(
    folder: Path, changes: dict[str, Any], message: str
) -> None:
    before = text(folder)
    with pytest.raises(SettingsFileRefused) as caught:
        write_settings(changes, revision=None, directory=folder)
    assert str(caught.value) == message
    assert text(folder) == before


def test_null_removes_the_key_and_keeps_the_comments(folder: Path) -> None:
    write_settings({"ocr_engines": None}, revision=None, directory=folder)
    after = text(folder)
    assert "ocr_engines" not in parse_jsonc(after)
    assert "ocr_engine_fallback" not in parse_jsonc(after)  # the old key goes with the list
    assert after.startswith("// mine\n") and parse_jsonc(after)["web_port"] == 9100


@pytest.mark.parametrize("key", REMOVED_KEYS)
def test_a_removed_fraction_key_is_refused_and_writes_nothing(folder: Path, key: str) -> None:
    before = text(folder)
    with pytest.raises(SettingsFileRefused) as caught:
        write_settings({key: 0.2}, revision=None, directory=folder)
    assert str(caught.value) == f"{key} is not a setting that can be changed here."
    assert text(folder) == before


def test_booleans_and_the_unit_are_written_as_json(folder: Path) -> None:
    write_settings(
        {
            "ocr_maths_routing_enabled": False,
            "ocr_routing_unit": "page",
        },
        revision=None,
        directory=folder,
    )
    data = parse_jsonc(text(folder))
    assert data["ocr_maths_routing_enabled"] is False
    assert data["ocr_routing_unit"] == "page"


# ── 1.4 Startup behaviour does not change ───────────────────────────────


def test_an_unknown_reader_in_the_file_still_falls_back_to_auto_at_startup(
    folder: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("PDF_READER", raising=False)
    (folder / "omrs.jsonc").write_text('{ "pdf_reader": "pdfminer" }', encoding="utf-8")
    empty = folder / "none.env"
    empty.write_text("", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="omrs.config"):
        settings = Settings(_env_file=empty)
    assert settings.pdf_reader == "auto"
    assert any("Unknown PDF_READER" in record.getMessage() for record in caplog.records)


# ── Ordered lists (ordered-reader-and-ocr-lists, tasks 1.1 to 1.3) ───────


def test_a_list_save_removes_the_old_keys_in_the_same_write(folder: Path) -> None:
    (folder / "omrs.jsonc").write_text(
        '// mine\n{\n  "ocr_engine_primary": "dots-mocr", // old\n'
        '  "ocr_engine_fallback": "paddleocr-vl",\n  "pdf_reader": "pypdf",\n'
        '  "web_port": 9100\n}\n',
        encoding="utf-8",
    )
    write_settings({"ocr_engines": ["dots-mocr", "paddleocr-vl"]}, revision=None, directory=folder)
    data = parse_jsonc(text(folder))
    assert data["ocr_engines"] == ["dots-mocr", "paddleocr-vl"]
    assert "ocr_engine_primary" not in data and "ocr_engine_fallback" not in data
    assert data["pdf_reader"] == "pypdf"  # the other list's old key stays until that list is saved
    assert text(folder).startswith("// mine\n") and data["web_port"] == 9100


@pytest.mark.parametrize(
    ("key", "list_key"),
    [
        ("pdf_reader", "pdf_readers"),
        ("ocr_engine_primary", "ocr_engines"),
        ("ocr_engine_fallback", "ocr_engines"),
    ],
)
@pytest.mark.parametrize("value", ["pypdf", None])
def test_a_write_of_an_old_key_is_refused_naming_the_list_key(
    folder: Path, key: str, list_key: str, value: Any
) -> None:
    before = text(folder)
    with pytest.raises(SettingsFileRefused) as caught:
        write_settings({key: value}, revision=None, directory=folder)
    assert list_key in str(caught.value) and str(caught.value).startswith(f"{key}: ")
    assert text(folder) == before


def test_an_old_key_is_still_checked_for_a_studio_step() -> None:
    """A Read step accepts the old names, so the value rule still judges them."""
    assert document_reading_problem("pdf_reader", "pdfminer") == READER_RULE
    assert document_reading_problem("ocr_engine_fallback", "../x") == ENGINE_RULE
