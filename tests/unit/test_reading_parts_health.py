"""Health rows of reading parts, built from descriptors and registries (task 6.2, design D14).

The spec scenarios of ``reading-parts`` ("Health SHALL show each reading part on
its own") come first. No check imports a part, downloads or starts anything.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from omrs.core import reading_parts
from omrs.integrations import part_registry
from omrs.integrations.pdf import blank_pages, maths_pages, page_routing, script_routing
from omrs.integrations.pdf.local_ocr import registry as local_ocr_registry
from omrs.transports.api import reading_parts_health as health
from omrs.transports.api import runtime_components

_PANIC = "PanicException: lock poisoned"


def _backends(settings: Any) -> dict[str, dict[str, Any]]:
    return {row["name"]: row for row in health.reading_parts_health(settings)["local_ocr_backends"]}


def _rules(settings: Any) -> dict[str, dict[str, Any]]:
    return {row["name"]: row for row in health.reading_parts_health(settings)["page_rules"]}


# ── Spec scenarios ───────────────────────────────────────────────────────


def test_a_panic_shows_the_default_backend_switched_off(effective_settings: Any) -> None:
    """Scenario "Backend switched off at run time"."""
    page_routing.switch_local_tier_off(_PANIC)

    row = _backends(effective_settings())["pp-ocrv6-small"]

    assert row["off_reason"] == _PANIC


def test_maths_on_and_non_latin_off_show_as_such(effective_settings: Any) -> None:
    """Scenario "Rule status"."""
    settings = effective_settings(ocr_maths_routing_enabled=True, ocr_non_latin_routing="off")

    rules = _rules(settings)

    assert (rules["maths"]["enabled"], rules["maths"]["version"]) == (
        True,
        maths_pages.MATHS_DETECTOR_VERSION,
    )
    assert rules["non_latin"]["enabled"] is False


# ── Local OCR backends ───────────────────────────────────────────────────


def test_the_default_backend_row_has_every_contract_field(effective_settings: Any) -> None:
    rows = health.reading_parts_health(effective_settings())["local_ocr_backends"]

    assert [row["name"] for row in rows] == ["pp-ocrv6-small"]
    assert rows[0]["label"] == "PP-OCRv6 small"
    assert rows[0]["off_reason"] is None
    assert rows[0]["effective_cut"] == 0.9
    assert rows[0]["source"] == "built-in"
    assert set(rows[0]) == {
        "name",
        "label",
        "installed",
        "model_present",
        "off_reason",
        "effective_cut",
        "source",
    }


def test_the_operator_cut_replaces_the_backend_cut(effective_settings: Any) -> None:
    row = _backends(effective_settings(ocr_local_min_confidence=0.75))["pp-ocrv6-small"]

    assert row["effective_cut"] == 0.75


def test_installed_comes_from_the_probe(
    effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local_ocr_registry.BACKENDS, "installed", lambda name: False)

    assert _backends(effective_settings())["pp-ocrv6-small"]["installed"] is False


def test_model_present_reads_the_descriptor_files(effective_settings: Any, tmp_path: Path) -> None:
    settings = effective_settings(ocr_local_model_directory=str(tmp_path))
    assert _backends(settings)["pp-ocrv6-small"]["model_present"] is False

    descriptor = reading_parts.local_backend("pp-ocrv6-small")
    for name in descriptor.health.model_files:
        (tmp_path / name).write_text("x", encoding="utf-8")

    assert _backends(settings)["pp-ocrv6-small"]["model_present"] is True


def test_backends_follow_the_list_order(
    effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = reading_parts.LocalOcrBackendDescriptor(
        name="fake-ocr",
        import_path="omrs_fake_ocr:BACKEND",
        label="Fake OCR",
        help_key="local_ocr_backend.fake-ocr",
        probe_module="omrs_fake_ocr_missing",
        min_confidence=0.8,
        calibrated_by="00-fake",
        producer="fake_ocr",
    )
    state = local_ocr_registry.BACKENDS.snapshot()
    monkeypatch.setattr(
        reading_parts, "LOCAL_OCR_BACKENDS", (*reading_parts.LOCAL_OCR_BACKENDS, fake)
    )
    local_ocr_registry.register(
        "fake-ocr",
        fake.import_path,
        producer="fake_ocr",
        min_confidence=0.8,
        calibrated_by="00-fake",
        probe_module=fake.probe_module,
    )
    try:
        settings = effective_settings(ocr_local_backends=("fake-ocr", "pp-ocrv6-small"))
        rows = health.reading_parts_health(settings)["local_ocr_backends"]
    finally:
        local_ocr_registry.BACKENDS.restore(state)

    assert [row["name"] for row in rows] == ["fake-ocr", "pp-ocrv6-small"]
    assert (rows[0]["installed"], rows[0]["model_present"], rows[0]["effective_cut"]) == (
        False,
        None,
        0.8,
    )


# ── Page rules ───────────────────────────────────────────────────────────


def test_rules_follow_rule_order_with_version_and_source(effective_settings: Any) -> None:
    rows = health.reading_parts_health(effective_settings())["page_rules"]

    assert [row["name"] for row in rows] == ["blank", "maths", "non_latin"]
    assert all(row["source"] == "built-in" for row in rows)
    assert rows[0]["enabled"] is True, "a rule without a setting is on"


def test_non_latin_detect_is_on(effective_settings: Any) -> None:
    assert _rules(effective_settings(ocr_non_latin_routing="detect"))["non_latin"]["enabled"]


def test_maths_off_is_off(effective_settings: Any) -> None:
    assert not _rules(effective_settings(ocr_maths_routing_enabled=False))["maths"]["enabled"]


def test_each_built_in_rule_version_equals_its_detector_version() -> None:
    """The row shows the descriptor version; it must equal the version in the identity."""
    detector = {
        "blank": blank_pages.BLANK_PAGE_TEST_VERSION,
        "maths": maths_pages.MATHS_DETECTOR_VERSION,
        "non_latin": script_routing.SCRIPT_DETECTOR_VERSION,
    }
    assert {rule.name: rule.version for rule in reading_parts.PAGE_RULES} == detector


# ── Discovered parts ─────────────────────────────────────────────────────


def _found(name: str | None, problem: str | None, descriptor: Any = None) -> Any:
    return part_registry.DiscoveredPart(
        name=name,
        kind="page_rule",
        group="omrs.page_rules",
        distribution="omrs-stamp",
        version="0.1.0",
        value="omrs_stamp:DESCRIPTOR",
        descriptor=descriptor,
        problem=problem,
    )


def test_discovered_parts_show_distribution_version_and_problem(
    effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = _found(None, "ImportError: no module named omrs_stamp")
    monkeypatch.setattr(part_registry, "discovered_parts", lambda: (broken,))

    rows = health.reading_parts_health(effective_settings())["discovered_parts"]

    assert rows == [
        {
            "name": None,
            "kind": "page_rule",
            "distribution": "omrs-stamp",
            "version": "0.1.0",
            "problem": "ImportError: no module named omrs_stamp",
        }
    ]


def test_nothing_discovered_gives_an_empty_list(effective_settings: Any) -> None:
    assert health.reading_parts_health(effective_settings())["discovered_parts"] == []


def test_a_discovered_rule_is_off_until_its_enabled_option(
    effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    descriptor = reading_parts.PageRuleDescriptor(
        name="stamp-check",
        import_path="omrs_stamp:RULE",
        label="Stamp check",
        help_key="page_rule.stamp-check",
        order=90,
        source="omrs-stamp",
    )
    monkeypatch.setattr(
        part_registry, "discovered_parts", lambda: (_found("stamp-check", None, descriptor),)
    )
    from omrs.integrations.pdf.page_rules import registry as rule_registry

    state = rule_registry.RULES.snapshot()
    rule_registry.register("stamp-check", "omrs_stamp:RULE", order=90, source="omrs-stamp")
    try:
        off = _rules(effective_settings())["stamp-check"]
        options = {"stamp-check": {"enabled": True}}
        on = _rules(effective_settings(reading_part_options=options))["stamp-check"]
    finally:
        rule_registry.RULES.restore(state)

    assert (off["enabled"], off["source"], off["label"]) == (False, "omrs-stamp", "Stamp check")
    assert on["enabled"] is True


# ── Robustness and the runtime block ─────────────────────────────────────


def test_no_settings_gives_empty_sections() -> None:
    assert health.reading_parts_health(None) == {
        "local_ocr_backends": [],
        "page_rules": [],
        "discovered_parts": [],
    }


def test_a_failing_section_is_empty_and_the_others_stay(
    effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> Any:
        raise RuntimeError("boom")

    monkeypatch.setattr(part_registry, "discovered_parts", broken)

    body = health.reading_parts_health(effective_settings())

    assert body["discovered_parts"] == []
    assert [row["name"] for row in body["page_rules"]] == ["blank", "maths", "non_latin"]


def test_runtime_components_read_the_model_files_from_the_descriptor() -> None:
    descriptor = reading_parts.local_backend("pp-ocrv6-small")

    assert runtime_components.LOCAL_MODEL_FILES == descriptor.health.model_files
    assert descriptor.health.cache_folder is not None
    folder = runtime_components.local_model_folder(SimpleNamespace(ocr_local_model_directory=""))
    assert folder.as_posix().endswith(descriptor.health.cache_folder)


def test_runtime_components_hold_no_hand_typed_model_file_name() -> None:
    """Mutation guard: the file names live in the descriptor only (design D14)."""
    source = Path(runtime_components.__file__).read_text(encoding="utf-8")
    descriptor = reading_parts.local_backend("pp-ocrv6-small")

    assert [name for name in descriptor.health.model_files if name in source] == []
