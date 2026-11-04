"""Tests for the pure-data reading part descriptors (change local-ocr-backends, D2)."""

from __future__ import annotations

import ast
import dataclasses
import sys
from pathlib import Path

import pytest

from omrs.core import reading_parts as parts
from omrs.core.reading_parts import (
    LOCAL_OCR_BACKENDS,
    PAGE_RULES,
    PDF_READERS,
    LocalOcrBackendDescriptor,
    PageRuleDescriptor,
    PdfReaderDescriptor,
    by_name,
    check_table,
    names,
)

MODULE_PATH = Path(parts.__file__)


def _backend(**overrides: object) -> LocalOcrBackendDescriptor:
    fields: dict[str, object] = {
        "name": "fake",
        "import_path": "fake.module:BACKEND",
        "label": "Fake",
        "help_key": "fake",
        "producer": "fake_ocr",
    }
    fields.update(overrides)
    return LocalOcrBackendDescriptor(**fields)  # type: ignore[arg-type]


def _rule(name: str, order: int) -> PageRuleDescriptor:
    return PageRuleDescriptor(
        name=name,
        import_path=f"fake.rules.{name}:RULE",
        label=name,
        help_key=name,
        order=order,
    )


def _reader(name: str) -> PdfReaderDescriptor:
    return PdfReaderDescriptor(
        name=name,
        import_path=f"fake.readers.{name}:Reader",
        label=name,
        help_key=name,
        text_format="plain",
        page_provenance=True,
    )


# -- built-in tables ---------------------------------------------------------


def test_pdf_reader_names_and_order() -> None:
    assert names(PDF_READERS) == ("liteparse", "pdf_inspector", "pypdfium2", "pypdf")


def test_local_backend_names() -> None:
    assert names(LOCAL_OCR_BACKENDS) == ("pp-ocrv6-small",)


def test_page_rule_names_and_orders() -> None:
    assert names(PAGE_RULES) == ("blank", "maths", "non_latin")
    assert [rule.order for rule in PAGE_RULES] == [10, 20, 30]


def test_kind_is_readable_per_table() -> None:
    assert {d.kind for d in PDF_READERS} == {"pdf_reader"}
    assert {d.kind for d in LOCAL_OCR_BACKENDS} == {"local_ocr_backend"}
    assert {d.kind for d in PAGE_RULES} == {"page_rule"}


def test_pdf_reader_facts_match_integration_registrations() -> None:
    facts = {
        d.name: (d.import_path, d.probe_module, d.text_format, d.page_provenance, d.output_revision)
        for d in PDF_READERS
    }
    assert facts == {
        "liteparse": (
            "omrs.integrations.pdf.liteparse:LiteParseReader",
            "liteparse",
            "plain",
            True,
            1,
        ),
        "pdf_inspector": (
            "omrs.integrations.pdf.pdf_inspector:PdfInspectorReader",
            "pdf_inspector",
            "markdown",
            True,
            2,
        ),
        "pypdfium2": (
            "omrs.integrations.pdf.pypdfium:PyPDFium2Reader",
            "pypdfium2",
            "plain",
            True,
            1,
        ),
        "pypdf": ("omrs.integrations.pdf.pypdf:PyPDFReader", "pypdf", "plain", True, 1),
    }


def test_local_backend_pp_ocrv6_small_values() -> None:
    backend = by_name(LOCAL_OCR_BACKENDS, "pp-ocrv6-small")
    assert backend.import_path == "omrs.integrations.pdf.local_ocr.pp_ocrv6_small:BACKEND"
    assert backend.probe_module == "pdf_inspector"
    assert backend.min_confidence == 0.9
    assert backend.calibrated_by == "39-local-tier-escalation-2026-09-30"
    assert backend.keeps_scripts is None
    assert backend.producer == "pdf_inspector_ocr"
    assert backend.model == "pp-ocrv6-small@oar-ocr-v0.7.0"
    assert backend.health.cache_folder == "pp-ocrv6-small/oar-ocr-v0.7.0"
    assert backend.health.model_files == (
        "pp-ocrv6_small_det.onnx",
        "pp-ocrv6_small_rec.onnx",
        "ppocrv6_dict.txt",
    )
    assert [s.name for s in backend.settings] == [
        "ocr_local_min_confidence",
        "ocr_local_offline",
        "ocr_local_model_directory",
    ]
    # The override is unset by default; the cut above applies (design D9).
    assert [s.default for s in backend.settings] == [None, False, ""]
    assert backend.identity is not None
    assert (backend.identity.block, backend.identity.keys, backend.identity.presence) == (
        "ocr_routing",
        ("local_tier",),
        "with_local_tier",
    )


def test_page_rule_values() -> None:
    blank = by_name(PAGE_RULES, "blank")
    maths = by_name(PAGE_RULES, "maths")
    non_latin = by_name(PAGE_RULES, "non_latin")

    assert blank.import_path == "omrs.integrations.pdf.page_rules.blank:RULE"
    assert (blank.drops_pages, blank.sends_direct) == (True, False)
    assert blank.settings == ()
    assert blank.identity is not None
    assert (blank.identity.block, blank.identity.keys) == ("ocr_routing", ("blank_page_test",))
    assert blank.identity.presence == "always"

    assert maths.sends_direct is True
    assert maths.drops_pages is False
    (maths_setting,) = maths.settings
    assert maths_setting.name == "ocr_maths_routing_enabled"
    assert maths_setting.env == "OCR_MATHS_ROUTING_ENABLED"
    assert maths_setting.default is True
    assert maths_setting.enters_identity is True
    assert maths.identity is not None
    assert (maths.identity.block, maths.identity.keys, maths.identity.presence) == (
        "maths_routing",
        ("enabled", "detector_version"),
        "always",
    )

    assert (non_latin.sends_direct, non_latin.has_post_check, non_latin.has_degrade) == (
        True,
        True,
        True,
    )
    (script_setting,) = non_latin.settings
    assert script_setting.name == "ocr_non_latin_routing"
    assert script_setting.env == "OCR_NON_LATIN_ROUTING"
    assert script_setting.default == "off"
    assert script_setting.accepted == ("off", "detect", "always")
    assert script_setting.enters_identity is True
    assert non_latin.identity is not None
    assert (non_latin.identity.block, non_latin.identity.keys) == (
        "parser",
        ("non_latin_routing",),
    )
    assert non_latin.identity.presence == "pdf_when_on"


@pytest.mark.parametrize("table", [PDF_READERS, LOCAL_OCR_BACKENDS, PAGE_RULES])
def test_built_in_names_are_unique(table: tuple) -> None:
    listed = names(table)
    assert len(listed) == len(set(listed))


def test_built_in_page_rule_orders_are_unique() -> None:
    orders = [rule.order for rule in PAGE_RULES]
    assert len(orders) == len(set(orders))


# -- helpers -----------------------------------------------------------------


def test_by_name_unknown_lists_the_names() -> None:
    with pytest.raises(KeyError) as excinfo:
        by_name(PAGE_RULES, "nope")
    message = str(excinfo.value)
    assert "nope" in message
    assert "blank" in message and "maths" in message and "non_latin" in message


def test_check_table_refuses_a_repeated_name() -> None:
    with pytest.raises(ValueError, match="pypdf"):
        check_table((_reader("pypdf"), _reader("pypdf")))


def test_check_table_refuses_a_repeated_page_rule_order() -> None:
    with pytest.raises(ValueError, match="20"):
        check_table((_rule("a", 20), _rule("b", 20)))


def test_check_table_accepts_the_same_name_in_two_kinds() -> None:
    check_table((_reader("shared"),))
    check_table((_rule("shared", 1),))


# -- frozen and validated ----------------------------------------------------


def test_descriptors_are_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        PAGE_RULES[0].order = 99  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        PDF_READERS[0].name = "other"  # type: ignore[misc]
    setting = PAGE_RULES[1].settings[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        setting.default = False  # type: ignore[misc]


def test_cut_without_calibration_raises() -> None:
    with pytest.raises(ValueError, match="fake"):
        _backend(min_confidence=0.8)


def test_cut_with_calibration_is_accepted() -> None:
    backend = _backend(min_confidence=0.8, calibrated_by="1-some-experiment")
    assert backend.min_confidence == 0.8


def test_backend_without_a_cut_is_accepted() -> None:
    assert _backend().min_confidence is None


# -- purity ------------------------------------------------------------------


def _imported_modules(tree: ast.AST) -> list[tuple[str, int]]:
    """Return (module, relative level) for every import in *tree*."""
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, 0) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append((node.module or "", node.level))
    return found


def _source_tree() -> ast.AST:
    return ast.parse(MODULE_PATH.read_text(encoding="utf-8"))


def test_module_imports_nothing_from_omrs() -> None:
    for module, level in _imported_modules(_source_tree()):
        assert level == 0, f"relative import (level {level}) of {module!r}"
        assert module.split(".")[0] != "omrs", f"imports {module}"


def test_module_imports_only_the_standard_library() -> None:
    top_levels = {module.split(".")[0] for module, _ in _imported_modules(_source_tree())}
    assert top_levels, "expected at least one import"
    outside = sorted(t for t in top_levels if t not in sys.stdlib_module_names)
    assert outside == []


def test_module_stays_under_the_line_ceiling() -> None:
    assert len(MODULE_PATH.read_text(encoding="utf-8").splitlines()) < 500
