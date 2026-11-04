"""``reading_part_options``: options for parts without flat keys (task 5.3, design D12).

Spec reading-parts: "Parts without flat settings SHALL read their options from
one map" and "A discovered part SHALL act only when the operator names it".
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from tests.unit.test_part_discovery_support import (
    fake_parts_builder,
    rule_distribution,
    run_discovery,
)

from omrs import compose
from omrs.core.ingestion.reader_identity import pdf_parser_payload
from omrs.core.ingestion.source_state import build_index_identity
from omrs.integrations.part_registry import PartRegistry
from omrs.integrations.pdf.page_rules import registry as rule_registry
from omrs.integrations.pdf.page_rules.base import RuleContext, RuleOutcome
from omrs.integrations.pdf.page_rules.pipeline import run_rules


@pytest.fixture
def fake_parts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Yield the fake-distribution builder of ``test_part_discovery_support``."""
    yield from fake_parts_builder(tmp_path, monkeypatch)


@pytest.fixture
def fresh_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the next ``get_settings()`` build ``Settings`` again."""
    import omrs.config as config

    monkeypatch.setattr(config, "_settings", None)


def _effective(monkeypatch: pytest.MonkeyPatch, options: Any) -> Any:
    monkeypatch.setenv("READING_PART_OPTIONS", json.dumps(options))
    return compose.settings_to_effective(compose.get_settings())


# ── Reading the map ──────────────────────────────────────────────────────


def test_the_map_is_empty_by_default(fresh_settings) -> None:
    from omrs.core.settings import EffectiveSettings

    assert compose.get_settings().reading_part_options == {}
    assert EffectiveSettings().reading_part_options == {}
    assert compose.settings_to_effective(compose.get_settings()).reading_part_options == {}


def test_the_environment_holds_the_map_as_json(fake_parts, fresh_settings, monkeypatch) -> None:
    rule_distribution(fake_parts)

    effective = _effective(monkeypatch, {"stamp-check": {"enabled": True, "strictness": "high"}})

    assert effective.reading_part_options == {
        "stamp-check": {"enabled": True, "strictness": "high"}
    }


def test_the_settings_file_holds_the_map(
    fake_parts, fresh_settings, monkeypatch, tmp_path: Path
) -> None:
    rule_distribution(fake_parts)
    folder = tmp_path / "config"
    folder.mkdir()
    (folder / "omrs.jsonc").write_text(
        "{\n  // options of parts without flat keys\n"
        '  "reading_part_options": {"stamp-check": {"enabled": true}}\n}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("OMRS_CONFIG_DIR", str(folder))

    effective = compose.settings_to_effective(compose.get_settings())

    assert effective.reading_part_options == {"stamp-check": {"enabled": True}}


# ── Validation at start-up ───────────────────────────────────────────────


def test_an_unknown_option_is_refused_naming_the_part_and_the_key(
    fake_parts, fresh_settings, monkeypatch
) -> None:
    rule_distribution(fake_parts)

    with pytest.raises(ValueError) as caught:
        _effective(monkeypatch, {"stamp-check": {"colour": "red"}})

    assert "'stamp-check'" in str(caught.value)
    assert "'colour'" in str(caught.value)
    assert "red" not in str(caught.value)


def test_an_unknown_part_is_refused_naming_it(fresh_settings, monkeypatch) -> None:
    with pytest.raises(ValueError, match="'stamp-check'"):
        _effective(monkeypatch, {"stamp-check": {"enabled": True}})


@pytest.mark.parametrize(
    ("key", "value", "rule"),
    [
        ("strictness", "medium", "one of: low, high"),
        ("limit", "three", "int"),
        ("limit", True, "int"),
        ("enabled", "yes", "bool"),
    ],
)
def test_a_bad_value_is_refused_naming_the_part_and_the_key(
    fake_parts, fresh_settings, monkeypatch, key: str, value: Any, rule: str
) -> None:
    rule_distribution(fake_parts)

    with pytest.raises(ValueError) as caught:
        _effective(monkeypatch, {"stamp-check": {key: value}})

    message = str(caught.value)
    assert "'stamp-check'" in message
    assert repr(key) in message
    assert rule in message


def test_a_built_in_rule_accepts_and_ignores_enabled(fresh_settings, monkeypatch) -> None:
    effective = _effective(monkeypatch, {"maths": {"enabled": False}})

    assert effective.reading_part_options == {"maths": {"enabled": False}}


def test_a_reader_has_no_enabled_option(fresh_settings, monkeypatch) -> None:
    with pytest.raises(ValueError, match="'pypdf'.*'enabled'"):
        _effective(monkeypatch, {"pypdf": {"enabled": True}})


# ── A discovered rule runs only when enabled ─────────────────────────────


class _Rule:
    def __init__(self) -> None:
        self.runs = 0

    def run(self, ctx: RuleContext) -> RuleOutcome:
        self.runs += 1
        return RuleOutcome()


@pytest.fixture
def two_rules():
    """An empty rule registry with one built-in and one discovered fake rule."""
    saved = rule_registry.RULES.snapshot()
    rule_registry.RULES.restore(PartRegistry("page rule").snapshot())
    rules = {"own": _Rule(), "stamp-check": _Rule()}
    rule_registry.register("own", "fake.module:own", order=10)
    rule_registry.register("stamp-check", "fake.module:stamp", order=25, source="stampcheck")
    for name, rule in rules.items():
        rule_registry.RULES.cache[name] = rule
    yield rules
    rule_registry.RULES.restore(saved)


def _run(options: dict[str, Any]) -> None:
    run_rules(Path("doc.pdf"), [], {1}, SimpleNamespace(reading_part_options=options), None)


@pytest.mark.parametrize("options", [{}, {"stamp-check": {}}, {"stamp-check": {"enabled": False}}])
def test_a_discovered_rule_is_off_until_enabled(two_rules, options) -> None:
    _run(options)

    assert two_rules["stamp-check"].runs == 0
    assert two_rules["own"].runs == 1


def test_an_enabled_discovered_rule_runs(two_rules) -> None:
    _run({"stamp-check": {"enabled": True}})

    assert two_rules["stamp-check"].runs == 1


def test_a_switched_off_discovered_rule_does_not_run(two_rules) -> None:
    rule_registry.RULES.switch_off("stamp-check", "RuntimeError: earlier file")

    _run({"stamp-check": {"enabled": True}})

    assert two_rules["stamp-check"].runs == 0


def test_a_built_in_rule_ignores_enabled(two_rules) -> None:
    _run({"own": {"enabled": False}})

    assert two_rules["own"].runs == 1


def test_settings_without_the_map_run_built_in_rules_only(two_rules) -> None:
    run_rules(Path("doc.pdf"), [], {1}, None, None)

    assert (two_rules["own"].runs, two_rules["stamp-check"].runs) == (1, 0)


# ── Identity ─────────────────────────────────────────────────────────────


def _digest(settings: Any) -> str:
    return build_index_identity(
        settings,
        content_type="application/pdf",
        chunk_size=512,
        chunk_overlap=100,
        pdf_reader_revision=2,
        embed_model=SimpleNamespace(model_name="pinned-embedder"),
    )


def test_an_empty_map_adds_nothing(effective_settings) -> None:
    settings = effective_settings(pdf_reader="pdf_inspector")

    assert "reading_part_options" not in pdf_parser_payload(settings)
    assert _digest(settings) == _digest(effective_settings(pdf_reader="pdf_inspector"))


def test_a_discovered_rule_that_is_off_keeps_the_digest(fake_parts, effective_settings) -> None:
    before = _digest(effective_settings(pdf_reader="pdf_inspector"))
    rule_distribution(fake_parts)
    run_discovery()

    after = _digest(effective_settings(pdf_reader="pdf_inspector"))
    off = effective_settings(
        pdf_reader="pdf_inspector",
        reading_part_options={"stamp-check": {"strictness": "high", "enabled": False}},
    )

    assert after == before
    assert _digest(off) == before


def test_an_enabled_rule_enters_the_identity_with_its_identity_options(
    fake_parts, effective_settings
) -> None:
    rule_distribution(fake_parts)
    run_discovery()
    settings = effective_settings(
        pdf_reader="pdf_inspector",
        reading_part_options={
            "stamp-check": {"enabled": True, "strictness": "high", "note": "x", "limit": 4}
        },
    )

    payload = pdf_parser_payload(settings)

    assert payload["reading_part_options"] == {
        "stamp-check": {"enabled": True, "strictness": "high"}
    }
    assert _digest(settings) != _digest(effective_settings(pdf_reader="pdf_inspector"))


def test_built_in_options_add_nothing(effective_settings) -> None:
    settings = effective_settings(reading_part_options={"maths": {"enabled": False}})

    assert "reading_part_options" not in pdf_parser_payload(settings)
