"""Single source of the reading key lists (change local-ocr-backends, task 6.5, design D15).

Two kinds of test live here:

1. Derived lists follow the descriptors. Each test loads a private copy of the
   module that owns a list while the page rule table holds one more rule, and
   checks that the new rule's setting joins the list. The copy never enters
   the import system for long, so other tests see the real modules.
2. Kept literals are pinned to the descriptors. The rule metadata keys and the
   identity builders need facts that a descriptor does not hold, so they stay
   literal. These tests fail when a descriptor and the literal disagree.

The literal pins in ``test_reading_parts_list_pins.py`` hold today's values.
"""

from __future__ import annotations

import importlib.util
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from omrs.config import rules
from omrs.core import reading_parts
from omrs.core.ingestion import embed_exclusions, graph_adapters_catalogue, source_state
from omrs.core.ingestion.ocr_identity import (
    maths_routing_payload,
    non_latin_routing_payload,
    ocr_routing_payload,
)
from omrs.core.ingestion.reader_identity import pdf_parser_payload
from omrs.core.pipelines import levers

_FAKE_KEY = "ocr_fake_rule_enabled"
_FAKE_RULE = reading_parts.PageRuleDescriptor(
    name="fake_rule",
    import_path="fake_rule_module:RULE",
    label="Fake rule",
    help_key="page_rule.fake_rule",
    settings=(reading_parts.SettingField(name=_FAKE_KEY, env=_FAKE_KEY.upper(), default=False),),
    order=99,
)


def _copy_with_fake_rule(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Return a fresh copy of *module*, run while the page rule table holds a fake rule.

    The copy sits in ``sys.modules`` under its own name only while this test
    runs (pydantic and dataclasses look the module up there). The real module
    is never reloaded.
    """
    monkeypatch.setattr(reading_parts, "PAGE_RULES", (*reading_parts.PAGE_RULES, _FAKE_RULE))
    name = f"{module.__name__}_single_source_copy"
    spec = importlib.util.spec_from_file_location(name, module.__file__)
    assert spec is not None and spec.loader is not None
    copy = importlib.util.module_from_spec(spec)
    copy.__package__ = module.__package__
    monkeypatch.setitem(sys.modules, name, copy)
    spec.loader.exec_module(copy)
    return copy


def _without_fake(keys: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(key for key in keys if key != _FAKE_KEY)


# ── 1. Derived lists follow the descriptors ──────────────────────────────


def test_document_reading_keys_take_rule_settings_from_the_descriptors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    copy = _copy_with_fake_rule(rules, monkeypatch)

    keys = copy.DOCUMENT_READING_KEYS
    assert keys[keys.index(_FAKE_KEY) - 1] == "ocr_non_latin_routing"
    assert _without_fake(copy.DOCUMENT_READING_KEYS) == rules.DOCUMENT_READING_KEYS


def test_read_ocr_keys_take_rule_settings_from_the_descriptors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    copy = _copy_with_fake_rule(graph_adapters_catalogue, monkeypatch)

    assert _FAKE_KEY in copy.READ_OCR_KEYS
    assert _without_fake(copy.READ_OCR_KEYS) == graph_adapters_catalogue.READ_OCR_KEYS


def test_read_step_ocr_keys_take_rule_settings_from_the_descriptors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    copy = _copy_with_fake_rule(levers, monkeypatch)

    assert _FAKE_KEY in copy._READ_STEP_OCR_KEYS
    assert _without_fake(copy._READ_STEP_OCR_KEYS) == levers._READ_STEP_OCR_KEYS
    assert _FAKE_KEY in copy._HOST_OWNED_EXACT


def test_every_rule_setting_is_in_each_list_in_rule_order() -> None:
    """The rule settings sit in each list in descriptor order, the derivation's contract."""
    expected = tuple(field.name for rule in reading_parts.PAGE_RULES for field in rule.settings)
    for keys in (
        rules.DOCUMENT_READING_KEYS,
        graph_adapters_catalogue.READ_OCR_KEYS,
        levers._READ_STEP_OCR_KEYS,
    ):
        assert tuple(key for key in keys if key in expected) == expected


# ── 2. Kept literals pinned to the descriptors ───────────────────────────

#: The page-count metadata key each page rule stamps. A descriptor has no
#: metadata-key fact, so ``embed_exclusions`` keeps its literal list and this
#: map names the key per rule. A new rule fails the first test until it is added.
_RULE_METADATA_KEYS = {
    "blank": "ocr_pages_blank",
    "maths": "pages_maths_font",
    "non_latin": "pages_non_latin",
}


def test_every_page_rule_names_its_metadata_key() -> None:
    assert sorted(_RULE_METADATA_KEYS) == sorted(reading_parts.names(reading_parts.PAGE_RULES))


def test_rule_metadata_keys_never_reach_the_embedder() -> None:
    excluded = embed_exclusions.EXCLUDED_EMBED_METADATA_KEYS
    assert [key for key in _RULE_METADATA_KEYS.values() if key not in excluded] == []


def test_only_rules_with_a_conditional_identity_block_leave_the_identity_list() -> None:
    """A rule whose identity block is not always present has its key unlisted."""
    conditional = {
        _RULE_METADATA_KEYS[rule.name]
        for rule in reading_parts.PAGE_RULES
        if rule.identity is not None and rule.identity.presence != "always"
    }
    assert embed_exclusions.IDENTITY_UNLISTED_KEYS == conditional


def _identity_parts() -> list[reading_parts.PartDescriptor]:
    tables = (reading_parts.LOCAL_OCR_BACKENDS, reading_parts.PAGE_RULES)
    return [part for table in tables for part in table if part.identity is not None]


def _changed(field: reading_parts.SettingField) -> Any:
    """Return a value of *field* that differs from its default."""
    if isinstance(field.default, bool):
        return not field.default
    if field.accepted is not None:
        return next(value for value in field.accepted if value != field.default)
    if field.default is None:
        return 0.5
    raise AssertionError(f"no changed value rule for {field.name}; add one here")


def _on(part: reading_parts.PartDescriptor) -> dict[str, Any]:
    """Return the overrides that turn *part* on (a non-default value of each choice)."""
    return {field.name: _changed(field) for field in part.settings if field.accepted}


def _payload(settings: Any, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Return the identity payload of a PDF source before it is hashed."""
    seen: list[Any] = []

    def dumps(value: Any, **kwargs: Any) -> str:
        seen.append(value)
        return source_state_json.dumps(value, **kwargs)

    source_state_json = source_state.json
    monkeypatch.setattr(source_state, "json", SimpleNamespace(dumps=dumps))
    source_state.build_index_identity(
        settings,
        content_type="application/pdf",
        chunk_size=512,
        chunk_overlap=100,
        pdf_reader_revision=2,
        embed_model=SimpleNamespace(model_name="pinned-embedder"),
    )
    monkeypatch.setattr(source_state, "json", source_state_json)
    return seen[0]


_BUILDERS = {
    "ocr_routing": ocr_routing_payload,
    "maths_routing": maths_routing_payload,
    "parser": pdf_parser_payload,
}


@pytest.mark.parametrize("part", _identity_parts(), ids=lambda part: part.name)
def test_each_identity_builder_writes_the_keys_its_descriptor_names(
    part: reading_parts.PartDescriptor, effective_settings: Any
) -> None:
    spec = part.identity
    assert spec is not None
    settings = effective_settings(pdf_reader="pdf_inspector", **_on(part))

    written = _BUILDERS[spec.block](settings)

    assert [key for key in spec.keys if key not in written] == []


@pytest.mark.parametrize("part", _identity_parts(), ids=lambda part: part.name)
def test_each_identity_block_reaches_the_source_identity(
    part: reading_parts.PartDescriptor, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = part.identity
    assert spec is not None
    settings = effective_settings(pdf_reader="pdf_inspector", **_on(part))

    payload = _payload(settings, monkeypatch)

    assert [key for key in spec.keys if key not in payload[spec.block]] == []


def test_a_block_present_only_when_on_adds_nothing_when_off(effective_settings: Any) -> None:
    """``pdf_when_on`` blocks add no key at their default, so default digests hold."""
    settings = effective_settings(pdf_reader="pdf_inspector")
    for part in _identity_parts():
        assert part.identity is not None
        if part.identity.presence == "pdf_when_on":
            assert non_latin_routing_payload(settings) == {}
            assert [key for key in part.identity.keys if key in pdf_parser_payload(settings)] == []


_IDENTITY_FIELDS = [
    (part.name, field)
    for part in _identity_parts()
    for field in part.settings
    if field.enters_identity
]


@pytest.mark.parametrize(("part", "field"), _IDENTITY_FIELDS, ids=lambda item: str(item))
def test_each_identity_setting_moves_the_source_digest(
    part: str, field: reading_parts.SettingField, effective_settings: Any
) -> None:
    def digest(**overrides: Any) -> str:
        return source_state.build_index_identity(
            effective_settings(pdf_reader="pdf_inspector", **overrides),
            content_type="application/pdf",
            chunk_size=512,
            chunk_overlap=100,
            pdf_reader_revision=2,
            embed_model=SimpleNamespace(model_name="pinned-embedder"),
        )

    assert digest(**{field.name: _changed(field)}) != digest(), f"{part}.{field.name}"
