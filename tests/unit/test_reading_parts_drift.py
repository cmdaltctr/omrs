"""Drift tests for the copies of reading-part lists that cannot import Python.

Change local-ocr-backends, task 6.6, design D15. The HTTP contract enums and
the web key lists are hand-typed. Each test reads the file as text and fails,
naming the key, when a copy differs from the descriptors (through the
derived lists in ``config/rules.py``). Generating the copies is out of scope.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from omrs.config import rules
from omrs.core import reading_parts

_ROOT = Path(__file__).resolve().parents[2]
_CONTRACT = _ROOT / "src" / "omrs" / "transports" / "api" / "openapi.yaml"
_WEB_KEYS = _ROOT / "web" / "src" / "api" / "settingsDocumentReading.ts"
_WEB_WORDS = _ROOT / "web" / "src" / "settings" / "documentReadingWords.ts"
_WEB_PANEL = _ROOT / "web" / "src" / "pageRouting" / "pageRoutingWords.ts"

#: The old single-value keys. They stay valid in requests, so the request
#: copies hold them beside the list keys.
_OLD_KEYS = tuple(old for olds in rules.OLD_READING_KEYS.values() for old in olds)


def _differs(copy: list[str], expected: list[str], where: str) -> str:
    """Return a message naming every missing and extra key, or ``""`` when they agree."""
    missing = [key for key in expected if key not in copy]
    extra = [key for key in copy if key not in expected]
    if missing or extra:
        return f"{where}: missing {missing}, extra {extra}"
    return "" if copy == expected else f"{where}: order {copy} != {expected}"


@cache
def _contract() -> dict[str, Any]:
    return yaml.safe_load(_CONTRACT.read_text(encoding="utf-8"))


def _schema(name: str) -> dict[str, Any]:
    return _contract()["components"]["schemas"][name]


def _ts_array(path: Path, name: str) -> list[str]:
    """Return the string items of ``export const <name> = [ ... ]`` in *path*."""
    text = path.read_text(encoding="utf-8")
    found = re.search(rf"export const {name}\b[^=]*=\s*\[(?P<body>.*?)\]", text, re.S)
    assert found is not None, f"{name} not found in {path.name}"
    return re.findall(r'"([^"]+)"', found["body"])


def _ts_object_keys(path: Path, name: str) -> list[str]:
    """Return the top-level keys of ``export const <name> ... = { ... };`` in *path*."""
    text = path.read_text(encoding="utf-8")
    found = re.search(rf"export const {name}\b.*?=\s*\{{\n(?P<body>.*?)\n\}};", text, re.S)
    assert found is not None, f"{name} not found in {path.name}"
    return re.findall(r"^  ([a-z_]+):", found["body"], re.M)


def _with_old_keys(keys: tuple[str, ...]) -> list[str]:
    """Return *keys* with each old key after the list key that replaced it."""
    return [item for key in keys for item in (key, *rules.OLD_READING_KEYS.get(key, ()))]


# ── openapi.yaml ─────────────────────────────────────────────────────────


def test_the_contract_setting_key_enum_follows_the_descriptors() -> None:
    enum = _schema("DocumentReadingSetting")["properties"]["key"]["enum"]
    assert _differs(enum, list(rules.DOCUMENT_READING_KEYS), "DocumentReadingSetting.key") == ""


def test_the_contract_row_count_follows_the_key_list() -> None:
    settings = _schema("DocumentReadingState")["properties"]["settings"]
    count = len(rules.DOCUMENT_READING_KEYS)
    assert (settings["minItems"], settings["maxItems"]) == (count, count)


def test_the_contract_update_keys_follow_the_descriptors() -> None:
    values = _schema("DocumentReadingUpdate")["properties"]["values"]
    enum = values["propertyNames"]["enum"]
    expected = _with_old_keys(rules.DOCUMENT_READING_KEYS)
    assert _differs(enum, expected, "DocumentReadingUpdate.values") == ""
    assert values["maxProperties"] == len(expected)


def test_the_contract_reader_enum_follows_the_reader_descriptors() -> None:
    enum = _schema("ReaderOption")["properties"]["name"]["enum"]
    assert _differs(enum, list(rules.PDF_READER_NAMES), "ReaderOption.name") == ""


def test_the_contract_reader_rule_example_is_the_rule_text() -> None:
    put = _contract()["paths"]["/settings/document-reading"]["put"]
    text = " ".join(put["description"].split())
    assert f'"pdf_readers: {rules.READER_LIST_RULE}"' in text


def test_the_contract_part_kinds_follow_the_descriptor_kinds() -> None:
    enum = _schema("DiscoveredPartHealth")["properties"]["kind"]["enum"]
    kinds = [
        reading_parts.KIND_PDF_READER,
        reading_parts.KIND_LOCAL_OCR_BACKEND,
        reading_parts.KIND_PAGE_RULE,
    ]
    assert _differs(enum, kinds, "DiscoveredPartHealth.kind") == ""


# ── web/src/api/settingsDocumentReading.ts ───────────────────────────────


def test_the_web_key_list_follows_the_descriptors() -> None:
    copy = _ts_array(_WEB_KEYS, "DOCUMENT_READING_KEYS")
    expected = _with_old_keys(rules.DOCUMENT_READING_KEYS)
    assert _differs(copy, expected, "settingsDocumentReading.ts DOCUMENT_READING_KEYS") == ""


# ── web/src/settings/documentReadingWords.ts ─────────────────────────────


def test_the_web_rows_follow_the_descriptors() -> None:
    copy = _ts_object_keys(_WEB_WORDS, "READING_ROWS")
    # The cuts have no row of their own: the Local OCR backends row edits them.
    expected = [key for key in rules.DOCUMENT_READING_KEYS if key != rules.LOCAL_CUTS_KEY]
    assert _differs(copy, expected, "documentReadingWords.ts READING_ROWS") == ""


def test_the_web_script_modes_follow_the_non_latin_descriptor() -> None:
    rule = reading_parts.by_name(reading_parts.PAGE_RULES, "non_latin")
    accepted = list(rule.settings[0].accepted or ())
    copy = _ts_array(_WEB_WORDS, "SCRIPT_MODES")
    assert _differs(copy, accepted, "documentReadingWords.ts SCRIPT_MODES") == ""


def test_the_page_routing_panel_words_follow_the_descriptors() -> None:
    """Change page-routing-panel, task 5.3, design D2 and D8."""
    optional = _ts_array(_WEB_PANEL, "OPTIONAL_READERS")
    with_extra = [reader.name for reader in reading_parts.PDF_READERS if reader.extra is not None]
    assert _differs(optional, with_extra, "pageRoutingWords.ts OPTIONAL_READERS") == ""
    text = _WEB_PANEL.read_text(encoding="utf-8")
    steps = re.search(r"export const PANEL_STEPS\b.*?=\s*\[(?P<body>.*?)\n\]", text, re.S)
    assert steps is not None, "PANEL_STEPS not found in pageRoutingWords.ts"
    step_keys = re.findall(r"keys:\s*\[(?P<keys>[^\]]*)\]", steps["body"])
    rules_step = re.findall(r'"([^"]+)"', step_keys[1])
    expected = [key for key in rules.PAGE_RULE_KEYS if key != "document_router"]
    assert _differs(rules_step, expected, "pageRoutingWords.ts PANEL_STEPS step 2") == ""


def test_the_web_old_keys_are_the_python_old_keys() -> None:
    copy = [key for key in _ts_array(_WEB_KEYS, "DOCUMENT_READING_KEYS") if key in _OLD_KEYS]
    assert sorted(copy) == sorted(_OLD_KEYS)
